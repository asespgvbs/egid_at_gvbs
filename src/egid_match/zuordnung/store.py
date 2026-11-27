"""Persistenz und Excel für das lokale manuelle Zuordnungswerkzeug."""

from contextlib import contextmanager
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from itertools import chain
import json
from pathlib import Path
import sqlite3

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .. import matching
from ..common import ConflictError, ReviewError, egid_text, identifiers


STATUSES = ("Offen", "Sonderfall", "Abgeschlossen", "Unklar", "Zurückgestellt", "Keine Zuordnung möglich")
FINISHED = {"Abgeschlossen", "Keine Zuordnung möglich"}
OPEN_STATUSES = {"Offen", "Unklar", "Zurückgestellt"}
QUEUE_STATUSES = {"open": OPEN_STATUSES, "special": {"Sonderfall"}, "completed": FINISHED}
SHEET = "review_address_suffix"
PRODUCT = "egid-match-manual-review"
AUTOMATIC_SHEET = "Automatische Zuordnungen"
AUTOMATIC_META = "automatic_egids"
REVIEW_CATEGORIES = (SHEET, matching.SUFFIX_PAIR_REVIEW, matching.SUFFIX_SINGLE_REVIEW, "zuordnungskonflikt")
MATCHING_COLUMNS = {"GVBSID", "Matching-Kategorie", "EGID", "Automatische Zuordnung", "EGID-Kandidaten"}


def _encode(value):
    if isinstance(value, (datetime, date, time)):
        return {"_excel_type": type(value).__name__, "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {"_excel_type": "timedelta", "value": value.total_seconds()}
    raise TypeError("Nicht unterstützter Excel-Zelltyp.")


def _decode(value):
    kind = value.get("_excel_type")
    converters = {"datetime": datetime.fromisoformat, "date": date.fromisoformat, "time": time.fromisoformat}
    if kind == "timedelta":
        return timedelta(seconds=value["value"])
    return converters[kind](value["value"]) if kind in converters else value


def encode(value):
    return json.dumps(value, ensure_ascii=False, default=_encode)


def decode(value):
    return json.loads(value, object_hook=_decode)


def prepare_rows(headers, rows):
    """Validiert den Import vollständig, bevor eine Transaktion beginnt."""
    headers = [matching.txt(value) for value in headers]
    if not headers or any(not value for value in headers) or len(set(headers)) != len(headers):
        raise ReviewError("Die Excel-Kopfzeile enthält leere oder doppelte Spaltennamen.")
    prepared, seen = [], set()
    for values in rows:
        values = list(values[:len(headers)]) + [None] * max(0, len(headers) - len(values))
        if not any(value is not None for value in values):
            continue
        original = dict(zip(headers, values))
        fields = {matching.COLUMN_ALIASES.get(key, key): value for key, value in original.items()}
        gvbsid = matching.txt(fields.get("GVBSID"))
        if not gvbsid:
            control, building = matching.txt(fields.get("Kontrollnummer")), matching.txt(fields.get("Gebäudenummer"))
            if control and building:
                gvbsid = matching.gvbsid_text((control, building))
        if not gvbsid or gvbsid in seen:
            raise ReviewError("Jede importierte GVBSID muss vorhanden und innerhalb der Datei eindeutig sein.")
        seen.add(gvbsid)
        address = matching.txt(fields.get("Suchadresse") or fields.get("GVBS-Adresse"))
        if not address:
            address = matching.search_address({"Strasse": fields.get("Strasse"), "Hausnummer": fields.get("Hausnummer"),
                                               "Hausnummer Zusatz": fields.get("Hausnummer Zusatz"), "Postleitzahl": fields.get("Postleitzahl")})
        direct = {egid_text(token) for token in identifiers(fields.get("EGID-Kandidaten"))}
        suffix = {egid_text(token) for token in identifiers(fields.get("EGID mit Hausnummernzusatz"))}
        if matching.txt(fields.get("EGID")):
            direct.add(egid_text(fields["EGID"]))
        grids = set()
        for name in ("EGRID", "EGRID-Kandidaten", "EGRID der Hausnummernzusätze"):
            grids.update(identifiers(fields.get(name)))
        prepared.append({"gvbsid": gvbsid, "purpose": matching.txt(fields.get("Zweckbestimmung")),
                         "address": address, "candidates": sorted(direct), "suffix_candidates": sorted(suffix),
                         "grids": sorted(grids), "raw": original})
    if not prepared:
        raise ReviewError("Die Adress-Suffix-Prüffallblätter enthalten keine importierbaren Zeilen.")
    return headers, prepared


def _sheet_name(workbook, title):
    return next((name for name in workbook.sheetnames if name.strip().casefold() == title.casefold()), None)


def _summary_counts(headers, rows):
    """Nur die vom Matching exportierte Kategorienbilanz als Vollständigkeitsbeleg."""
    category_index, count_index = headers.index("Kategorie"), headers.index("Anzahl")
    categories = {category for category, _, _ in matching.CATEGORIES} | {"zuordnungskonflikt"}
    counts, total = Counter(), None
    for row in rows:
        if len(row) <= max(category_index, count_index):
            continue
        category = matching.category_name(row[category_index])
        if category not in categories and category != "Gesamt":
            continue
        count = row[count_index]
        if type(count) is not int or count < 0:
            return None
        if category == "Gesamt":
            if total is not None:
                return None
            total = count
        else:
            if category in counts:
                return None
            counts[category] = count
    return counts if total is not None and sum(counts.values()) == total else None


def _matching_sheet(workbook):
    named = _sheet_name(workbook, "Matching")
    if named is not None:
        return named
    candidates, summaries = [], []
    for name in workbook.sheetnames:
        rows = workbook[name].iter_rows(values_only=True)
        headers = [matching.txt(value) for value in next(rows, ())]
        if len(set(headers)) != len(headers):
            continue
        if MATCHING_COLUMNS <= set(headers):
            candidates.append((name, headers.index("Matching-Kategorie")))
        if {"Kategorie", "Anzahl"} <= set(headers):
            counts = _summary_counts(headers, rows)
            if counts is not None:
                summaries.append(counts)
    for name, index in candidates:
        counts = Counter()
        for row in workbook[name].iter_rows(min_row=2, values_only=True):
            if any(value is not None for value in row):
                counts[matching.category_name(row[index]) if len(row) > index else ""] += 1
        if any(counts == summary for summary in summaries):
            return name
    return None


def read_automatic_egids(workbook, matching_name=None):
    """Globale Sperrliste aus dem vollständigen Matching oder einem App-Export."""
    blocked = set()
    known = False
    matching_name = matching_name if matching_name is not None else _matching_sheet(workbook)
    if matching_name is not None:
        known = True
        rows = workbook[matching_name].iter_rows(values_only=True)
        headers = [matching.txt(value) for value in next(rows, ())]
        required = ("EGID", "Automatische Zuordnung", "Matching-Kategorie")
        if any(headers.count(name) != 1 for name in required):
            raise ReviewError("Das Blatt Matching benötigt eindeutige Spalten EGID, Automatische Zuordnung und Matching-Kategorie.")
        for row in rows:
            fields = dict(zip(headers, row))
            egid = matching.txt(fields.get("EGID"))
            automatic = matching.txt(fields.get("Automatische Zuordnung")) == "Ja"
            category = matching.category_name(fields.get("Matching-Kategorie"))
            if not egid and not automatic and (category not in matching.AUTO_CATEGORIES
                                               or category == matching.SUFFIX_SINGLE_REVIEW):
                continue
            if not egid or not automatic or category not in matching.AUTO_CATEGORIES:
                raise ReviewError("Das Blatt Matching enthält eine widersprüchliche automatische EGID-Zuordnung.")
            blocked.add(egid_text(egid))
    automatic_name = _sheet_name(workbook, AUTOMATIC_SHEET)
    if automatic_name is not None:
        known = True
        rows = workbook[automatic_name].iter_rows(values_only=True)
        if tuple(next(rows, ())) != ("EGID",):
            raise ReviewError("Das Blatt Automatische Zuordnungen benötigt genau die Spalte EGID.")
        for row in rows:
            if row and matching.txt(row[0]):
                blocked.add(egid_text(row[0]))
    return blocked if known else None


def read_review_excel(path):
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        matching_name = _matching_sheet(workbook)
        matching_rows, matching_headers = None, ()
        if matching_name is not None:
            matching_rows = workbook[matching_name].iter_rows(values_only=True)
            matching_headers = tuple(next(matching_rows, ()))
        names = [matching.txt(value) for value in matching_headers]
        headers, values = None, []
        # Ein vollständiges Gesamtblatt enthält auch Fälle fehlender Kategorieblätter.
        if not MATCHING_COLUMNS <= set(names):
            accepted = {name.strip().casefold() for category in REVIEW_CATEGORIES
                        for name in (category, category[:31], matching.CATEGORY_SHEET_TITLES.get(category, category))}
            accepted.update(alias.casefold() for alias, category in matching.CATEGORY_ALIASES.items()
                            if category in REVIEW_CATEGORIES)
            row_sets = []
            for name in workbook.sheetnames:
                if name.strip().casefold() not in accepted:
                    continue
                rows = workbook[name].iter_rows(values_only=True)
                sheet_headers = tuple(next(rows, ()))
                if headers is not None and headers != sheet_headers:
                    raise ReviewError("Die Prüffallblätter müssen dieselben Spalten enthalten.")
                headers = sheet_headers
                row_sets.append(rows)
            values = list(chain.from_iterable(row_sets))
        if not any(any(value is not None for value in row) for row in values):
            if matching_name is None:
                raise ReviewError("Kein importierbarer GVBSID-Matching-Bestand erkannt. Bitte die vollständige "
                                  "Matching-Arbeitsmappe oder einen Zuordnungsapp-Export laden. Ein umbenanntes "
                                  "Gesamtblatt benötigt die exportierten Matching-Spalten und eine passende "
                                  "Kategorie-Zusammenfassung mit Gesamtzahl.")
            headers = matching_headers
            if names.count("Matching-Kategorie") != 1:
                raise ReviewError("Für den Prüffallimport aus dem Gesamtblatt wird genau eine "
                                  "Spalte Matching-Kategorie benötigt.")
            index = names.index("Matching-Kategorie")
            values = [row for row in matching_rows if len(row) > index
                      and matching.category_name(row[index]) in REVIEW_CATEGORIES]
            if not values:
                raise ReviewError("Das Gesamtblatt enthält keine Adress-Suffix-Prüffälle. "
                                  "Automatisch zugeteilte Fälle werden nicht als Prüffälle importiert.")
        # Ältere Exporte dieser Kategorie bleiben als manuelle Prüffälle importierbar.
        normalized_headers = [matching.txt(value) for value in headers]
        if "Automatische Zuordnung" in normalized_headers:
            auto_index = normalized_headers.index("Automatische Zuordnung")
            values = [row for row in values if len(row) <= auto_index or matching.txt(row[auto_index]) != "Ja"]
        headers, prepared = prepare_rows(headers, values)
        return headers, prepared, read_automatic_egids(workbook, matching_name)
    finally:
        workbook.close()


class ReviewStore:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextmanager
    def connection(self, write=False):
        # mode=rw erzeugt niemals unbemerkt eine fehlende Datei.
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except BaseException:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    @classmethod
    def create(cls, path):
        path = Path(path)
        # Ausschliesslich neu erstellen; bestehende Dateien nie überschreiben.
        with path.open("xb"):
            pass
        store = cls(path)
        store.open()
        return store

    def open(self):
        with self.connection(write=True) as connection:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if tables and "review_meta" not in tables:
                raise ReviewError("Diese Datenbank gehört nicht zum Zuordnungswerkzeug. Bitte eine separate neue Datenbank erstellen.")
            if tables:
                if not {"review_meta", "review_records", "review_assignments"} <= tables:
                    raise ReviewError("Die Zuordnungsdatenbank ist unvollständig. Sie wird nicht automatisch verändert.")
                metadata = dict(connection.execute("SELECT key, value FROM review_meta"))
                if metadata.get("product") != PRODUCT or metadata.get("version") != "1":
                    raise ReviewError("Die Datenbank hat ein unbekanntes oder nicht unterstütztes Format.")
                return
            connection.execute("CREATE TABLE review_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("""CREATE TABLE review_records (
                gvbsid TEXT PRIMARY KEY, position INTEGER NOT NULL, purpose TEXT NOT NULL, address TEXT NOT NULL,
                candidates TEXT NOT NULL, suffix_candidates TEXT NOT NULL, grids TEXT NOT NULL, raw TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Offen', comment TEXT NOT NULL DEFAULT '',
                version INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL DEFAULT '')""")
            connection.execute("""CREATE TABLE review_assignments (
                gvbsid TEXT NOT NULL REFERENCES review_records(gvbsid), egid TEXT NOT NULL,
                PRIMARY KEY (gvbsid, egid))""")
            connection.executemany("INSERT INTO review_meta VALUES (?, ?)", [("product", PRODUCT), ("version", "1"), ("headers", "[]")])

    def import_rows(self, headers, rows, *, automatic_egids=None):
        headers, prepared = prepare_rows(headers, rows)
        blocked = None if automatic_egids is None else {egid_text(value) for value in automatic_egids}
        with self.connection(write=True) as connection:
            if blocked is not None:
                previous_blocked = self._automatic_egids(connection)
                blocked.update(previous_blocked or ())
                connection.execute("INSERT INTO review_meta VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                   (AUTOMATIC_META, encode(sorted(blocked, key=int))))
            previous = decode(connection.execute("SELECT value FROM review_meta WHERE key='headers'").fetchone()[0])
            combined = previous + [header for header in headers if header not in previous]
            connection.execute("UPDATE review_meta SET value=? WHERE key='headers'", (encode(combined),))
            position = connection.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM review_records").fetchone()[0]
            for offset, record in enumerate(prepared):
                connection.execute("""INSERT INTO review_records
                    (gvbsid, position, purpose, address, candidates, suffix_candidates, grids, raw)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(gvbsid) DO UPDATE SET purpose=excluded.purpose, address=excluded.address,
                    candidates=excluded.candidates, suffix_candidates=excluded.suffix_candidates,
                    grids=excluded.grids, raw=excluded.raw, version=review_records.version + 1""",
                    (record["gvbsid"], position + offset, record["purpose"], record["address"],
                     encode(record["candidates"]), encode(record["suffix_candidates"]), encode(record["grids"]), encode(record["raw"])))
        return len(prepared)

    def import_excel(self, path):
        headers, prepared, blocked = read_review_excel(path)
        if blocked is None:
            raise ReviewError("Bitte die vollständige Matching-Datei mit dem Blatt Matching laden. "
                              "Ohne die automatischen Zuordnungen können EGID nicht sicher gesperrt werden.")
        # prepare_rows wird für denselben vollständig geprüften Originalinhalt verwendet.
        return self.import_rows(headers, [list(record["raw"].values()) for record in prepared], automatic_egids=blocked)

    @staticmethod
    def _automatic_egids(connection):
        row = connection.execute("SELECT value FROM review_meta WHERE key=?", (AUTOMATIC_META,)).fetchone()
        return None if row is None else {egid_text(value) for value in decode(row[0])}

    def automatic_egids(self):
        with self.connection() as connection:
            return self._automatic_egids(connection)

    def records(self):
        with self.connection() as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM review_records ORDER BY position, gvbsid")]
            assignments = {}
            for row in connection.execute("SELECT gvbsid, egid FROM review_assignments ORDER BY length(egid), egid"):
                assignments.setdefault(row[0], []).append(row[1])
        for row in rows:
            for name in ("candidates", "suffix_candidates", "grids", "raw"):
                row[name] = decode(row[name])
            row["assigned"] = assignments.get(row["gvbsid"], [])
        return rows

    def progress(self):
        with self.connection() as connection:
            counts = dict(connection.execute("SELECT status, COUNT(*) FROM review_records GROUP BY status"))
        total = sum(counts.values())
        return {"total": total, "completed": counts.get("Abgeschlossen", 0),
                "impossible": counts.get("Keine Zuordnung möglich", 0),
                "special": counts.get("Sonderfall", 0),
                "remaining": sum(counts.get(status, 0) for status in OPEN_STATUSES)}

    def save(self, decisions, allowed_egids, *, package_egrid=None):
        if not isinstance(decisions, list) or not decisions:
            raise ReviewError("Keine Entscheidungen zum Speichern vorhanden.")
        seen = set()
        with self.connection(write=True) as connection:
            if package_egrid is not None:
                members = {row[0] for row in connection.execute("SELECT gvbsid, grids FROM review_records")
                           if package_egrid in decode(row[1])}
                submitted = {matching.txt(row.get("gvbsid")) for row in decisions}
                if not members <= submitted:
                    raise ConflictError("Das EGRID-Paket hat neue Fälle. Bitte das gesamte Paket neu laden.")
            blocked = self._automatic_egids(connection)
            if blocked is None:
                raise ReviewError("Bitte zuerst die vollständige Matching-Datei importieren, damit automatisch zugeteilte EGID gesperrt sind.")
            for decision in decisions:
                gvbsid = matching.txt(decision.get("gvbsid"))
                if gvbsid in seen:
                    raise ReviewError("Eine GVBSID darf nur einmal je Speichervorgang vorkommen.")
                seen.add(gvbsid)
                row = connection.execute("SELECT version FROM review_records WHERE gvbsid=?", (gvbsid,)).fetchone()
                if row is None:
                    raise ReviewError("Die angegebene GVBSID ist nicht vorhanden.")
                if decision.get("version") != row[0]:
                    raise ConflictError("Ein Datensatz wurde zwischenzeitlich geändert. Bitte neu laden; es wurde nichts gespeichert.")
                values = decision.get("assigned", [])
                if not isinstance(values, list):
                    raise ReviewError("Die Zuordnung muss eine Liste von EGID sein.")
                assigned = {egid_text(value) for value in values}
                if assigned & blocked:
                    raise ReviewError("Diese EGID sind bereits automatisch zugeteilt oder manuell vergeben und für weitere Zuordnungen gesperrt: "
                                      + ", ".join(sorted(assigned & blocked, key=int)))
                if not assigned <= set(allowed_egids):
                    raise ReviewError("Eine EGID gehört nicht zu den verfügbaren Kandidaten oder verlässlich geladenen Geodaten.")
                status = decision.get("status", "Abgeschlossen")
                if status not in STATUSES:
                    raise ReviewError("Unbekannter Bearbeitungsstatus.")
                if status == "Keine Zuordnung möglich" and assigned:
                    raise ReviewError("Keine Zuordnung möglich darf keine zugeteilte EGID enthalten.")
                comment = decision.get("comment", "")
                if not isinstance(comment, str) or len(comment) > 20000:
                    raise ReviewError("Der Kommentar ist ungültig oder zu lang.")
                updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
                connection.execute("UPDATE review_records SET status=?, comment=?, version=version+1, updated_at=? WHERE gvbsid=?",
                                   (status, comment, updated, gvbsid))
                connection.execute("DELETE FROM review_assignments WHERE gvbsid=?", (gvbsid,))
                connection.executemany("INSERT INTO review_assignments VALUES (?, ?)", [(gvbsid, egid) for egid in sorted(assigned)])

    def export_workbook(self):
        # Ein gemeinsamer Lese-Snapshot verhindert einen gemischten Bearbeitungsstand.
        with self.connection() as connection:
            connection.execute("BEGIN")
            blocked = self._automatic_egids(connection)
            headers = decode(connection.execute("SELECT value FROM review_meta WHERE key='headers'").fetchone()[0])
            records = [dict(row) for row in connection.execute("SELECT * FROM review_records ORDER BY position, gvbsid")]
            assigned = {}
            for gvbsid, egid in connection.execute("SELECT gvbsid, egid FROM review_assignments ORDER BY length(egid), egid"):
                assigned.setdefault(gvbsid, []).append(egid)
        extras = []
        for title in ("Manuell zugeteilte EGID", "Bearbeitungsstatus", "Kommentar", "Letzte Bearbeitung"):
            label, number = title, 1
            while label in headers or label in extras:
                number += 1
                label = f"{title} (aktuell {number})"
            extras.append(label)
        workbook = Workbook()
        original = workbook.active
        original.title = SHEET
        original.append(headers + extras)
        relations = workbook.create_sheet("Zuordnungen")
        relations.append(["GVBSID", "Zweckbestimmung", "EGID", "Bearbeitungsstatus", "Kommentar"])
        pending = workbook.create_sheet("Offene Fälle")
        pending.append(headers + extras)
        special = workbook.create_sheet("Sonderfälle")
        special.append(headers + extras)
        completed = workbook.create_sheet("Abgeschlossene Fälle")
        completed.append(headers + extras)
        if blocked is not None:
            automatic = workbook.create_sheet(AUTOMATIC_SHEET)
            automatic.append(["EGID"])
            for egid in sorted(blocked, key=int):
                automatic.append([egid])
        for record in records:
            raw = decode(record["raw"])
            values = [raw.get(header) for header in headers] + [", ".join(assigned.get(record["gvbsid"], [])), record["status"], record["comment"], record["updated_at"]]
            original.append(values)
            if record["status"] in OPEN_STATUSES:
                pending.append(values)
            elif record["status"] == "Sonderfall":
                special.append(values)
            elif record["status"] in FINISHED:
                completed.append(values)
            for egid in assigned.get(record["gvbsid"], []):
                relations.append([record["gvbsid"], record["purpose"], egid, record["status"], record["comment"]])
        for sheet in workbook.worksheets:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="17365D")
                cell.alignment = Alignment(wrap_text=True)
            for column in sheet.columns:
                sheet.column_dimensions[column[0].column_letter].width = 32
            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
                    # Manuelle Eingaben sind Text; ursprüngliche Excel-Formeln bleiben erhalten.
                    if sheet is relations or cell.column > len(headers):
                        if isinstance(cell.value, str):
                            cell.data_type = "s"
        return workbook

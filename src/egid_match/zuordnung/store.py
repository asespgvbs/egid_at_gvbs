"""Persistenz und Excel für das lokale manuelle Zuordnungswerkzeug."""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from itertools import chain
import json
from pathlib import Path
import sqlite3

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .. import matching
from ..common import ConflictError, ReviewError, egid_text, identifiers


STATUSES = ("Offen", "Abgeschlossen", "Unklar", "Zurückgestellt", "Keine Zuordnung möglich")
FINISHED = {"Abgeschlossen", "Keine Zuordnung möglich"}
SHEET = "review_address_suffix"
PRODUCT = "egid-match-manual-review"


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


def read_review_excel(path):
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        sheets = [name for name in (SHEET, matching.SUFFIX_PAIR_REVIEW, matching.SUFFIX_SINGLE_REVIEW)
                  if name in workbook.sheetnames]
        if not sheets:
            raise ReviewError("Die Excel-Datei enthält kein Adress-Suffix-Prüffallblatt "
                              "(review_address_suffix, address_suffix_pair_lt4 oder review_suffix_single_building).")
        headers, row_sets = None, []
        for name in sheets:
            rows = workbook[name].iter_rows(values_only=True)
            sheet_headers = tuple(next(rows, ()))
            if headers is not None and headers != sheet_headers:
                raise ReviewError("Die Prüffallblätter müssen dieselben Spalten enthalten.")
            headers = sheet_headers
            row_sets.append(rows)
        return prepare_rows(headers, chain.from_iterable(row_sets))
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

    def import_rows(self, headers, rows):
        headers, prepared = prepare_rows(headers, rows)
        with self.connection(write=True) as connection:
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
        headers, prepared = read_review_excel(path)
        # prepare_rows wird für denselben vollständig geprüften Originalinhalt verwendet.
        return self.import_rows(headers, [list(record["raw"].values()) for record in prepared])

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
                "remaining": total - sum(counts.get(status, 0) for status in FINISHED)}

    def save(self, decisions, allowed_egids):
        if not isinstance(decisions, list) or not decisions:
            raise ReviewError("Keine Entscheidungen zum Speichern vorhanden.")
        seen = set()
        with self.connection(write=True) as connection:
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
                if not assigned <= set(allowed_egids):
                    raise ReviewError("Eine EGID gehört nicht zu den verfügbaren Kandidaten oder verlässlich geladenen Geodaten.")
                status = decision.get("status", "Abgeschlossen" if assigned else "Keine Zuordnung möglich")
                if status not in STATUSES:
                    raise ReviewError("Unbekannter Bearbeitungsstatus.")
                if status == "Abgeschlossen" and not assigned:
                    raise ReviewError("Abgeschlossen erfordert mindestens eine zugeteilte EGID.")
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
        for record in records:
            raw = decode(record["raw"])
            values = [raw.get(header) for header in headers] + [", ".join(assigned.get(record["gvbsid"], [])), record["status"], record["comment"], record["updated_at"]]
            original.append(values)
            if record["status"] not in FINISHED:
                pending.append(values)
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

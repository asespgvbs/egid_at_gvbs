"""Eigenständige EGID-Abdeckung auf Basis des GVBSID-Matchings."""

import argparse
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import matching as gvbs


DEFAULT_OUTPUT = Path("egid_abdeckung.xlsx")
NO_DIRECT_MATCH = "kein direkter Adresstreffer"
CATEGORY_PRIORITY = (
    "perfect_match",
    "super_match",
    "oneEgid_oneAddress_multipleGVBSIDs",
    "oneEgid_multipleAddresses_multipleGVBSIDs",
    gvbs.SUFFIX_PAIR_AUTO,
    gvbs.SUFFIX_PAIR_REVIEW,
    "multiple_egid",
    "multiple_gvbsid_multiple_egid",
    gvbs.SUFFIX_SINGLE_REVIEW,
    "review_address_suffix",
    "invalid_gwr_data",
    "zuordnungskonflikt",
    "manuell_zugeteilt",
    NO_DIRECT_MATCH,
)
AUTOMATIC = "Automatisch zugeordnet"
DIRECT_ONLY = "Direkter GVBS-Adresskandidat, aber nicht automatisch zugeordnet"
NO_CANDIDATE = "Kein direkter GVBS-Adresskandidat"
OVERVIEW_COLUMNS = (
    "EGID", "EGRID", "Alle GWR-Adressen", "Anzahl GWR-Adressen",
    "Direkter GVBS-Adresskandidat vorhanden", "Automatisch zugeordnet",
    "EGID-Hauptkategorie", "Alle vorkommenden Matching-Kategorien",
    "Zugehörige GVBSIDs", "Anzahl unterschiedlicher GVBSIDs",
    "Nur über Hausnummernzusatz erkannt", "Bemerkung",
)
MISSING_COLUMNS = (
    "EGID", "EGRID", "Alle GWR-Adressen", "Anzahl GWR-Adressen",
    "Strasse", "Hausnummer", "PLZ", "Hinweis Hausnummernzusatz",
    "Zugehörige GVBSIDs über Hausnummernzusatz", "Bemerkung",
)


def read_egid_inventory(db):
    """Vollbestand und alle Adressen; auch unvollständige Adressen erhalten."""
    db = Path(db)
    if not db.is_file():
        raise FileNotFoundError(f"GWR-Datenbank nicht gefunden: {db}")
    connection = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        egids = {row[0] for row in connection.execute(
            "SELECT DISTINCT EGID FROM building WHERE GSTAT = 1004 AND EGID IS NOT NULL"
        )}
        addresses = defaultdict(set)
        for egid, street, number, postal in connection.execute("""
            SELECT DISTINCT e.EGID, e.STRNAME, e.DEINR, e.DPLZ4
            FROM entrance e JOIN building b ON e.EGID = b.EGID
            WHERE b.GSTAT = 1004 AND b.EGID IS NOT NULL
        """):
            address = tuple(gvbs.txt(value) for value in (street, number, postal))
            if any(address):
                addresses[egid].add(address)
        return egids, dict(addresses)
    finally:
        connection.close()


def _identifiers(value):
    """Liest ausschliesslich die vom bestehenden Matching erzeugten ID-Listen."""
    return {part.strip() for part in gvbs.txt(value).split(",") if part.strip()}


def analyze_coverage(existing_egids, matching_results, egid_addresses, egid_grids):
    """Kein neues Matching: vorhandene Kandidaten und Zuordnungen invertieren."""
    inventory = {gvbs.txt(egid): egid for egid in existing_egids}
    direct = defaultdict(set)
    categories = defaultdict(set)
    suffix = defaultdict(set)
    assigned = set()
    assigned_gvbsids = defaultdict(set)
    issues = []

    def report(kind, egid, gvbsid, detail):
        issues.append({"Art": kind, "EGID": egid, "GVBSID": gvbsid, "Bemerkung": detail})

    for result in matching_results:
        gvbsid = gvbs.txt(result.get("GVBSID"))
        category = gvbs.category_name(result["Matching-Kategorie"])
        candidates = _identifiers(result.get("EGID-Kandidaten"))
        for token in sorted(candidates):
            if token not in inventory:
                report("Kandidat ausserhalb GWR-Bestand", token, gvbsid, category)
                continue
            direct[token].add(gvbsid)
            categories[token].add(category)
            if category not in CATEGORY_PRIORITY[:-1]:
                report("Unerwartete Kandidatenkategorie", token, gvbsid, category)
        suffix_candidates = _identifiers(result.get("EGID mit Hausnummernzusatz"))
        for token in sorted(suffix_candidates):
            if token not in inventory:
                report("Hausnummernzusatz ausserhalb GWR-Bestand", token, gvbsid, category)
            else:
                suffix[token].add(gvbsid)

        assigned_token = gvbs.txt(result.get("EGID"))
        automatic_flag = result.get("Automatische Zuordnung") == "Ja"
        if bool(assigned_token) != automatic_flag:
            report("Widersprüchliche Zuordnung", assigned_token, gvbsid,
                   "EGID und Kennzeichen Automatische Zuordnung stimmen nicht überein.")
        if assigned_token:
            suffix_assignment = (
                category == gvbs.SUFFIX_PAIR_AUTO
                and gvbsid.rsplit("-", 1)[-1] == "1"
                and assigned_token in suffix_candidates
            )
            if assigned_token not in inventory:
                report("Zuordnung ausserhalb GWR-Bestand", assigned_token, gvbsid, category)
            elif not automatic_flag or category not in gvbs.AUTO_CATEGORIES or not (assigned_token in candidates or suffix_assignment):
                report("Ungültige automatische Zuordnung", assigned_token, gvbsid, category)
            else:
                assigned.add(assigned_token)
                assigned_gvbsids[assigned_token].add(gvbsid)
                categories[assigned_token].add(category)

    priority = {name: index for index, name in enumerate(CATEGORY_PRIORITY)}
    rows = []
    for egid in gvbs.sorted_egids(inventory.values()):
        token = gvbs.txt(egid)
        addresses = sorted(egid_addresses.get(egid, set()))
        grids = sorted(egid_grids.get(egid, set()))
        all_categories = sorted(categories[token], key=lambda name: (priority.get(name, len(priority)), name))
        has_direct = bool(direct[token])
        only_suffix = not has_direct and bool(suffix[token])
        remarks = []
        if not addresses:
            remarks.append("Keine GWR-Adresse vorhanden.")
        elif any(not all(address) for address in addresses):
            remarks.append("Mindestens eine GWR-Adresse ist unvollständig.")
        if not grids:
            remarks.append("Keine EGRID vorhanden.")
        if only_suffix:
            remarks.append("Nur über Hausnummernzusatz erkannt; kein direkter GVBS-Adresskandidat.")
            if token in assigned:
                remarks.append("Über die Kubatur-Paarregel automatisch zur Gebäudenummer 1 zugeordnet.")
        if len(all_categories) > 1:
            remarks.append("Mehrere Matching-Kategorien; Hauptkategorie gemäss statistischer Priorität.")
        rows.append({
            "EGID": egid,
            "EGRID": "\n".join(grids),
            "Alle GWR-Adressen": "\n".join(gvbs.address_text(address) for address in addresses),
            "Anzahl GWR-Adressen": len(addresses),
            "Direkter GVBS-Adresskandidat vorhanden": "Ja" if has_direct else "Nein",
            "Automatisch zugeordnet": "Ja" if token in assigned else "Nein",
            "EGID-Hauptkategorie": all_categories[0] if has_direct or token in assigned else NO_DIRECT_MATCH,
            "Alle vorkommenden Matching-Kategorien": "\n".join(all_categories),
            "Zugehörige GVBSIDs": "\n".join(sorted(direct[token] | assigned_gvbsids[token])),
            "Anzahl unterschiedlicher GVBSIDs": len(direct[token] | assigned_gvbsids[token]),
            "Nur über Hausnummernzusatz erkannt": "Ja" if only_suffix else "Nein",
            "Bemerkung": " ".join(remarks),
            "_addresses": addresses,
            "_suffix_gvbsids": sorted(suffix[token]),
        })
    return rows, issues


def summarize_coverage(rows):
    """Beide Bilanzen zählen EGIDs, nicht GVBS-Zeilen oder Kategoriebeziehungen."""
    if len({row["EGID"] for row in rows}) != len(rows):
        raise ValueError("Eine EGID kommt mehrfach in der Gesamtübersicht vor.")
    categories = Counter(row["EGID-Hauptkategorie"] for row in rows)
    statuses = Counter()
    for row in rows:
        if row["Automatisch zugeordnet"] == "Ja":
            if (row["Direkter GVBS-Adresskandidat vorhanden"] != "Ja"
                    and not (row["Nur über Hausnummernzusatz erkannt"] == "Ja"
                             and row["EGID-Hauptkategorie"] == gvbs.SUFFIX_PAIR_AUTO)):
                raise ValueError("Automatische Zuordnung ohne direkten Adresskandidaten.")
            statuses[AUTOMATIC] += 1
        elif row["Direkter GVBS-Adresskandidat vorhanden"] == "Ja":
            statuses[DIRECT_ONLY] += 1
        else:
            statuses[NO_CANDIDATE] += 1
    return categories, statuses


def save_coverage_excel(path, rows, issues):
    categories, statuses = summarize_coverage(rows)
    total = len(rows)
    workbook = Workbook()
    summary = workbook.active
    summary.title = "EGID-Zusammenfassung"
    summary.append(["Auswertung", "Anzahl", "Anteil am Gesamt", "Kontrolle"])

    def add_summary(label, count, control=None):
        summary.append([label, count, count / total if total else 0, control])

    add_summary("Gesamtzahl bestehender EGIDs", total)
    extra_categories = sorted(set(categories) - set(CATEGORY_PRIORITY))
    for category in (*CATEGORY_PRIORITY, *extra_categories):
        add_summary(category, categories[category])
    for status in (AUTOMATIC, DIRECT_ONLY, NO_CANDIDATE):
        add_summary(status, statuses[status])
    add_summary("Nur über Hausnummernzusatz erkannt",
                sum(row["Nur über Hausnummernzusatz erkannt"] == "Ja" for row in rows),
                "Teilmenge von Kein direkter GVBS-Adresskandidat")
    add_summary("Kontrollsumme Abdeckungsstatus", sum(statuses.values()),
                "OK" if sum(statuses.values()) == total else "FEHLER")
    add_summary("Kontrollsumme Hauptkategorien", sum(categories.values()),
                "OK" if sum(categories.values()) == total else "FEHLER")
    add_summary("Differenz Abdeckungsstatus zu Gesamt", sum(statuses.values()) - total)
    add_summary("Differenz Hauptkategorien zu Gesamt", sum(categories.values()) - total)
    summary.append(["Inkonsistenzen", len(issues), None,
                    "Siehe Blatt Inkonsistenzen" if issues else "Keine"])

    overview = workbook.create_sheet("EGID-Gesamtübersicht")
    overview.append(OVERVIEW_COLUMNS)
    missing = workbook.create_sheet("EGID-ohne-GVBSID")
    missing.append(MISSING_COLUMNS)
    for row in rows:
        overview.append([row[column] for column in OVERVIEW_COLUMNS])
        if row["Direkter GVBS-Adresskandidat vorhanden"] == "Nein" and row["Automatisch zugeordnet"] == "Nein":
            # Jede Adresse bleibt als eigene Zeile innerhalb der Zelle erhalten.
            addresses = row["_addresses"]
            detail = {
                **row,
                "Strasse": "\n".join(address[0] or "(fehlt)" for address in addresses),
                "Hausnummer": "\n".join(address[1] or "(fehlt)" for address in addresses),
                "PLZ": "\n".join(address[2] or "(fehlt)" for address in addresses),
                "Hinweis Hausnummernzusatz": row["Nur über Hausnummernzusatz erkannt"],
                "Zugehörige GVBSIDs über Hausnummernzusatz": "\n".join(row["_suffix_gvbsids"]),
            }
            missing.append([detail[column] for column in MISSING_COLUMNS])

    notes = workbook.create_sheet("Kategorien-Hinweise")
    notes.append(["Priorität", "Kategorie / Begriff", "Definition", "Einordnung"])
    definitions = {name: definition for name, definition, _ in gvbs.CATEGORIES}
    for priority, category in enumerate(CATEGORY_PRIORITY, start=1):
        definition = definitions.get(category, "Keine GVBSID führt diese EGID als direkten Adresskandidaten.")
        assignment = (
            "Automatisch nur bei tatsächlicher Zuordnung im Matching; die Priorität allein genügt nicht."
            if category in gvbs.AUTO_CATEGORIES
            else "Keine automatische Zuordnung aus dieser Kategorie."
        )
        notes.append([priority, category, definition, assignment])
    for term, definition, meaning in (
        ("EGID-Hauptkategorie",
         "Bei mehreren Kategorien direkter Kandidaten gilt die oben aufgeführte statistische Priorität.",
         "Jede EGID wird genau einmal bei ihrer Hauptkategorie gezählt. Die GVBSID-Matchingregeln bleiben unverändert."),
        ("Alle vorkommenden Matching-Kategorien",
         "Alle Kategorien der GVBSID-Zeilen, in denen diese EGID als direkter Kandidat "
         "oder als automatisch zugeordneter .1-Suffix-Kandidat vorkommt.",
         "Die Kategoriedefinitionen oben beschreiben diese GVBSID-Zeilen. Mehrere Beziehungen zählen dieselbe EGID nicht mehrfach."),
        (AUTOMATIC,
         "Das Matching hat diese EGID tatsächlich eingetragen und Automatische Zuordnung auf Ja gesetzt. "
         "Die Kategorie muss automatisch zuordnen; die EGID muss Teil des GWR-Bestands und direkter Kandidat "
         "oder der über die Kubatur-Paarregel zugeordnete .1-Suffix-Kandidat sein.",
         "Abdeckungszustand A. Mindestens eine gültige tatsächliche Zuordnung genügt, auch bei weiteren nicht automatisch zugeordneten Kandidatenbeziehungen."),
        (DIRECT_ONLY,
         "Mindestens eine GVBSID hat diese EGID als direkten Kandidaten; es liegt keine gültige automatische Zuordnung vor.",
         "Abdeckungszustand B. Zusammen mit A und C ergibt sich der gesamte EGID-Bestand."),
        (NO_CANDIDATE,
         "Die EGID besitzt weder einen direkten GVBS-Adresskandidaten noch eine automatische Zuordnung über die Kubatur-Paarregel.",
         "Abdeckungszustand C. Alle diese EGIDs stehen zusätzlich im Blatt EGID-ohne-GVBSID."),
        ("Nur über Hausnummernzusatz erkannt",
         "Die EGID wurde ausschliesslich als zusätzliche EGID über einen Hausnummernzusatz erkannt und besitzt keinen direkten Kandidaten.",
         "Teil von A bei automatischer Kubatur-Paarzuordnung, sonst Teilmenge von C; nicht zusätzlich zur Gesamtzahl addieren. "
         "Nicht zugeordnete Fälle stehen im Blatt EGID-ohne-GVBSID."),
        ("Gesamtzahl bestehender EGIDs",
         "Alle unterschiedlichen EGIDs aus GWR-building mit GSTAT = 1004, einschliesslich EGIDs ohne Adresse oder EGRID.",
         "Eine Zeile pro EGID. Sämtliche vorhandenen GWR-Adressen und EGRIDs werden vollständig ausgewiesen."),
        ("Kontrollsummen",
         "A + B + C und die Summe aller Hauptkategorien müssen jeweils der Gesamtzahl bestehender EGIDs entsprechen.",
         "Beide Kontrollen müssen OK und beide Differenzen zu Gesamt müssen 0 ergeben."),
        ("Inkonsistenzen",
         "Beispielsweise Kandidaten oder Zuordnungen ausserhalb des GWR-Bestands oder widersprüchliche Zuordnungskennzeichen.",
         "Separates Blatt Inkonsistenzen bei Auffälligkeiten. Die Anzahl der Hinweise ist keine zusätzliche EGID-Anzahl."),
    ):
        notes.append([None, term, definition, meaning])

    if issues:
        diagnostics = workbook.create_sheet("Inkonsistenzen")
        issue_columns = ("Art", "EGID", "GVBSID", "Bemerkung")
        diagnostics.append(issue_columns)
        for issue in issues:
            diagnostics.append([issue[column] for column in issue_columns])

    for sheet in workbook.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.row_dimensions[1].height = 36
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="17365D")
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for index, cell in enumerate(sheet[1], start=1):
            width = 65 if cell.value in ("Alle GWR-Adressen", "Bemerkung", "Auswertung") else 45
            sheet.column_dimensions[get_column_letter(index)].width = width
        for cells in sheet.iter_rows(min_row=2):
            for cell in cells:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    summary.column_dimensions["B"].width = 18
    summary.column_dimensions["C"].width = 22
    notes.column_dimensions["A"].width = 14
    notes.column_dimensions["B"].width = 55
    notes.column_dimensions["C"].width = 110
    notes.column_dimensions["D"].width = 85
    for cells in notes.iter_rows(min_row=2):
        color = gvbs.CATEGORY_COLORS.get(cells[1].value)
        if color:
            for cell in cells:
                cell.fill = PatternFill("solid", fgColor=color)
    for cells in summary.iter_rows(min_row=2):
        cells[2].number_format = "0.00%"
        color = gvbs.CATEGORY_COLORS.get(cells[0].value)
        if cells[0].value == "zuordnungskonflikt" and not cells[1].value:
            color = None
        if color:
            for cell in cells:
                cell.fill = PatternFill("solid", fgColor=color)
    category_column = OVERVIEW_COLUMNS.index("EGID-Hauptkategorie")
    for cells in overview.iter_rows(min_row=2):
        color = gvbs.CATEGORY_COLORS.get(cells[category_column].value)
        if color:
            for cell in cells:
                cell.fill = PatternFill("solid", fgColor=color)
    workbook.save(path)


def main():
    parser = argparse.ArgumentParser(description="Eigenständige EGID-Abdeckung des GWR-Bestands")
    parser.add_argument("--input", type=Path, help="GVBS-Eingabe; ohne diese Option Dateidialoge.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--gwr-db", type=Path, default=gvbs.DEFAULT_GWR_DB,
                        help="GWR-Datenbank des Kantons Basel-Stadt.")
    args = parser.parse_args()
    if args.input is None:
        try:
            selection = gvbs.select_files(None, args.output)
        except (ImportError, RuntimeError) as exc:
            parser.error(f"Dateidialog konnte nicht geöffnet werden: {exc}")
        if selection is None:
            print("Dateiauswahl abgebrochen; keine EGID-Auswertung erstellt.")
            return
        args.input, args.output = selection
    if args.output.resolve() in (args.input.resolve(), args.gwr_db.resolve()):
        parser.error("Ausgabe darf weder Eingabe noch GWR-Datenbank überschreiben.")
    addr_egids, egid_addresses, egid_grids, grid_egids = gvbs.read_gwr(args.gwr_db)
    existing_egids, all_addresses = read_egid_inventory(args.gwr_db)
    _, records = gvbs.read_excel(args.input)
    results = gvbs.match(records, addr_egids, egid_addresses, egid_grids, grid_egids,
                        postal_lookup=lambda addresses: gvbs.read_postal_candidates(args.gwr_db, addresses))
    rows, issues = analyze_coverage(existing_egids, results, all_addresses, egid_grids)
    save_coverage_excel(args.output, rows, issues)
    print(f"EGID-Abdeckung: {args.output.resolve()}")
    print(f"Bestehende EGIDs: {len(rows)}; Inkonsistenzen: {len(issues)}")


if __name__ == "__main__":
    main()

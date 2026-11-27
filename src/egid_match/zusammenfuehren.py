"""Automatische und manuelle EGID-Zuteilungen zu GVBSIDs zusammenführen."""

from pathlib import Path
from collections import Counter

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

from .common import egid_text, txt
from .matching import ASSIGNED_EGID_COLUMN, CATEGORIES, COLUMN_ALIASES, gvbsid_text, manual_egids


def _headers(sheet, required):
    headers = [txt(cell.value) for cell in sheet[1]]
    if len(headers) != len(set(headers)) or any(headers.count(name) != 1 for name in required):
        raise ValueError(f"Blatt {sheet.title}: fehlende oder doppelte Spalten; benötigt: {', '.join(required)}.")
    return {name: index for index, name in enumerate(headers)}


def _add(assignments, gvbsid, egid, source):
    if not gvbsid:
        raise ValueError("Eine Zuteilung hat keine GVBSID.")
    egid = egid_text(egid)
    previous = assignments.setdefault(gvbsid, {}).get(egid)
    if previous is not None and previous != source:
        raise ValueError(f"GVBSID {gvbsid}: EGID {egid} hat widersprüchliche Zuteilungsquellen.")
    assignments[gvbsid][egid] = source


def _summary_order(label):
    """Quellen nach Matching-Reihenfolge, Kombinationen an erster Quelle einordnen."""
    order = {name: index for index, (name, _, _) in enumerate(CATEGORIES)}
    if label == "Nicht zugeteilt":
        return (len(order) + 1, 0, label)
    sources = label.split(", ")
    ranks = [order.get("manuell_zugeteilt" if source == "manuell" else source, len(order))
             for source in sources]
    return (min(ranks), len(sources), label)


def merge_workbooks(original, matching, manual):
    """Ergänzt die Eingabearbeitsmappe und erstellt Übersicht und Zusammenfassung."""
    if "Matching" not in matching.sheetnames or "Zuordnungen" not in manual.sheetnames:
        raise ValueError("Benötigt werden das Blatt 'Matching' und das Blatt 'Zuordnungen' des Zuordnungsexports.")
    source = original.active
    input_headers = [txt(cell.value) for cell in source[1]]
    canonical = [COLUMN_ALIASES.get(name, name) for name in input_headers]
    if len(canonical) != len(set(canonical)) or any(canonical.count(name) != 1 for name in ("Kontrollnummer", "Gebäudenummer")):
        raise ValueError("Die Eingabe benötigt eindeutige Spalten Kontrollnummer und Gebäudenummer.")
    if any(name.casefold() in {sheet.casefold() for sheet in original.sheetnames}
           for name in ("Zuteileung_EGID_GVBS", "Zusammenfassung")):
        raise ValueError("Die Eingabe enthält bereits ein Ausgabe-Blatt 'Zuteileung_EGID_GVBS' oder 'Zusammenfassung'.")
    ids = {}
    source_rows = []
    for row in source.iter_rows(min_row=2):
        if not any(cell.value is not None for cell in row):
            continue
        control = txt(row[canonical.index("Kontrollnummer")].value)
        building = txt(row[canonical.index("Gebäudenummer")].value)
        source_rows.append((row[canonical.index("Kontrollnummer")].value,
                            row[canonical.index("Gebäudenummer")].value,
                            gvbsid_text((control, building)) if control and building else None))
        if not control or not building:
            if ASSIGNED_EGID_COLUMN in input_headers and txt(row[input_headers.index(ASSIGNED_EGID_COLUMN)].value):
                raise ValueError("Eine Zeile mit EGID zusammengeführt benötigt Kontrollnummer und Gebäudenummer.")
            continue
        gvbsid = gvbsid_text((control, building))
        if gvbsid in ids:
            raise ValueError(f"GVBSID {gvbsid} kommt in der Eingabe mehrfach vor.")
        ids[gvbsid] = row[0].row

    assignments = {}
    if ASSIGNED_EGID_COLUMN in input_headers:
        index = input_headers.index(ASSIGNED_EGID_COLUMN) + 1
        for gvbsid, row_number in ids.items():
            for egid in manual_egids(source.cell(row_number, index).value):
                _add(assignments, gvbsid, egid, "manuell")

    sheet = matching["Matching"]
    headers = _headers(sheet, ("GVBSID", "EGID", "Matching-Kategorie", "Automatische Zuordnung"))
    for row in sheet.iter_rows(min_row=2, values_only=True):
        gvbsid, egid, category, automatic = (txt(row[headers[name]]) for name in
            ("GVBSID", "EGID", "Matching-Kategorie", "Automatische Zuordnung"))
        if bool(egid) != (automatic == "Ja"):
            raise ValueError("Das Matching enthält eine widersprüchliche automatische Zuordnung.")
        if egid:
            if not category:
                raise ValueError("Bei einer automatischen Zuteilung fehlt die Matching-Kategorie.")
            _add(assignments, gvbsid, egid, category)

    sheet = manual["Zuordnungen"]
    headers = _headers(sheet, ("GVBSID", "EGID"))
    for row in sheet.iter_rows(min_row=2, values_only=True):
        gvbsid, egid = txt(row[headers["GVBSID"]]), txt(row[headers["EGID"]])
        if not gvbsid and not egid:
            continue
        if not gvbsid or not egid:
            raise ValueError("Eine manuelle Zuordnung enthält keine vollständige GVBSID-EGID-Beziehung.")
        _add(assignments, gvbsid, egid, "manuell")

    missing = set(assignments) - set(ids)
    if missing:
        raise ValueError("Zuteilungen enthalten GVBSIDs, die in der ursprünglichen Eingabe fehlen: " + ", ".join(sorted(missing)))
    output = original
    egid_col = input_headers.index(ASSIGNED_EGID_COLUMN) + 1 if ASSIGNED_EGID_COLUMN in input_headers else source.max_column + 1
    source.cell(1, egid_col, ASSIGNED_EGID_COLUMN)
    source_col = input_headers.index("zugeteilt aus") + 1 if "zugeteilt aus" in input_headers else source.max_column + 1
    source.cell(1, source_col, "zugeteilt aus")
    for gvbsid, row_number in ids.items():
        values = assignments.get(gvbsid, {})
        egids = sorted(values, key=int)
        source.cell(row_number, egid_col).value = ", ".join(egids) or None
        source.cell(row_number, source_col).value = ", ".join(values[egid] for egid in egids) or None
    result = output.create_sheet("Zuteileung_EGID_GVBS")
    result.append(["Kontrollnummer", "Gebäudenummer", "EGID_zusammengeführt", "EGID_zugeteil_aus"])
    counts = Counter()
    for control, building, gvbsid in source_rows:
        values = assignments.get(gvbsid, {})
        egids = sorted(values, key=int)
        sources = ", ".join(values[egid] for egid in egids)
        result.append([control, building, ", ".join(egids) or None,
                       sources or None])
        counts[sources or "Nicht zugeteilt"] += 1
    summary = output.create_sheet("Zusammenfassung")
    summary.append(["Zuteilungsquelle", "Anzahl", "Prozent", "Prozent kumuliert"])
    total = len(source_rows)
    cumulative = 0
    for label, count in sorted(counts.items(), key=lambda item: _summary_order(item[0])):
        cumulative += count
        summary.append([label, count, count / total, cumulative / total])
        for cell in summary[summary.max_row][2:]:
            cell.number_format = "0.00%"
    summary.append(["Gesamt", total, 1 if total else 0, None])
    summary.cell(summary.max_row, 3).number_format = "0.00%"
    for sheet in (result, summary):
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="17365D")
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 30
    return output


def select_files():
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    try:
        paths = []
        for title in ("Ursprüngliche GVBS-Eingabe auswählen", "Matching-Ausgabe auswählen", "Zuordnungsexport auswählen"):
            path = filedialog.askopenfilename(parent=root, title=title, filetypes=[("Excel-Arbeitsmappe", "*.xlsx")])
            if not path:
                return None
            paths.append(Path(path))
        output = filedialog.asksaveasfilename(parent=root, title="Zusammengeführte Ausgabe speichern",
            defaultextension=".xlsx", initialfile="gvbs_egid_zuteilungen.xlsx", confirmoverwrite=True,
            filetypes=[("Excel-Arbeitsmappe", "*.xlsx")])
        return (*paths, Path(output)) if output else None
    finally:
        root.destroy()


def main():
    selection = select_files()
    if selection is None:
        print("Abgebrochen; keine Ausgabe erstellt.")
        return
    *inputs, output = selection
    if any(path.suffix.lower() != ".xlsx" for path in (*inputs, output)):
        raise ValueError("Bitte ausschliesslich .xlsx-Dateien auswählen.")
    if output.resolve() in {path.resolve() for path in inputs}:
        raise ValueError("Die Ausgabe muss von allen Eingabedateien verschieden sein.")
    workbooks = []
    try:
        for index, path in enumerate(inputs):
            workbooks.append(load_workbook(path, read_only=index != 0, data_only=index != 0))
        merge_workbooks(*workbooks).save(output)
    finally:
        for workbook in workbooks:
            workbook.close()
    print(f"Zusammengeführte Ausgabe erstellt: {output}")


if __name__ == "__main__":
    main()

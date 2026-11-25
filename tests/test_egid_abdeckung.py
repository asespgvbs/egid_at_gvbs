"""EGID-Auswertung: ausschliesslich synthetische Daten im Arbeitsspeicher."""

import contextlib
import copy
import importlib.util
import io
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import ANY, Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import egid_match.matching as gvbs
import egid_match.abdeckung as coverage


def synthetic_inventory():
    """Alle zehn GVBS-Kategorien sowie EGIDs ohne vollständige Stammdaten."""
    street = "Synthetische Teststrasse"
    key = lambda number: gvbs.address(street, number, "0000")
    records = [{
        "Kontrollnummer": f"SYNTHETIC-{index}", "Gebäudenummer": "1",
        "Strasse": street, "Hausnummer": number, "Hausnummer Zusatz": None,
        "Postleitzahl": "0000",
    } for index, number in enumerate(("10", "20", "30", "30", "40", "42", "50", "60", "60", "70", "80", "90", ""))]
    addresses = {
        1: {key("10")}, 2: {key("20"), key("20a")}, 3: {key("30")},
        4: {key("40"), key("42")}, 5: {key("50")}, 6: {key("50")},
        7: {key("60")}, 8: {key("60")}, 9: {key("70")}, 10: {key("70.1")},
        11: {key("80")}, 13: {key("100"), key("102")},
        14: {(street, "", "0000")},
    }
    addr_egids = {}
    for egid, values in addresses.items():
        for value in values:
            if all(value):
                addr_egids.setdefault(value, set()).add(egid)
    grids = {egid: {f"SYNTHETIC-GRID-{egid}"} for egid in range(1, 15) if egid not in (11, 12)}
    grids[10] = set(grids[9])
    grids[13].add("SYNTHETIC-GRID-13-B")
    grid_egids = {}
    for egid, values in grids.items():
        for value in values:
            grid_egids.setdefault(value, set()).add(egid)
    return set(range(1, 15)), records, addr_egids, addresses, grids, grid_egids


def result(category, *, candidates="1", assigned=None, gvbsid="SYNTHETIC-1", suffix=""):
    return {
        "GVBSID": gvbsid, "Matching-Kategorie": category,
        "EGID-Kandidaten": candidates, "EGID": assigned,
        "Automatische Zuordnung": "Ja" if assigned is not None else "Nein",
        "EGID mit Hausnummernzusatz": suffix,
    }


class CoverageTests(unittest.TestCase):
    def analyze_fixture(self):
        inventory, records, addr_egids, addresses, grids, grid_egids = synthetic_inventory()
        matching = gvbs.match(records, addr_egids, addresses, grids, grid_egids)
        before = copy.deepcopy(matching)
        rows, issues = coverage.analyze_coverage(inventory, matching, addresses, grids)
        self.assertEqual(matching, before)
        return rows, issues, matching

    def test_all_categories_full_inventory_and_balances(self):
        rows, issues, matching = self.analyze_fixture()
        self.assertEqual(issues, [])
        self.assertEqual({row["Matching-Kategorie"] for row in matching},
                         {item[0] for item in gvbs.CATEGORIES}
                         - {gvbs.SUFFIX_PAIR_AUTO, gvbs.SUFFIX_PAIR_REVIEW, gvbs.SUFFIX_SINGLE_REVIEW,
                            "manuell_zugeteilt", "zuordnungskonflikt"})
        self.assertEqual(len(rows), 14)
        self.assertEqual({row["EGID"] for row in rows}, set(range(1, 15)))
        categories, statuses = coverage.summarize_coverage(rows)
        self.assertEqual(statuses[coverage.AUTOMATIC], 4)
        self.assertEqual(statuses[coverage.DIRECT_ONLY], 6)
        self.assertEqual(statuses[coverage.NO_CANDIDATE], 4)
        self.assertEqual(sum(statuses.values()), 14)
        self.assertEqual(sum(categories.values()), 14)
        self.assertEqual(categories[coverage.NO_DIRECT_MATCH], 4)
        by_id = {row["EGID"]: row for row in rows}
        self.assertEqual(by_id[12]["Anzahl GWR-Adressen"], 0)
        self.assertEqual(by_id[12]["EGRID"], "")
        self.assertEqual(by_id[14]["Anzahl GWR-Adressen"], 1)
        self.assertIn("unvollständig", by_id[14]["Bemerkung"])
        self.assertEqual(by_id[3]["Anzahl unterschiedlicher GVBSIDs"], 2)
        self.assertEqual(by_id[4]["Anzahl unterschiedlicher GVBSIDs"], 2)
        for egid, category in enumerate(coverage.CATEGORY_PRIORITY[:4], start=1):
            self.assertEqual(by_id[egid]["EGID-Hauptkategorie"], category)
            self.assertEqual(by_id[egid]["Automatisch zugeordnet"], "Ja")

    def test_suffix_only_stays_without_direct_candidate(self):
        rows, _, _ = self.analyze_fixture()
        suffix = next(row for row in rows if row["EGID"] == 10)
        self.assertEqual(suffix["Nur über Hausnummernzusatz erkannt"], "Ja")
        self.assertEqual(suffix["Direkter GVBS-Adresskandidat vorhanden"], "Nein")
        self.assertEqual(suffix["Automatisch zugeordnet"], "Nein")
        self.assertEqual(suffix["EGID-Hauptkategorie"], coverage.NO_DIRECT_MATCH)
        self.assertEqual(len(suffix["_suffix_gvbsids"]), 1)

    def test_all_four_automatic_categories_use_actual_assignments(self):
        for category in gvbs.AUTO_CATEGORIES:
            with self.subTest(category=category):
                rows, issues = coverage.analyze_coverage({1}, [result(category, assigned=1)], {}, {})
                self.assertEqual(rows[0]["Automatisch zugeordnet"], "Ja")
                self.assertEqual(issues, [])
                rows, issues = coverage.analyze_coverage({1}, [result(category)], {}, {})
                self.assertEqual(rows[0]["Automatisch zugeordnet"], "Nein")
                self.assertEqual(issues, [])

    def test_multiple_categories_and_repeated_gvbsids_count_egid_once(self):
        results = [
            result("review_address_suffix", gvbsid="SYNTHETIC-2"),
            result("multiple_egid", gvbsid="SYNTHETIC-3"),
            result("perfect_match", assigned=1),
            result("perfect_match", assigned=1),
        ]
        rows, issues = coverage.analyze_coverage({1, 1}, results, {}, {})
        self.assertEqual(issues, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["EGID-Hauptkategorie"], "perfect_match")
        self.assertEqual(rows[0]["Alle vorkommenden Matching-Kategorien"], "perfect_match\nmultiple_egid\nreview_address_suffix")
        self.assertEqual(rows[0]["Anzahl unterschiedlicher GVBSIDs"], 3)
        self.assertEqual(coverage.summarize_coverage(rows)[1][coverage.AUTOMATIC], 1)

    def test_statistical_priority_does_not_create_assignments(self):
        for first, second in zip(coverage.CATEGORY_PRIORITY[:-2], coverage.CATEGORY_PRIORITY[1:-1]):
            with self.subTest(first=first, second=second):
                rows, _ = coverage.analyze_coverage({1}, [result(second), result(first)], {}, {})
                self.assertEqual(rows[0]["EGID-Hauptkategorie"], first)
                self.assertEqual(rows[0]["Automatisch zugeordnet"], "Nein")

    def test_direct_candidate_is_not_marked_as_suffix_only(self):
        rows, issues = coverage.analyze_coverage({1, 2}, [
            result("review_address_suffix", suffix="2"),
            result("super_match", candidates="2", assigned=2, gvbsid="SYNTHETIC-2"),
        ], {}, {})
        self.assertEqual(issues, [])
        row = next(row for row in rows if row["EGID"] == 2)
        self.assertEqual(row["Nur über Hausnummernzusatz erkannt"], "Nein")
        self.assertEqual(row["Automatisch zugeordnet"], "Ja")

    def test_external_candidates_and_assignments_are_reported_separately(self):
        rows, issues = coverage.analyze_coverage({1}, [
            result("perfect_match", candidates="999", assigned=999, suffix="998"),
        ], {}, {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Direkter GVBS-Adresskandidat vorhanden"], "Nein")
        self.assertEqual(len(issues), 3)
        self.assertEqual({issue["Art"] for issue in issues}, {
            "Kandidat ausserhalb GWR-Bestand", "Zuordnung ausserhalb GWR-Bestand",
            "Hausnummernzusatz ausserhalb GWR-Bestand",
        })

    def test_inconsistent_assignment_flags_are_reported(self):
        bad_flag = result("perfect_match", assigned=1)
        bad_flag["Automatische Zuordnung"] = "Nein"
        for invalid in (bad_flag, result("multiple_egid", assigned=1), result("perfect_match", candidates="2", assigned=1)):
            with self.subTest(invalid=invalid):
                rows, issues = coverage.analyze_coverage({1, 2}, [invalid], {}, {})
                self.assertTrue(issues)
                self.assertTrue(all(row["Automatisch zugeordnet"] == "Nein" for row in rows))

    def test_duplicate_overview_rows_are_rejected(self):
        rows, _ = coverage.analyze_coverage({1}, [], {}, {})
        with self.assertRaisesRegex(ValueError, "mehrfach"):
            coverage.summarize_coverage(rows + rows)


class InventoryTests(unittest.TestCase):
    def test_complete_inventory_query_with_synthetic_in_memory_database(self):
        # Diese Datenbank wird hier vollständig synthetisch im Speicher erstellt.
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE building (EGID INTEGER, GSTAT INTEGER, EGRID TEXT)")
        connection.execute("CREATE TABLE entrance (EGID INTEGER, STRNAME TEXT, DEINR TEXT, DPLZ4 TEXT)")
        connection.executemany("INSERT INTO building VALUES (?, ?, ?)", [
            (1, 1004, "SYNTHETIC-GRID"), (1, 1004, "SYNTHETIC-GRID"),
            (2, 1004, None), (3, 1005, None), (4, 1004, None), (None, 1004, None),
        ])
        connection.executemany("INSERT INTO entrance VALUES (?, ?, ?, ?)", [
            (1, "Synthetische Teststrasse", "10", "0000"),
            (1, "Synthetische Teststrasse", "12", "0000"),
            (3, "Synthetische Teststrasse", "30", "0000"),
            (4, "Synthetische Teststrasse", None, "0000"),
        ])
        try:
            with patch.object(Path, "is_file", return_value=True), patch.object(coverage.sqlite3, "connect", return_value=connection) as connect:
                egids, addresses = coverage.read_egid_inventory(Path("synthetic/gwr.sqlite"))
            self.assertEqual(egids, {1, 2, 4})
            self.assertEqual(len(addresses[1]), 2)
            self.assertNotIn(2, addresses)
            self.assertEqual(addresses[4], {("Synthetische Teststrasse", "", "0000")})
            self.assertTrue(connect.call_args.args[0].endswith("?mode=ro"))
            self.assertTrue(connect.call_args.kwargs["uri"])
        finally:
            connection.close()

    def test_inventory_connection_closes_after_query_error(self):
        connection = Mock()
        connection.execute.side_effect = sqlite3.OperationalError("synthetischer Fehler")
        with patch.object(Path, "is_file", return_value=True), patch.object(coverage.sqlite3, "connect", return_value=connection):
            with self.assertRaises(sqlite3.OperationalError):
                coverage.read_egid_inventory(Path("synthetic/gwr.sqlite"))
        connection.close.assert_called_once()


class WorkbookTests(unittest.TestCase):
    def make_workbook(self, rows, issues):
        workbook = coverage.Workbook()
        with patch.object(coverage, "Workbook", return_value=workbook), patch.object(workbook, "save") as save:
            coverage.save_coverage_excel(Path("synthetic/coverage.xlsx"), rows, issues)
        save.assert_called_once_with(Path("synthetic/coverage.xlsx"))
        self.addCleanup(workbook.close)
        return workbook

    def test_sheets_balances_all_addresses_suffix_relations_and_category_notes(self):
        inventory, records, addr_egids, addresses, grids, grid_egids = synthetic_inventory()
        matching = gvbs.match(records, addr_egids, addresses, grids, grid_egids)
        rows, issues = coverage.analyze_coverage(inventory, matching, addresses, grids)
        workbook = self.make_workbook(rows, issues)
        self.assertEqual(workbook.sheetnames, ["EGID-Zusammenfassung", "EGID-Gesamtübersicht", "EGID-ohne-GVBSID", "Kategorien-Hinweise"])
        summary = {row[0]: row[1:] for row in list(workbook.worksheets[0].values)[1:]}
        self.assertEqual(summary["Gesamtzahl bestehender EGIDs"][:2], (14, 1))
        self.assertEqual(summary[coverage.AUTOMATIC][0], 4)
        self.assertEqual(summary[coverage.DIRECT_ONLY][0], 6)
        self.assertEqual(summary[coverage.NO_CANDIDATE][0], 4)
        self.assertEqual(summary["Nur über Hausnummernzusatz erkannt"][0], 1)
        self.assertEqual(summary["Kontrollsumme Abdeckungsstatus"], (14, 1, "OK"))
        self.assertEqual(summary["Kontrollsumme Hauptkategorien"], (14, 1, "OK"))
        self.assertEqual(summary["Differenz Abdeckungsstatus zu Gesamt"][0], 0)
        self.assertEqual(workbook.worksheets[1].max_row, 15)
        missing = {row[0]: row for row in list(workbook.worksheets[2].values)[1:]}
        self.assertEqual(set(missing), {10, 12, 13, 14})
        self.assertEqual(missing[13][3], 2)
        self.assertEqual(missing[13][5], "100\n102")
        self.assertIn("100", missing[13][2])
        self.assertIn("102", missing[13][2])
        self.assertEqual(missing[13][1], "SYNTHETIC-GRID-13\nSYNTHETIC-GRID-13-B")
        self.assertEqual(missing[10][7], "Ja")
        self.assertTrue(missing[10][8].startswith("SYNTHETIC-"))
        self.assertEqual(missing[14][5], "(fehlt)")
        for sheet in workbook.worksheets:
            self.assertEqual(sheet.freeze_panes, "A2")
            self.assertEqual(sheet.auto_filter.ref, sheet.dimensions)
        self.assertEqual(workbook.worksheets[0]["C2"].number_format, "0.00%")
        notes = list(workbook["Kategorien-Hinweise"].values)
        category_notes = notes[1:1 + len(coverage.CATEGORY_PRIORITY)]
        self.assertEqual([row[0] for row in category_notes], list(range(1, 1 + len(coverage.CATEGORY_PRIORITY))))
        self.assertEqual([row[1] for row in category_notes], list(coverage.CATEGORY_PRIORITY))
        automatic_notes = [row for row in category_notes if row[1] in gvbs.AUTO_CATEGORIES]
        self.assertEqual(len(automatic_notes), len(gvbs.AUTO_CATEGORIES))
        self.assertTrue(all("tatsächlicher Zuordnung" in row[3] for row in automatic_notes))
        explanations = {row[1]: row[2:] for row in notes[1 + len(coverage.CATEGORY_PRIORITY):]}
        self.assertIn("Teilmenge von C", explanations["Nur über Hausnummernzusatz erkannt"][1])
        self.assertIn("A + B + C", explanations["Kontrollsummen"][0])
        self.assertEqual(workbook["Kategorien-Hinweise"]["B2"].fill.fgColor.rgb, "00E2F0D9")

    def test_empty_inventory_creates_headers_and_zero_percentages(self):
        workbook = self.make_workbook([], [])
        self.assertEqual(workbook.worksheets[1].max_row, 1)
        self.assertEqual(workbook.worksheets[2].max_row, 1)
        self.assertIn("Kategorien-Hinweise", workbook.sheetnames)
        for row in list(workbook.worksheets[0].values)[1:-1]:
            self.assertEqual(row[1], 0)
            self.assertEqual(row[2], 0)

    def test_inconsistencies_have_separate_sheet_and_do_not_change_totals(self):
        rows, issues = coverage.analyze_coverage({1}, [result("perfect_match", candidates="999", assigned=999)], {}, {})
        workbook = self.make_workbook(rows, issues)
        self.assertEqual(workbook.sheetnames[-1], "Inkonsistenzen")
        self.assertEqual(workbook["Inkonsistenzen"].max_row, 3)
        self.assertEqual(workbook["EGID-Gesamtübersicht"].max_row, 2)


class EntrypointTests(unittest.TestCase):
    def test_imports_do_not_trigger_dialogs_data_reads_or_exports(self):
        import tkinter
        for name in ("matching", "abdeckung"):
            filename = ROOT / "src" / "egid_match" / (name + ".py")
            with self.subTest(filename=filename), patch.object(sqlite3, "connect") as database, patch.object(gvbs, "load_workbook") as read, patch("openpyxl.load_workbook") as external_read, patch("openpyxl.workbook.workbook.Workbook.save") as save, patch.object(tkinter, "Tk") as dialog:
                spec = importlib.util.spec_from_file_location("egid_match.synthetic_" + name, filename)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                database.assert_not_called()
                read.assert_not_called()
                external_read.assert_not_called()
                save.assert_not_called()
                dialog.assert_not_called()

    def test_both_scripts_have_independent_help_entrypoints(self):
        for module in (gvbs, coverage):
            with self.subTest(module=module.__name__), patch.object(sys, "argv", [module.__name__, "--help"]), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit_result:
                module.main()
            self.assertEqual(exit_result.exception.code, 0)

    def test_coverage_runs_without_gvbs_export_or_previous_excel(self):
        inventory, records, addr_egids, addresses, grids, grid_egids = synthetic_inventory()
        with patch.object(sys, "argv", ["egid-abdeckung", "--input", "synthetic/input.xlsx", "--output", "synthetic/coverage.xlsx"]), patch.object(gvbs, "select_files") as select, patch.object(gvbs, "read_gwr", return_value=(addr_egids, addresses, grids, grid_egids)), patch.object(gvbs, "read_postal_candidates", return_value={}), patch.object(coverage, "read_egid_inventory", return_value=(inventory, addresses)), patch.object(gvbs, "read_excel", return_value=(list(gvbs.REQUIRED), records)) as read, patch.object(gvbs, "match", wraps=gvbs.match) as matching, patch.object(gvbs, "save_excel") as old_export, patch.object(coverage, "save_coverage_excel") as new_export, contextlib.redirect_stdout(io.StringIO()):
            coverage.main()
        select.assert_not_called()
        read.assert_called_once_with(Path("synthetic/input.xlsx"))
        matching.assert_called_once_with(records, addr_egids, addresses, grids, grid_egids, postal_lookup=ANY)
        old_export.assert_not_called()
        self.assertEqual(new_export.call_args.args[0], Path("synthetic/coverage.xlsx"))
        self.assertEqual(len(new_export.call_args.args[1]), 14)

    def test_cancel_coverage_dialog_does_not_access_data(self):
        with patch.object(sys, "argv", ["egid-abdeckung"]), patch.object(gvbs, "select_files", return_value=None) as select, patch.object(gvbs, "read_gwr") as read, patch.object(coverage, "read_egid_inventory") as inventory, patch.object(gvbs, "read_excel") as excel, patch.object(coverage, "save_coverage_excel") as export, contextlib.redirect_stdout(io.StringIO()):
            coverage.main()
        select.assert_called_once_with(None, Path("egid_abdeckung.xlsx"))
        read.assert_not_called()
        inventory.assert_not_called()
        excel.assert_not_called()
        export.assert_not_called()

    def test_identical_input_output_stops_before_data_access(self):
        with patch.object(sys, "argv", ["egid-abdeckung", "--input", "synthetic/same.xlsx", "--output", "synthetic/same.xlsx"]), patch.object(gvbs, "read_gwr") as read, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            coverage.main()
        self.assertEqual(error.exception.code, 2)
        read.assert_not_called()


if __name__ == "__main__":
    unittest.main()

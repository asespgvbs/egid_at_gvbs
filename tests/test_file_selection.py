"""Dialogtests mit simulierten Auswahlen und vollständig synthetischen Daten."""

import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from egid_match import matching as app

SCRIPT = ROOT / "src" / "egid_match" / "matching.py"


class FileSelectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Mock()
        self.tk_patch = patch("tkinter.Tk", return_value=self.root)
        self.tk_patch.start()
        self.addCleanup(self.tk_patch.stop)

    def test_select_input_and_output(self):
        with (
            patch("tkinter.filedialog.askopenfilename", return_value="synthetic/input.xlsx"),
            patch("tkinter.filedialog.asksaveasfilename", return_value="synthetic/result.xlsx") as save,
        ):
            paths = app.select_files(None, app.DEFAULT_OUTPUT)
        self.assertEqual(paths, (Path("synthetic/input.xlsx"), Path("synthetic/result.xlsx")))
        self.assertEqual(save.call_args.kwargs["defaultextension"], ".xlsx")
        self.assertTrue(save.call_args.kwargs["confirmoverwrite"])
        self.root.withdraw.assert_called_once()
        self.root.destroy.assert_called_once()

    def test_cancel_input_skips_output_dialog(self):
        with (
            patch("tkinter.filedialog.askopenfilename", return_value=""),
            patch("tkinter.filedialog.asksaveasfilename") as save,
        ):
            self.assertIsNone(app.select_files(None, app.DEFAULT_OUTPUT))
        save.assert_not_called()
        self.root.destroy.assert_called_once()

    def test_cancel_output_discards_selected_input(self):
        with (
            patch("tkinter.filedialog.askopenfilename", return_value="synthetic/selected.xlsx"),
            patch("tkinter.filedialog.asksaveasfilename", return_value=""),
        ):
            self.assertIsNone(app.select_files(None, app.DEFAULT_OUTPUT))
        self.root.destroy.assert_called_once()

    def test_dialog_error_destroys_window(self):
        import tkinter

        with patch("tkinter.filedialog.askopenfilename", side_effect=tkinter.TclError("synthetic error")):
            with self.assertRaisesRegex(RuntimeError, "synthetic error"):
                app.select_files(None, app.DEFAULT_OUTPUT)
        self.root.destroy.assert_called_once()


class MainSelectionTests(unittest.TestCase):
    def setUp(self):
        # Alle Datei-/Datenbankzugriffe sind ersetzt, auch beim Fehlerfall.
        patches = {
            "read_gwr": patch.object(app, "read_gwr", return_value=({}, {}, {}, {})),
            "read_excel": patch.object(app, "read_excel", return_value=(list(app.REQUIRED), [{
                "Kontrollnummer": "SYNTHETIC-1",
                "Gebäudenummer": "1",
                "Strasse": "Synthetische Teststrasse",
                "Hausnummer": "1",
                "Hausnummer Zusatz": None,
                "Postleitzahl": "0000",
            }])),
            "save_excel": patch.object(app, "save_excel"),
        }
        self.mocks = {}
        for name, patcher in patches.items():
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, arguments, selected):
        with (
            patch.object(sys, "argv", [str(SCRIPT), *arguments]),
            patch.object(app, "select_files", return_value=selected),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            app.main()

    def test_normal_start_uses_both_selected_paths(self):
        self.run_main([], (Path("synthetic/input.xlsx"), Path("synthetic/result.xlsx")))
        self.mocks["read_excel"].assert_called_once_with(Path("synthetic/input.xlsx"))
        self.assertEqual(self.mocks["save_excel"].call_args.args[0], Path("synthetic/result.xlsx"))

    def test_cancel_uses_previous_input_and_test_output_in_previous_folder(self):
        self.run_main([
            "--input", "synthetic/previous.xlsx",
            "--output", "synthetic/output/previous_result.xlsx",
        ], None)
        self.mocks["read_excel"].assert_called_once_with(Path("synthetic/previous.xlsx"))
        self.assertEqual(
            self.mocks["save_excel"].call_args.args[0],
            Path("synthetic/output/gebaeude_egid_matching_TEST.xlsx"),
        )

    def test_cancel_without_output_option_uses_test_name(self):
        self.run_main(["--input", "synthetic/previous.xlsx"], None)
        self.assertEqual(self.mocks["save_excel"].call_args.args[0], Path(app.TEST_OUTPUT_NAME))

    def test_cancel_without_arguments_uses_default_test_input(self):
        self.run_main([], None)
        expected_input = Path.cwd() / "data" / "test_match_data.xlsx"
        self.mocks["read_excel"].assert_called_once_with(expected_input)
        self.assertEqual(self.mocks["save_excel"].call_args.args[0], Path(app.TEST_OUTPUT_NAME))

    def test_same_input_and_output_stops_before_reading_data(self):
        with self.assertRaises(SystemExit) as error:
            self.run_main([], (Path("synthetic/same.xlsx"), Path("synthetic/same.xlsx")))
        self.assertEqual(error.exception.code, 2)
        self.mocks["read_gwr"].assert_not_called()
        self.mocks["read_excel"].assert_not_called()
        self.mocks["save_excel"].assert_not_called()


class InputColumnTests(unittest.TestCase):
    def read_synthetic_workbook(self, headers, values=None):
        if values is None:
            synthetic_values = {
                "Kontrollnummer": "SYNTHETIC-1",
                "Gebäudenummer": "7",
                "Strasse": "Synthetische Teststrasse",
                "Hausnummer": "12",
                "Hausnummer Zusatz": None,
                "Postleitzahl": "0000",
            }
            values = [synthetic_values.get(app.COLUMN_ALIASES.get(column, column)) for column in headers]
        workbook = Mock()
        workbook.active.iter_rows.return_value = iter([
            headers,
            values,
        ])
        with patch.object(app, "load_workbook", return_value=workbook):
            return app.read_excel(Path("synthetic/input.xlsx"))

    def test_new_and_legacy_headers_produce_same_matching_result(self):
        new_headers = ["Kontrollnummer", "Gebäudenummer", "Strasse", "Hausnummer", "Hausnummer Zusatz", "Postleitzahl"]
        previous_headers = ["Kontrollnummer", "Gebäudenummer", "Strassennamen", "Hausnummer", "PLZ"]
        legacy_headers = ["Kontrollnummer", "Gebäude (Nr.)", "Strasse", "Nr.", "PLZ"]
        key = app.address("Synthetische Teststrasse", "12", "0000")
        for headers in (new_headers, previous_headers, legacy_headers):
            with self.subTest(headers=headers):
                imported_headers, records = self.read_synthetic_workbook(headers)
                self.assertEqual(imported_headers, headers)
                results = app.match(
                    records,
                    {key: {900000001}},
                    {900000001: {key}},
                    {900000001: {"SYNTHETIC-EGRID"}},
                    {"SYNTHETIC-EGRID": {900000001}},
                )
                self.assertEqual(results[0]["GVBSID"], "SYNTHETIC-1-7")
                self.assertEqual(results[0]["EGID"], 900000001)
                self.assertEqual(results[0]["Matching-Kategorie"], "perfect_match")

    def test_house_number_suffix_is_used_and_import_values_are_preserved(self):
        headers = [*app.REQUIRED, "Zusätzliche Spalte"]
        for suffix, full_number in ((" A ", "12a"), (".1", "12.1"), (None, "12")):
            with self.subTest(suffix=suffix):
                values = ["SYNTHETIC-1", "7", "Synthetische Teststrasse", 12.0, suffix, "0000", "Originalwert"]
                imported_headers, records = self.read_synthetic_workbook(headers, values)
                key = app.address("Synthetische Teststrasse", full_number, "0000")
                results = app.match(
                    records,
                    {key: {900000001}},
                    {900000001: {key}},
                    {900000001: {"SYNTHETIC-EGRID"}},
                    {"SYNTHETIC-EGRID": {900000001}},
                )
                self.assertEqual(imported_headers, headers)
                self.assertEqual(list(records[0].values()), values)
                self.assertEqual(results[0]["EGID"], 900000001)
                self.assertEqual(results[0]["Hausnummer Zusatz"], suffix)
                self.assertEqual(results[0]["Zusätzliche Spalte"], "Originalwert")

    def test_suffix_without_house_number_is_invalid(self):
        _, records = self.read_synthetic_workbook(
            list(app.REQUIRED),
            ["SYNTHETIC-1", "7", "Synthetische Teststrasse", None, "a", "0000"],
        )
        results = app.match(records, {}, {}, {}, {})
        self.assertEqual(results[0]["Matching-Kategorie"], "invalid_input")
        self.assertIsNone(results[0]["EGID"])

    def test_missing_column_reports_new_name(self):
        with self.assertRaisesRegex(ValueError, "Fehlende Spalten:.*Hausnummer"):
            self.read_synthetic_workbook([
                "Kontrollnummer", "Gebäudenummer", "Strassennamen", "Andere Spalte", "PLZ",
            ])

    def test_ambiguous_legacy_and_new_column_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Doppelte Spaltennamen"):
            self.read_synthetic_workbook([
                "Kontrollnummer", "Gebäudenummer", "Strassennamen", "Hausnummer", "PLZ", "Nr.",
            ])


def synthetic_assignment_case(numbers, candidates_by_number, *, missing_grid=False, suffix_conflict=False):
    """Vollständig synthetische Zuordnung ohne Datei- oder Datenbankzugriff."""
    records = [{
        "Kontrollnummer": f"SYNTHETIC-{index}",
        "Gebäudenummer": "1",
        "Strasse": "Synthetische Teststrasse",
        "Hausnummer": number,
        "Hausnummer Zusatz": None,
        "Postleitzahl": "0000",
    } for index, number in enumerate(numbers)]
    addr_egids = {}
    egid_addresses = {}
    egid_grids = {}
    grid_egids = {}
    for number, candidates in candidates_by_number.items():
        key = app.address("Synthetische Teststrasse", number, "0000")
        addr_egids[key] = set(candidates)
        for egid in candidates:
            grid = f"SYNTHETIC-EGRID-{egid}"
            egid_addresses.setdefault(egid, set()).add(key)
            egid_grids[egid] = {grid}
            grid_egids[grid] = {egid}
    if missing_grid:
        egid_grids.clear()
        grid_egids.clear()
    if suffix_conflict:
        suffix_egid = 900000099
        suffix_key = app.address("Synthetische Teststrasse", "10a", "0000")
        addr_egids[suffix_key] = {suffix_egid}
        egid_addresses[suffix_egid] = {suffix_key}
        egid_grids[suffix_egid] = set(egid_grids[900000001])
        for grid in egid_grids[suffix_egid]:
            grid_egids[grid].add(suffix_egid)
    return records, app.match(records, addr_egids, egid_addresses, egid_grids, grid_egids)


class MultipleGvbsAssignmentTests(unittest.TestCase):
    def test_same_address_assigns_egid_to_all_gvbsids(self):
        _, results = synthetic_assignment_case(["10", "10"], {"10": {900000001}})
        self.assertEqual([row["Matching-Kategorie"] for row in results], [
            "oneEgid_oneAddress_multipleGVBSIDs",
            "oneEgid_oneAddress_multipleGVBSIDs",
        ])
        self.assertEqual([row["EGID"] for row in results], [900000001, 900000001])
        self.assertTrue(all(row["Automatische Zuordnung"] == "Ja" for row in results))

    def test_different_addresses_and_mixed_cases_assign_egid_to_all_gvbsids(self):
        for numbers in (["10", "12"], ["10", "10", "12"]):
            with self.subTest(numbers=numbers):
                _, results = synthetic_assignment_case(numbers, {"10": {900000001}, "12": {900000001}})
                self.assertTrue(all(row["Matching-Kategorie"] == "oneEgid_multipleAddresses_multipleGVBSIDs" for row in results))
                self.assertTrue(all(row["EGID"] == 900000001 for row in results))
                self.assertTrue(all(row["Automatische Zuordnung"] == "Ja" for row in results))

    def test_ambiguous_candidates_remain_unassigned(self):
        for numbers, category in ((["10"], "multiple_egid"), (["10", "10"], "multiple_gvbsid_multiple_egid")):
            with self.subTest(category=category):
                _, results = synthetic_assignment_case(numbers, {"10": {900000001, 900000002}})
                self.assertTrue(all(row["Matching-Kategorie"] == category for row in results))
                self.assertTrue(all(row["EGID"] is None for row in results))
                self.assertTrue(all(row["Automatische Zuordnung"] == "Nein" for row in results))


class CategoryPriorityTests(unittest.TestCase):
    def test_original_categories_and_their_automatic_assignments(self):
        cases = [
            ([""], {}, {}, "invalid_input", False),
            (["99"], {}, {}, "no_match", False),
            (["10"], {"10": {900000001, 900000002}}, {}, "multiple_egid", False),
            (["10", "10"], {"10": {900000001, 900000002}}, {}, "multiple_gvbsid_multiple_egid", False),
            (["10"], {"10": {900000001}}, {"missing_grid": True}, "invalid_gwr_data", False),
            (["10"], {"10": {900000001}}, {"suffix_conflict": True}, "review_address_suffix", False),
            (["10"], {"10": {900000001}}, {}, "perfect_match", True),
            (["10"], {"10": {900000001}, "12": {900000001}}, {}, "super_match", True),
            (["10", "10"], {"10": {900000001}}, {}, "oneEgid_oneAddress_multipleGVBSIDs", True),
            (["10", "12"], {"10": {900000001}, "12": {900000001}}, {}, "oneEgid_multipleAddresses_multipleGVBSIDs", True),
        ]
        for numbers, candidates, options, category, automatic in cases:
            with self.subTest(category=category):
                _, results = synthetic_assignment_case(numbers, candidates, **options)
                self.assertEqual(len(results), len(numbers))
                for result in results:
                    self.assertEqual(result["Matching-Kategorie"], category)
                    self.assertEqual(result["EGID"], 900000001 if automatic else None)
                    self.assertEqual(result["Automatische Zuordnung"], "Ja" if automatic else "Nein")
        self.assertEqual(app.AUTO_CATEGORIES - {app.SUFFIX_PAIR_AUTO}, {case[3] for case in cases if case[4]})
        self.assertEqual({case[3] for case in cases},
                         {name for name, _, _ in app.CATEGORIES} - {app.SUFFIX_PAIR_AUTO, app.SUFFIX_PAIR_REVIEW})

    def test_missing_grid_precedes_both_multiple_gvbs_categories(self):
        for numbers in (["10", "10"], ["10", "12"], ["10", "10", "12"]):
            with self.subTest(numbers=numbers):
                _, results = synthetic_assignment_case(
                    numbers, {"10": {900000001}, "12": {900000001}}, missing_grid=True,
                )
                self.assertTrue(all(row["Matching-Kategorie"] == "invalid_gwr_data" for row in results))
                self.assertTrue(all(row["EGID"] is None for row in results))
                self.assertTrue(all(row["Automatische Zuordnung"] == "Nein" for row in results))

    def test_suffix_conflict_precedes_both_multiple_gvbs_categories_per_row(self):
        for numbers in (["10", "10"], ["10", "12"], ["10", "10", "12"]):
            with self.subTest(numbers=numbers):
                _, results = synthetic_assignment_case(
                    numbers, {"10": {900000001}, "12": {900000001}}, suffix_conflict=True,
                )
                for number, result in zip(numbers, results, strict=True):
                    if number == "10":
                        self.assertEqual(result["Matching-Kategorie"], "review_address_suffix")
                        self.assertIsNone(result["EGID"])
                        self.assertEqual(result["Automatische Zuordnung"], "Nein")
                        self.assertEqual(result["Anzahl EGID mit Hausnummernzusatz"], 1)
                    else:
                        self.assertEqual(result["Matching-Kategorie"], "oneEgid_multipleAddresses_multipleGVBSIDs")
                        self.assertEqual(result["EGID"], 900000001)
                        self.assertEqual(result["Automatische Zuordnung"], "Ja")

    def test_ambiguous_candidates_precede_missing_grid(self):
        for numbers, expected in ((["10"], "multiple_egid"), (["10", "10"], "multiple_gvbsid_multiple_egid")):
            with self.subTest(numbers=numbers):
                _, results = synthetic_assignment_case(
                    numbers, {"10": {900000001, 900000002}}, missing_grid=True,
                )
                self.assertTrue(all(row["Matching-Kategorie"] == expected for row in results))
                self.assertTrue(all(row["EGID"] is None for row in results))

    def test_suffix_address_with_own_gvbsid_allows_automatic_assignment(self):
        _, results = synthetic_assignment_case(
            ["10", "10", "10a"], {"10": {900000001}, "10a": {900000099}}, suffix_conflict=True,
        )
        self.assertEqual([row["Matching-Kategorie"] for row in results], [
            "oneEgid_oneAddress_multipleGVBSIDs", "oneEgid_oneAddress_multipleGVBSIDs", "super_match",
        ])
        self.assertEqual([row["EGID"] for row in results], [900000001, 900000001, 900000099])
        self.assertTrue(all(row["Automatische Zuordnung"] == "Ja" for row in results))


class OutputWorkbookTests(unittest.TestCase):
    def create_output(self, headers, records, results):
        # Nur Arbeitsmappen im Speicher; auch keine temporären Excel-Dateien.
        workbook = app.Workbook()
        with (
            patch.object(app, "Workbook", return_value=workbook),
            patch.object(workbook, "save") as save,
        ):
            app.save_excel(Path("synthetic/output.xlsx"), headers, results, records)
        save.assert_called_once_with(Path("synthetic/output.xlsx"))
        return workbook

    def test_multiple_gvbs_assignments_reach_output_sheets_and_totals(self):
        records, results = synthetic_assignment_case(
            ["10", "10", "20", "22", "99"],
            {"10": {900000001}, "20": {900000002}, "22": {900000002}},
        )
        workbook = self.create_output(list(app.REQUIRED), records, results)
        self.addCleanup(workbook.close)
        expected_egids = [900000001, 900000001, 900000002, 900000002, None]
        for sheet_name in ("Matching", "Ergebnis"):
            rows = list(workbook[sheet_name].values)
            column = rows[0].index("EGID")
            self.assertEqual([row[column] for row in rows[1:]], expected_egids)
        overview = {row[0]: row[1:] for row in list(workbook["Zusammenfassung"].values)[1:]}
        self.assertEqual(overview["Gesamt"], (5, 1, None))
        self.assertEqual(overview["Automatisch zugeordnet"], (4, 0.8, None))
        self.assertEqual(overview["Nicht automatisch zugeordnet"], (1, 0.2, None))
        self.assertEqual(overview["oneEgid_oneAddress_multipleGVBSIDs"], (2, 0.4, 0.4))
        self.assertEqual(overview["oneEgid_multipleAddresses_multipleGVBSIDs"], (2, 0.4, 0.8))
        for category, egid in (("oneEgid_oneAddress_multipleGVBSIDs", 900000001),
                               ("oneEgid_multipleAddresses_multipleGVBSIDs", 900000002)):
            sheet = workbook[app.CATEGORY_SHEET_TITLES[category]]
            rows = list(sheet.values)
            column = rows[0].index("EGID")
            self.assertEqual([row[column] for row in rows[1:]], [egid, egid])
        notes = {row[0]: row[1:] for row in workbook["Kategorien-Hinweise"].values}
        self.assertIn("oneEgid_oneAddress_multipleGVBSIDs", notes["Grundregel"][0])
        self.assertIn("oneEgid_multipleAddresses_multipleGVBSIDs", notes["Grundregel"][0])

    def test_priority_checks_reach_output_sheets_and_totals(self):
        for options, category, assigned_count in (
            ({"missing_grid": True}, "invalid_gwr_data", 0),
            ({"suffix_conflict": True}, "review_address_suffix", 2),
        ):
            with self.subTest(category=category):
                records, results = synthetic_assignment_case(
                    ["10", "10", "20", "22", "99"],
                    {"10": {900000001}, "20": {900000002}, "22": {900000002}},
                    **options,
                )
                workbook = self.create_output(list(app.REQUIRED), records, results)
                self.addCleanup(workbook.close)
                for sheet_name in ("Matching", "Ergebnis", category):
                    rows = list(workbook[sheet_name].values)
                    column = rows[0].index("EGID")
                    self.assertIsNone(rows[1][column])
                    self.assertIsNone(rows[2][column])
                overview = {row[0]: row[1:] for row in list(workbook["Zusammenfassung"].values)[1:]}
                self.assertEqual(overview["Automatisch zugeordnet"], (assigned_count, assigned_count / 5, None))
                self.assertEqual(overview["Nicht automatisch zugeordnet"], (5 - assigned_count, (5 - assigned_count) / 5, None))
                expected_review_count = 4 if category == "invalid_gwr_data" else 2
                self.assertEqual(overview[category][0], expected_review_count)
                self.assertEqual(overview[category][1], expected_review_count / 5)

    def test_result_sheet_preserves_import_and_inserts_search_address_and_assigned_egid(self):
        headers = [*app.REQUIRED, "Notiz", "Zweckbestimmung", "Zusätzliche Zahl"]
        rows = [
            [10, "1", "Synthetische Teststrasse", 12, " a ", "0000", "Treffer", "Synthetischer Zweck 1", 123],
            ["2", "2", "Synthetische Teststrasse", 99, None, "0000", "Kein Treffer", "Synthetischer Zweck 2", None],
            [2, "3", "Synthetische Teststrasse", 13, None, "0000", "Mehrdeutig", "Synthetischer Zweck 3", 0],
            [1, "4", "Synthetische Teststrasse", 14, None, "0000", "Zusatzkonflikt", "Synthetischer Zweck 4", 456],
            ["003", "5", "Synthetische Teststrasse", 15, None, "0000", "Super-Match", "Synthetischer Zweck 5", 789],
        ]
        records = [dict(zip(headers, row)) for row in rows]
        key = lambda number: app.address("Synthetische Teststrasse", number, "0000")
        results = app.match(
            records,
            {key("12a"): {900000001}, key("13"): {900000002, 900000003},
             key("14"): {900000004}, key("15"): {900000006}},
            {900000001: {key("12a")}, 900000002: {key("13")}, 900000003: {key("13")},
             900000004: {key("14")}, 900000005: {key("14a")},
             900000006: {key("15"), key("15a")}},
            {900000001: {"TEST-1"}, 900000002: {"TEST-2"}, 900000003: {"TEST-3"},
             900000004: {"TEST-4"}, 900000005: {"TEST-4"}, 900000006: {"TEST-5"}},
            {"TEST-1": {900000001}, "TEST-2": {900000002}, "TEST-3": {900000003},
             "TEST-4": {900000004, 900000005}, "TEST-5": {900000006}},
        )
        self.assertEqual([result["Matching-Kategorie"] for result in results], [
            "perfect_match", "no_match", "multiple_egid", "review_address_suffix", "super_match",
        ])
        workbook = self.create_output(headers, records, results)
        self.addCleanup(workbook.close)
        self.assertEqual(workbook.sheetnames, ["Matching", "Zusammenfassung", "Kategorien-Hinweise", "Ergebnis"] + [
            app.CATEGORY_SHEET_TITLES.get(name, name) for name, _, _ in app.CATEGORIES
        ])
        outcome = list(workbook["Ergebnis"].values)
        self.assertEqual(outcome[0], tuple(headers[:6] + ["Suchadresse", "EGID"] + headers[6:]))
        search_addresses = [
            "Synthetische Teststrasse 12a, 0000",
            "Synthetische Teststrasse 99, 0000",
            "Synthetische Teststrasse 13, 0000",
            "Synthetische Teststrasse 14, 0000",
            "Synthetische Teststrasse 15, 0000",
        ]
        # Zahlen und Textzahlen gemeinsam sortieren; gleiche Nummern bleiben stabil.
        expected_order = [3, 1, 2, 4, 0]
        assigned_egids = [900000001, None, None, None, 900000006]
        for index, exported in zip(expected_order, outcome[1:], strict=True):
            original = rows[index]
            self.assertEqual(
                exported,
                tuple(original[:6] + [search_addresses[index], assigned_egids[index]] + original[6:]),
            )
        self.assertEqual([row[0] for row in outcome[1:]], [1, "2", 2, "003", 10])
        self.assertEqual(workbook["Ergebnis"].freeze_panes, "A2")
        self.assertEqual(workbook["Ergebnis"].auto_filter.ref, "A1:K6")
        matching_rows = list(workbook["Matching"].values)
        matching_headers = matching_rows[0]
        self.assertEqual(matching_headers[:4], ("Suchadresse", "GVBSID", "Matching-Zusammenfassung", "Zweckbestimmung"))
        remaining_headers = tuple(column for column in headers if column != "Zweckbestimmung")
        self.assertEqual(matching_headers[4:4 + len(remaining_headers)], remaining_headers)
        self.assertEqual(matching_headers.count("Zweckbestimmung"), 1)
        for index, exported in zip(expected_order, matching_rows[1:], strict=True):
            result = results[index]
            self.assertEqual(exported[:4], (
                search_addresses[index], result["GVBSID"], result["Matching-Zusammenfassung"], rows[index][-2],
            ))
            self.assertEqual(exported[matching_headers.index("EGID")], assigned_egids[index])
        self.assertEqual(
            [row[matching_headers.index("Kontrollnummer")] for row in matching_rows[1:]],
            [1, "2", 2, "003", 10],
        )
        self.assertIn("Matching-Kategorie", matching_headers)
        self.assertIn("Matching-Zusammenfassung", matching_headers)
        self.assertEqual({row[0]: row[1] for row in list(workbook["Zusammenfassung"].values)[1:]}["Gesamt"], 5)

    def test_legacy_import_and_existing_egid_column_are_preserved(self):
        headers = ["Kontrollnummer", "Gebäude (Nr.)", "Strassennamen", "Nr.", "PLZ", "EGID", "GVBSID"]
        row = ["SYNTHETIC-1", "7", "Synthetische Teststrasse", 12, "0000", "Original-EGID", "Original-GVBSID"]
        records = [dict(zip(headers, row))]
        results = app.match(records, {}, {}, {}, {})
        workbook = self.create_output(headers, records, results)
        self.addCleanup(workbook.close)
        self.assertEqual(list(workbook["Ergebnis"].values), [
            tuple(headers[:5] + ["Suchadresse", "EGID"] + headers[5:]),
            tuple(row[:5] + ["Synthetische Teststrasse 12, 0000", None] + row[5:]),
        ])
        matching_headers = next(workbook["Matching"].values)
        self.assertEqual(matching_headers[:4], ("Suchadresse", "GVBSID", "Matching-Zusammenfassung", "Zweckbestimmung"))
        self.assertIsNone(list(workbook["Matching"].values)[1][3])
        self.assertEqual(matching_headers.count("GVBSID"), 1)

    def test_empty_import_creates_all_sheets_and_result_headers(self):
        workbook = self.create_output(list(app.REQUIRED), [], [])
        self.addCleanup(workbook.close)
        self.assertEqual(list(workbook["Ergebnis"].values), [tuple([*app.REQUIRED, "Suchadresse", "EGID"])])
        self.assertEqual(next(workbook["Matching"].values)[:4], ("Suchadresse", "GVBSID", "Matching-Zusammenfassung", "Zweckbestimmung"))
        self.assertEqual(len(workbook.worksheets), 4 + len(app.CATEGORIES))


if __name__ == "__main__":
    unittest.main()

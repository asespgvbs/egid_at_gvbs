"""Dialogtests mit simulierten Auswahlen und vollständig synthetischen Daten."""

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "main.py"
SPEC = importlib.util.spec_from_file_location("egid_match_main", SCRIPT)
app = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)


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
        expected_input = SCRIPT.parent / "data" / "test_match_data.xlsx"
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


class OutputWorkbookTests(unittest.TestCase):
    def create_output(self, headers, records, results):
        # Echter Excel-Export ausschliesslich im Arbeitsspeicher.
        workbook = app.Workbook()
        with (
            patch.object(app, "Workbook", return_value=workbook),
            patch.object(workbook, "save") as save,
        ):
            app.save_excel(Path("synthetic/output.xlsx"), headers, results, records)
        save.assert_called_once_with(Path("synthetic/output.xlsx"))
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return app.load_workbook(output)

    def test_result_sheet_preserves_import_and_inserts_only_assigned_egid(self):
        headers = [*app.REQUIRED, "Notiz", "Zusätzliche Zahl"]
        rows = [
            ["SYNTHETIC-1", "1", "Synthetische Teststrasse", 12, "a", "0000", "Treffer", 123],
            ["SYNTHETIC-2", "2", "Synthetische Teststrasse", 99, None, "0000", "Kein Treffer", None],
            ["SYNTHETIC-3", "3", "Synthetische Teststrasse", 13, None, "0000", "Mehrdeutig", 0],
            ["SYNTHETIC-4", "4", "Synthetische Teststrasse", 14, None, "0000", "Zusatzkonflikt", 456],
            ["SYNTHETIC-5", "5", "Synthetische Teststrasse", 15, None, "0000", "Super-Match", 789],
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
        self.assertEqual(workbook.sheetnames, ["Matching", "Zusammenfassung", "Kategorien-Hinweise", "Egebnis"])
        outcome = list(workbook["Egebnis"].values)
        self.assertEqual(outcome[0], tuple(headers[:6] + ["EGID"] + headers[6:]))
        for original, exported, egid in zip(rows, outcome[1:], [900000001, None, None, None, 900000006], strict=True):
            self.assertEqual(exported, tuple(original[:6] + [egid] + original[6:]))
        self.assertEqual(workbook["Egebnis"].freeze_panes, "A2")
        self.assertEqual(workbook["Egebnis"].auto_filter.ref, "A1:I6")
        matching_headers = next(workbook["Matching"].values)
        self.assertIn("Matching-Kategorie", matching_headers)
        self.assertIn("Matching-Zusammenfassung", matching_headers)
        self.assertEqual(dict(list(workbook["Zusammenfassung"].values)[1:])["Gesamt"], 5)

    def test_legacy_import_and_existing_egid_column_are_preserved(self):
        headers = ["Kontrollnummer", "Gebäude (Nr.)", "Strassennamen", "Nr.", "PLZ", "EGID", "GVBSID"]
        row = ["SYNTHETIC-1", "7", "Synthetische Teststrasse", 12, "0000", "Original-EGID", "Original-GVBSID"]
        records = [dict(zip(headers, row))]
        results = app.match(records, {}, {}, {}, {})
        workbook = self.create_output(headers, records, results)
        self.addCleanup(workbook.close)
        self.assertEqual(list(workbook["Egebnis"].values), [
            tuple(headers[:5] + ["EGID"] + headers[5:]),
            tuple(row[:5] + [None] + row[5:]),
        ])

    def test_empty_import_creates_all_sheets_and_result_headers(self):
        workbook = self.create_output(list(app.REQUIRED), [], [])
        self.addCleanup(workbook.close)
        self.assertEqual(list(workbook["Egebnis"].values), [tuple([*app.REQUIRED, "EGID"])])
        self.assertEqual(len(workbook.worksheets), 4)


if __name__ == "__main__":
    unittest.main()

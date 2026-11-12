"""Dialogtests mit simulierten Auswahlen und vollständig synthetischen Daten."""

import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "gvbs_egid_match.py"
SPEC = importlib.util.spec_from_file_location("gvbs_egid_match", SCRIPT)
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
                "Gebäude (Nr.)": "1",
                "Strasse": "Synthetische Teststrasse",
                "Nr.": "1",
                "PLZ": "0000",
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


if __name__ == "__main__":
    unittest.main()

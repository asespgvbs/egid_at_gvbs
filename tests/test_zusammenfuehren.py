"""Zusammenführung ausschliesslich mit synthetischen Arbeitsmappen im Speicher."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from openpyxl import Workbook
from egid_match.zusammenfuehren import merge_workbooks, main


def workbooks():
    original = Workbook()
    original.active.append(["Kontrollnummer", "Gebäudenummer", "EGID zusammengeführt", "Testwert"])
    original.active.append(["SYNTHETIC-A", 0, None, "bleibt"])
    original.active.append(["SYNTHETIC-B", 1, "901, 902", "bleibt"])
    original.active.append(["SYNTHETIC-C", 0, None, "bleibt"])
    original.create_sheet("Weitere Angaben")["A1"] = "synthetisch"
    matching = Workbook()
    matching.active.title = "Matching"
    matching.active.append(["GVBSID", "EGID", "Matching-Kategorie", "Automatische Zuordnung"])
    matching.active.append(["SYNTHETIC-A-0", 900, "perfect_match", "Ja"])
    matching.active.append(["SYNTHETIC-B-1", None, "manuell_zugeteilt", "Nein"])
    matching.active.append(["SYNTHETIC-C-0", None, "no_match", "Nein"])
    manual = Workbook()
    manual.active.title = "Zuordnungen"
    manual.active.append(["GVBSID", "Zweckbestimmung", "EGID", "Bearbeitungsstatus", "Kommentar"])
    manual.active.append(["SYNTHETIC-A-0", None, 903, "Abgeschlossen", None])
    manual.active.append(["SYNTHETIC-B-1", None, 901, "Abgeschlossen", None])
    return original, matching, manual


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.books = workbooks()
        for book in self.books:
            self.addCleanup(book.close)
        guard = patch("egid_match.zusammenfuehren.load_workbook", side_effect=AssertionError("Kein Dateizugriff"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_mixed_assignments_original_values_and_empty_case(self):
        book = merge_workbooks(*self.books)
        rows = list(book["Zuteileung_EGID_GVBS"].values)
        self.assertEqual(rows[0], ("Kontrollnummer", "Gebäudenummer", "EGID_zusammengeführt", "EGID_zugeteil_aus"))
        self.assertEqual(rows[1][-2:], ("900, 903", "perfect_match, manuell"))
        self.assertEqual(rows[2][-2:], ("901, 902", "manuell, manuell"))
        self.assertEqual(rows[3][-2:], (None, None))
        self.assertEqual(rows[2][:2], ("SYNTHETIC-B", 1))
        self.assertEqual(book.sheetnames, ["Sheet", "Weitere Angaben", "Zuteileung_EGID_GVBS", "Zusammenfassung"])
        original_rows = list(book.active.values)
        self.assertEqual(original_rows[0], ("Kontrollnummer", "Gebäudenummer", "EGID zusammengeführt", "Testwert", "zugeteilt aus"))
        self.assertEqual((original_rows[1][2], original_rows[1][4]), ("900, 903", "perfect_match, manuell"))
        summary = list(book["Zusammenfassung"].values)
        self.assertEqual(summary[0], ("Zuteilungsquelle", "Anzahl", "Prozent", "Prozent kumuliert"))
        self.assertEqual([row[0] for row in summary[1:-1]],
                         ["perfect_match, manuell", "manuell, manuell", "Nicht zugeteilt"])
        self.assertEqual(sum(row[1] for row in summary[1:-1]), 3)
        self.assertEqual(summary[-2][3], 1)
        self.assertEqual(summary[-1], ("Gesamt", 3, 1, None))
        self.assertEqual(book["Zusammenfassung"]["C2"].number_format, "0.00%")
        self.assertEqual(self.books[0]["Weitere Angaben"]["A1"].value, "synthetisch")

    def test_summary_orders_matching_categories_before_manual_and_unassigned(self):
        self.books[1].active.cell(3, 2, 904)
        self.books[1].active.cell(3, 3, "super_match")
        self.books[1].active.cell(3, 4, "Ja")
        self.books[0].active.cell(3, 3).value = None
        self.books[2].active.delete_rows(3)
        book = merge_workbooks(*self.books)
        labels = [row[0].value for row in book["Zusammenfassung"].iter_rows(min_row=2)]
        self.assertEqual(labels, ["perfect_match, manuell", "super_match", "Nicht zugeteilt", "Gesamt"])

    def test_unknown_and_duplicate_ids_rejected_before_output_changes(self):
        self.books[2].active.append(["SYNTHETIC-UNKNOWN-0", None, 999])
        with self.assertRaisesRegex(ValueError, "fehlen"):
            merge_workbooks(*self.books)
        self.assertEqual(self.books[0].active.max_column, 4)

    def test_conflicting_sources_are_not_silently_merged(self):
        self.books[2].active.append(["SYNTHETIC-A-0", None, 900])
        with self.assertRaisesRegex(ValueError, "widersprüchliche"):
            merge_workbooks(*self.books)

    def test_duplicate_original_gvbsid_is_rejected(self):
        self.books[0].active.append(["SYNTHETIC-A", 0, None, "doppelt"])
        with self.assertRaisesRegex(ValueError, "mehrfach"):
            merge_workbooks(*self.books)

    def test_reuses_existing_assignment_and_source_columns(self):
        self.books[0].active.cell(1, 5, "zugeteilt aus")
        self.books[0].active.cell(4, 5, "veraltet")
        book = merge_workbooks(*self.books)
        rows = list(book.active.values)
        self.assertEqual(len(rows[0]), 5)
        self.assertEqual(rows[1][2], "900, 903")
        self.assertEqual(rows[1][4], "perfect_match, manuell")
        self.assertIsNone(rows[3][4])

    def test_original_cannot_be_output(self):
        inputs = (Path("synthetic-original.xlsx"), Path("synthetic-matching.xlsx"), Path("synthetic-manual.xlsx"))
        with patch("egid_match.zusammenfuehren.select_files", return_value=(*inputs, inputs[0])):
            with self.assertRaisesRegex(ValueError, "verschieden"):
                main()

    def test_cancel_never_opens_a_file(self):
        with patch("egid_match.zusammenfuehren.select_files", return_value=None), patch("builtins.print"):
            main()


if __name__ == "__main__":
    unittest.main()

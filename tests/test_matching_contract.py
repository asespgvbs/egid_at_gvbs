"""Export und Zuordnungsimport mit synthetischen Arbeitsmappen und SQLite :memory:."""

from pathlib import Path
import sqlite3
import sys
from unittest.mock import patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from egid_match import matching, abdeckung
from egid_match.zuordnung import store
from test_suffix_pairs import synthetic_pair
from test_zuordnung_store import SyntheticMemory


class MatchingContractTests(SyntheticMemory):
    def setUp(self):
        super().setUp()
        connect = sqlite3.connect

        def only_memory(database, *args, **kwargs):
            if database != ":memory:":
                raise AssertionError("Nur synthetische SQLite-Daten im Speicher erlaubt")
            return connect(database, *args, **kwargs)

        guard = patch("sqlite3.connect", side_effect=only_memory)
        guard.start()
        self.addCleanup(guard.stop)

    def workbook(self, single=False):
        fixture = synthetic_pair((None,), (0,)) if single else synthetic_pair((300, 100))
        address = matching.address("Synthetische Teststrasse", "99", "0000")
        fixture[0].append({**fixture[0][0], "Kontrollnummer": "SYNTHETIC-AUTO", "Hausnummer": 99})
        fixture[1][address] = {900000050}
        fixture[2][900000050] = {address}
        fixture[3][900000050] = {"SYNTHETIC-AUTO-GRID"}
        fixture[4]["SYNTHETIC-AUTO-GRID"] = {900000050}
        results = matching.match(*fixture)
        if single:
            # Historische Matching-Ausgabe vor der automatischen Zuteilung.
            results[0]["EGID"] = None
            results[0]["Automatische Zuordnung"] = "Nein"
        workbook = matching.Workbook()
        self.addCleanup(workbook.close)
        # Nur der Dateizugriff ist ersetzt; Export und Import sind Produktionscode.
        with patch.object(matching, "Workbook", return_value=workbook), patch.object(workbook, "save") as save:
            matching.save_excel(self.folder / "synthetic.xlsx", list(fixture[0][0]), results, fixture[0])
        save.assert_called_once_with(self.folder / "synthetic.xlsx")
        return workbook, fixture, results

    def read(self, workbook):
        with patch.object(store, "load_workbook", return_value=workbook):
            return store.read_review_excel(self.folder / "synthetic.xlsx")

    def import_workbook(self, destination, workbook):
        with patch.object(store, "load_workbook", return_value=workbook):
            return destination.import_excel(self.folder / "synthetic.xlsx")

    def rename_all(self, workbook):
        for index, sheet in enumerate(workbook.worksheets):
            sheet.title = f"SYNTHETIC-TABLE-{index}"

    def test_manual_assignment_is_reserved_and_conflict_is_imported(self):
        fixture = synthetic_pair((None,), (0,))
        fixture[0][0]["EGID_zugeteilt"] = "900000001; 900000010"
        fixture[0].append({**fixture[0][0], "Kontrollnummer": "SYNTHETIC-OTHER", "EGID_zugeteilt": ""})
        results = matching.match(*fixture)
        self.assertEqual([row["Matching-Kategorie"] for row in results], ["manuell_zugeteilt", "zuordnungskonflikt"])
        self.assertTrue(all(row["EGID"] is None and row["Automatische Zuordnung"] == "Nein" for row in results))
        self.assertIn("900000001", results[1]["Matching-Zusammenfassung"])
        workbook = matching.Workbook()
        self.addCleanup(workbook.close)
        with patch.object(matching, "Workbook", return_value=workbook), patch.object(workbook, "save"):
            matching.save_excel(self.folder / "synthetic.xlsx", list(fixture[0][0]), results, fixture[0])
        summary = {row[0].value: row for row in workbook["Zusammenfassung"].iter_rows(min_row=2)}
        self.assertTrue(all(cell.fill.fgColor.rgb == "00FF0000" for cell in summary["zuordnungskonflikt"]))
        self.assertEqual(workbook["manuell_zugeteilt"]["A2"].fill.fgColor.rgb, "00D9D9D9")
        self.assertEqual(workbook["zuordnungskonflikt"]["A2"].fill.fgColor.rgb, "00FF0000")
        destination = self.empty_store()
        self.assertEqual(self.import_workbook(destination, workbook), 1)
        self.assertEqual(destination.automatic_egids(), {"900000001", "900000010"})
        record = destination.records()[0]
        self.assertEqual(record["raw"]["Matching-Kategorie"], "zuordnungskonflikt")
        with self.assertRaisesRegex(store.ReviewError, "zugeteilt"):
            destination.save([{"gvbsid": record["gvbsid"], "version": record["version"],
                               "assigned": ["900000001"]}], {"900000001"})

    def test_reserved_suffix_prevents_automatic_pair_assignment(self):
        fixture = synthetic_pair((400, 100))
        fixture[0].append({**fixture[0][0], "Kontrollnummer": "SYNTHETIC-OWNER",
                           "Hausnummer": 99, "EGID_zugeteilt": 900000002})
        results = matching.match(*fixture)
        self.assertEqual([row["Matching-Kategorie"] for row in results],
                         ["zuordnungskonflikt", "zuordnungskonflikt", "manuell_zugeteilt"])
        self.assertTrue(all(row["EGID"] is None for row in results))

    def test_invalid_manual_egid_is_rejected(self):
        fixture = synthetic_pair((None,), (0,))
        for value in ("abc", "1.2", ",;", -1):
            with self.subTest(value=value):
                fixture[0][0]["EGID_zugeteilt"] = value
                with self.assertRaisesRegex(ValueError, "EGID"):
                    matching.match(*fixture)

    def test_summary_does_not_color_zero_conflicts(self):
        workbook, _, _ = self.workbook()
        row = next(row for row in workbook["Zusammenfassung"].iter_rows(min_row=2)
                   if row[0].value == "zuordnungskonflikt")
        self.assertEqual(row[1].value, 0)
        self.assertTrue(all(cell.fill.patternType is None for cell in row))

    def test_export_to_import_preserves_original_values_decisions_and_global_locks(self):
        workbook, _, _ = self.workbook()
        self.assertTrue(all(len(sheet.title) <= 31 for sheet in workbook))
        destination = self.empty_store()
        self.assertEqual(self.import_workbook(destination, workbook), 2)
        self.assertEqual(destination.automatic_egids(), {"900000050"})
        record = destination.records()[0]
        self.assertEqual(record["raw"]["Matching-Kategorie"], matching.SUFFIX_PAIR_REVIEW)
        destination.save([{"gvbsid": record["gvbsid"], "version": record["version"],
                           "assigned": ["900000001"], "status": "Sonderfall", "comment": "Synthetisch geprüft"}],
                         {"900000001"})
        self.assertEqual(self.import_workbook(destination, workbook), 2)
        saved = destination.records()[0]
        self.assertEqual((saved["assigned"], saved["status"], saved["comment"]),
                         (["900000001"], "Sonderfall", "Synthetisch geprüft"))
        self.assertEqual(saved["raw"], record["raw"])
        with self.assertRaisesRegex(store.ReviewError, "zugeteilt"):
            destination.save([{"gvbsid": saved["gvbsid"], "version": saved["version"],
                               "assigned": ["900000050"]}], {"900000050"})

    def test_completely_renamed_export_is_importable_with_all_automatic_locks(self):
        workbook, _, _ = self.workbook(single=True)
        self.rename_all(workbook)
        destination = self.empty_store()
        self.assertEqual(self.import_workbook(destination, workbook), 1)
        self.assertEqual(destination.automatic_egids(), {"900000050"})
        self.assertEqual(destination.records()[0]["raw"]["Matching-Kategorie"], matching.SUFFIX_SINGLE_REVIEW)

    def test_total_sheet_supplies_missing_empty_or_partial_category_sheets(self):
        for layout in ("missing", "empty", "partial"):
            with self.subTest(layout=layout):
                workbook, _, results = self.workbook()
                sheet = workbook[matching.SUFFIX_PAIR_REVIEW]
                if layout == "missing":
                    del workbook[sheet.title]
                else:
                    sheet.delete_rows(2, 2 if layout == "empty" else 1)
                _, records, blocked = self.read(workbook)
                self.assertEqual([record["gvbsid"] for record in records], [row["GVBSID"] for row in results[:2]])
                self.assertEqual(blocked, {"900000050"})

    def test_legacy_short_and_normalized_category_names_with_app_lock_sheet(self):
        for title in ("review_suffix_single_building", matching.SUFFIX_SINGLE_REVIEW[:31],
                      matching.CATEGORY_SHEET_TITLES[matching.SUFFIX_SINGLE_REVIEW],
                      " " + matching.CATEGORY_SHEET_TITLES[matching.SUFFIX_SINGLE_REVIEW].upper() + " "):
            with self.subTest(title=title):
                workbook, _, _ = self.workbook(single=True)
                review = workbook[matching.CATEGORY_SHEET_TITLES[matching.SUFFIX_SINGLE_REVIEW]]
                for name in list(workbook.sheetnames):
                    if name != review.title:
                        del workbook[name]
                review.title = title
                index = next(cell.column for cell in review[1] if cell.value == "Matching-Kategorie")
                review.cell(2, index, "review_suffix_single_building")
                locks = workbook.create_sheet(" automatische zuordnungen ")
                locks.append(["EGID"])
                locks.append([900000050])
                _, records, blocked = self.read(workbook)
                self.assertEqual(records[0]["raw"]["Matching-Kategorie"], "review_suffix_single_building")
                self.assertEqual(blocked, {"900000050"})

    def test_legacy_categories_in_renamed_export_and_coverage_are_canonicalized(self):
        workbook, fixture, results = self.workbook(single=True)
        for sheet in workbook:
            for row in sheet:
                for cell in row:
                    if cell.value == matching.SUFFIX_SINGLE_REVIEW:
                        cell.value = "review_suffix_single_building"
        self.rename_all(workbook)
        _, records, blocked = self.read(workbook)
        self.assertEqual(records[0]["raw"]["Matching-Kategorie"], "review_suffix_single_building")
        self.assertEqual(blocked, {"900000050"})
        results[0]["Matching-Kategorie"] = "review_suffix_single_building"
        rows, issues = abdeckung.analyze_coverage(set(fixture[2]), results, fixture[2], fixture[3])
        self.assertEqual(issues, [])
        self.assertEqual(rows[0]["EGID-Hauptkategorie"], matching.SUFFIX_SINGLE_REVIEW)

    def test_renamed_category_subset_is_not_accepted_as_complete_matching(self):
        workbook, _, _ = self.workbook()
        del workbook["Matching"]
        self.rename_all(workbook)
        destination = self.empty_store()
        with self.assertRaises(store.ReviewError):
            self.import_workbook(destination, workbook)
        self.assertEqual(destination.records(), [])
        self.assertIsNone(destination.automatic_egids())

    def test_renamed_total_requires_matching_summary_counts_and_total(self):
        for error in ("total", "categories", "missing", "duplicate"):
            with self.subTest(error=error):
                workbook, _, _ = self.workbook()
                summary = workbook["Zusammenfassung"]
                if error == "missing":
                    del workbook[summary.title]
                elif error == "duplicate":
                    summary.append(["Gesamt", 3])
                else:
                    for row in summary:
                        if error == "total" and row[0].value == "Gesamt":
                            row[1].value += 1
                        elif error == "categories" and row[0].value == matching.SUFFIX_PAIR_REVIEW:
                            row[1].value = 1
                        elif error == "categories" and row[0].value == "perfect_match":
                            row[1].value = 2
                self.rename_all(workbook)
                self.assertIsNone(store.read_automatic_egids(workbook))
                with self.assertRaises(store.ReviewError):
                    self.read(workbook)

    def test_inconsistent_automatic_assignment_rolls_back_import(self):
        workbook, _, _ = self.workbook()
        sheet = workbook["Matching"]
        flag = next(cell.column for cell in sheet[1] if cell.value == "Automatische Zuordnung")
        egid = next(cell.column for cell in sheet[1] if cell.value == "EGID")
        for row in sheet.iter_rows(min_row=2):
            if row[egid - 1].value == 900000050:
                row[flag - 1].value = "Nein"
        self.rename_all(workbook)
        destination = self.empty_store()
        with self.assertRaisesRegex(store.ReviewError, "widersprüchliche automatische"):
            self.import_workbook(destination, workbook)
        self.assertEqual(destination.records(), [])
        self.assertIsNone(destination.automatic_egids())

    def test_app_export_remains_importable(self):
        workbook, _, _ = self.workbook()
        first = self.empty_store()
        self.import_workbook(first, workbook)
        exported = first.export_workbook()
        self.addCleanup(exported.close)
        second = self.empty_store(self.folder / "synthetic-second.sqlite")
        self.assertEqual(self.import_workbook(second, exported), 2)
        self.assertEqual(second.automatic_egids(), {"900000050"})


if __name__ == "__main__":
    unittest.main()

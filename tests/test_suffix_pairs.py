"""Kubatur-Paarregel mit vollständig synthetischen Daten und Excel nur im Speicher."""

import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from egid_match import abdeckung, matching
from egid_match.zuordnung import store


def synthetic_pair(volumes=(400, 100), buildings=(0, 1), suffixes=("12.1",)):
    records = [{
        "Kontrollnummer": "SYNTHETIC-PAIR", "Gebäudenummer": building,
        "Strasse": "Synthetische Teststrasse", "Hausnummer": 12,
        "Hausnummer Zusatz": None, "Postleitzahl": "0000", "Kubatur": volume,
    } for building, volume in zip(buildings, volumes, strict=True)]
    key = lambda number: matching.address("Synthetische Teststrasse", number, "0000")
    addresses = {900000001: {key("12")}}
    addresses.update({900000002 + index: {key(number)} for index, number in enumerate(suffixes)})
    candidates = {}
    for egid, values in addresses.items():
        for value in values:
            candidates.setdefault(value, set()).add(egid)
    grids = {egid: {"SYNTHETIC-EGRID"} for egid in addresses}
    parcels = {"SYNTHETIC-EGRID": set(addresses)}
    return records, candidates, addresses, grids, parcels


class SuffixPairTests(unittest.TestCase):
    def setUp(self):
        # Jeder unbeabsichtigte Datei-/Datenbankzugriff lässt den Test scheitern.
        guard = patch("egid_match.matching.load_workbook", side_effect=AssertionError("Dateizugriff im synthetischen Test"))
        guard.start()
        self.addCleanup(guard.stop)
        guard = patch("sqlite3.connect", side_effect=AssertionError("Datenbankzugriff im synthetischen Test"))
        guard.start()
        self.addCleanup(guard.stop)

    def evaluate(self, fixture):
        before = copy.deepcopy(fixture)
        results = matching.match(*fixture)
        self.assertEqual(fixture, before)
        return results

    def assert_review(self, fixture):
        results = self.evaluate(fixture)
        self.assertTrue(all(row["Matching-Kategorie"] not in (
            matching.SUFFIX_PAIR_AUTO, matching.SUFFIX_PAIR_REVIEW) for row in results))
        self.assertTrue(all(row["EGID"] is None for row in results))

    def workbook(self, fixture, results):
        workbook = matching.Workbook()
        self.addCleanup(workbook.close)
        with patch.object(matching, "Workbook", return_value=workbook), patch.object(workbook, "save") as save:
            matching.save_excel(Path("synthetic-not-created.xlsx"), list(fixture[0][0]), results, fixture[0])
        save.assert_called_once_with(Path("synthetic-not-created.xlsx"))
        return workbook

    def test_boundary_four_and_larger_assign_distinct_egids(self):
        for volumes in ((400, 100), (401, 100), (4000, 100), (0.4, 0.1), ("1’200,0", "300")):
            with self.subTest(volumes=volumes):
                results = self.evaluate(synthetic_pair(volumes))
                self.assertEqual([row["EGID"] for row in results], [900000001, 900000002])
                self.assertTrue(all(row["Matching-Kategorie"] == matching.SUFFIX_PAIR_AUTO for row in results))
                self.assertTrue(all(row["Automatische Zuordnung"] == "Ja" for row in results))
                self.assertTrue(results[1]["Zuordnungsadresse"].endswith("12.1 0000"))
                # Der ursprünglich direkte Hauptadresskandidat bleibt nachvollziehbar.
                self.assertEqual(results[1]["EGID-Kandidaten"], "900000001")

    def test_below_four_is_orange_without_assignment(self):
        for volumes in ((399.99, 100), (100, 100), (50, 100)):
            with self.subTest(volumes=volumes):
                results = self.evaluate(synthetic_pair(volumes))
                self.assertTrue(all(row["Matching-Kategorie"] == matching.SUFFIX_PAIR_REVIEW for row in results))
                self.assertTrue(all(row["EGID"] is None and row["Automatische Zuordnung"] == "Nein" for row in results))

    def test_building_numbers_determine_assignment_independent_of_order(self):
        results = self.evaluate(synthetic_pair((100, 400), (1, 0)))
        self.assertEqual([row["EGID"] for row in results], [900000002, 900000001])

    def test_one_three_and_duplicate_import_rows_do_not_form_pairs(self):
        for volumes, buildings in (((400,), (0,)), ((400, 100, 20), (0, 1, 2)),
                                   ((400, 100), (0, 0)), ((400, 100), (0, 2))):
            with self.subTest(buildings=buildings):
                self.assert_review(synthetic_pair(volumes, buildings))
        fixture = synthetic_pair()
        fixture[0].append(copy.deepcopy(fixture[0][0]))
        self.assert_review(fixture)
        fixture[0][-1]["Hausnummer"] = None  # Auch eine ungültige dritte Zeile zählt.
        self.assert_review(fixture)

    def test_missing_invalid_zero_negative_and_nonfinite_kubatur_stay_yellow(self):
        for value in (None, "", "nicht bekannt", 0, -1, True, "NaN", "Infinity", float("inf")):
            for index in (0, 1):
                with self.subTest(value=value, index=index):
                    volumes = [400, 100]
                    volumes[index] = value
                    self.assert_review(synthetic_pair(volumes))

    def test_other_suffixes_or_several_suffix_egids_stay_review(self):
        for suffixes in (("12.2",), ("12a",), ("12.1", "12.2"), ("12.1", "12.1")):
            with self.subTest(suffixes=suffixes):
                self.assert_review(synthetic_pair(suffixes=suffixes))

    def test_ambiguous_dot_one_candidate_outside_parcel_is_rejected(self):
        fixture = synthetic_pair()
        suffix = next(iter(fixture[2][900000002]))
        fixture[1][suffix].add(900000003)
        fixture[2][900000003] = {suffix}
        fixture[3][900000003] = {"SYNTHETIC-OTHER-GRID"}
        fixture[4]["SYNTHETIC-OTHER-GRID"] = {900000003}
        self.assert_review(fixture)

    def test_unrelated_control_claiming_main_egid_prevents_automatic_pair(self):
        fixture = synthetic_pair()
        other = {**fixture[0][0], "Kontrollnummer": "SYNTHETIC-OTHER"}
        fixture[0].append(other)
        self.assert_review(fixture)

    def test_different_import_addresses_do_not_form_pair(self):
        fixture = synthetic_pair()
        other_address = matching.address("Synthetische Teststrasse", "14", "0000")
        fixture[0][1]["Hausnummer"] = 14
        fixture[1][other_address] = {900000001}
        fixture[2][900000001].add(other_address)
        results = self.evaluate(fixture)
        self.assertNotIn(matching.SUFFIX_PAIR_AUTO, [row["Matching-Kategorie"] for row in results])

    def test_existing_suffix_gvbsid_is_not_overridden(self):
        fixture = synthetic_pair()
        fixture[0].append({**fixture[0][0], "Kontrollnummer": "SYNTHETIC-OTHER", "Hausnummer Zusatz": ".1"})
        results = self.evaluate(fixture)
        self.assertTrue(all(row["Matching-Kategorie"] != matching.SUFFIX_PAIR_AUTO for row in results))
        self.assertEqual(results[2]["EGID"], 900000002)

    def test_legacy_columns_support_same_pair_rule(self):
        fixture = synthetic_pair()
        for record in fixture[0]:
            record["Gebäude (Nr.)"] = record.pop("Gebäudenummer")
        self.assertEqual([row["EGID"] for row in self.evaluate(fixture)], [900000001, 900000002])

    def test_excel_assignments_summary_categories_and_colours(self):
        for volumes, category, color, automatic_count in (
            ((400, 100), matching.SUFFIX_PAIR_AUTO, "00C4A484", 2),
            ((399, 100), matching.SUFFIX_PAIR_REVIEW, "00F4B183", 0),
        ):
            with self.subTest(category=category):
                fixture = synthetic_pair(volumes)
                results = self.evaluate(fixture)
                workbook = self.workbook(fixture, results)
                for name in ("Matching", category):
                    sheet = workbook[name]
                    self.assertEqual(sheet.max_row, 3)
                    self.assertEqual(sheet["A2"].fill.fgColor.rgb, color)
                    self.assertEqual(sheet["A3"].fill.fgColor.rgb, color)
                summary = {row[0]: row[1] for row in list(workbook["Zusammenfassung"].values)[1:]}
                self.assertEqual(summary[category], 2)
                self.assertEqual(summary["Automatisch zugeordnet"], automatic_count)
                outcome = list(workbook["Ergebnis"].values)
                egid_column = outcome[0].index("EGID")
                self.assertEqual([row[egid_column] for row in outcome[1:]], [row["EGID"] for row in results])

    def test_coverage_counts_assigned_suffix_and_keeps_balances(self):
        fixture = synthetic_pair()
        results = self.evaluate(fixture)
        rows, issues = abdeckung.analyze_coverage(set(fixture[2]), results, fixture[2], fixture[3])
        self.assertEqual(issues, [])
        categories, statuses = abdeckung.summarize_coverage(rows)
        self.assertEqual(categories[matching.SUFFIX_PAIR_AUTO], 2)
        self.assertEqual(statuses[abdeckung.AUTOMATIC], 2)
        suffix = next(row for row in rows if row["EGID"] == 900000002)
        self.assertEqual(suffix["Zugehörige GVBSIDs"], "SYNTHETIC-PAIR-1")
        self.assertEqual(suffix["Direkter GVBS-Adresskandidat vorhanden"], "Nein")
        self.assertEqual(suffix["Automatisch zugeordnet"], "Ja")
        workbook = matching.Workbook()
        with patch.object(abdeckung, "Workbook", return_value=workbook), patch.object(workbook, "save"):
            abdeckung.save_coverage_excel(Path("synthetic-not-created.xlsx"), rows, issues)
        self.addCleanup(workbook.close)
        self.assertEqual(workbook["EGID-ohne-GVBSID"].max_row, 1)

    def test_below_four_stays_unassigned_in_coverage(self):
        fixture = synthetic_pair((300, 100))
        results = self.evaluate(fixture)
        rows, issues = abdeckung.analyze_coverage(set(fixture[2]), results, fixture[2], fixture[3])
        self.assertEqual(issues, [])
        _, statuses = abdeckung.summarize_coverage(rows)
        self.assertEqual(statuses[abdeckung.AUTOMATIC], 0)
        self.assertEqual(sum(statuses.values()), 2)

    def test_manual_import_includes_orange_pairs_and_excludes_automatic_pairs(self):
        for volumes, expected in (((400, 100), []), ((300, 100), ["SYNTHETIC-PAIR-0", "SYNTHETIC-PAIR-1"])):
            fixture = synthetic_pair(volumes)
            workbook = self.workbook(fixture, self.evaluate(fixture))
            with patch.object(store, "load_workbook", return_value=workbook):
                if expected:
                    _, records, _ = store.read_review_excel(Path("synthetic-not-created.xlsx"))
                    self.assertEqual([row["gvbsid"] for row in records], expected)
                else:
                    with self.assertRaises(store.ReviewError):
                        store.read_review_excel(Path("synthetic-not-created.xlsx"))

    def test_manual_import_merges_yellow_and_orange_sheets(self):
        fixture = synthetic_pair((300, 100))
        fixture[0].append({**fixture[0][0], "Kontrollnummer": "SYNTHETIC-SINGLE", "Gebäudenummer": 2})
        # Separate synthetische Parzelle verhindert Konkurrenz zum Paar.
        fixture[0][-1]["Hausnummer"] = 20
        main = matching.address("Synthetische Teststrasse", "20", "0000")
        suffix = matching.address("Synthetische Teststrasse", "20a", "0000")
        fixture[1].update({main: {900000003}, suffix: {900000004}})
        fixture[2].update({900000003: {main}, 900000004: {suffix}})
        fixture[3].update({900000003: {"SYNTHETIC-SECOND"}, 900000004: {"SYNTHETIC-SECOND"}})
        fixture[4]["SYNTHETIC-SECOND"] = {900000003, 900000004}
        workbook = self.workbook(fixture, self.evaluate(fixture))
        with patch.object(store, "load_workbook", return_value=workbook):
            _, records, _ = store.read_review_excel(Path("synthetic-not-created.xlsx"))
        self.assertEqual({row["gvbsid"] for row in records}, {
            "SYNTHETIC-SINGLE-2", "SYNTHETIC-PAIR-0", "SYNTHETIC-PAIR-1"})

    def test_single_building_zero_with_one_or_multiple_suffixes_stays_unassigned(self):
        for suffixes in (("12.1",), ("12.2",), ("12a",), ("12.1", "12.2", "12a")):
            with self.subTest(suffixes=suffixes):
                fixture = synthetic_pair((None,), (0,), suffixes)
                record = self.evaluate(fixture)[0]
                self.assertEqual(record["Matching-Kategorie"], matching.SUFFIX_SINGLE_REVIEW)
                self.assertIsNone(record["EGID"])
                self.assertEqual(record["Automatische Zuordnung"], "Nein")
                self.assertEqual(record["Anzahl EGID mit Hausnummernzusatz"], len(suffixes))
                self.assertIn("Gebäudenummer 0", record["Matching-Zusammenfassung"])
                self.assertNotIn("Kubaturverhältnis 0/1", record)

    def test_single_building_category_requires_building_zero(self):
        for building in (1, 2, "", None):
            with self.subTest(building=building):
                record = self.evaluate(synthetic_pair((400,), (building,)))[0]
                self.assertNotEqual(record["Matching-Kategorie"], matching.SUFFIX_SINGLE_REVIEW)
                self.assertIsNone(record["EGID"])

    def test_single_building_category_rejects_duplicate_or_other_control_at_address(self):
        for same_control in (True, False):
            with self.subTest(same_control=same_control):
                fixture = synthetic_pair((400,), (0,))
                other = copy.deepcopy(fixture[0][0])
                if not same_control:
                    other["Kontrollnummer"] = "SYNTHETIC-OTHER"
                    other["Strasse"] = "  SYNTHETISCHE TESTSTRASSE  "
                    other["Hausnummer"] = " 12 "
                fixture[0].append(other)
                records = self.evaluate(fixture)
                self.assertTrue(all(row["Matching-Kategorie"] == "review_address_suffix" for row in records))

    def test_additional_building_elsewhere_or_invalid_row_prevents_single_category(self):
        for number in (99, None):
            with self.subTest(number=number):
                fixture = synthetic_pair((400,), (0,))
                fixture[0].append({**fixture[0][0], "Gebäudenummer": 1, "Hausnummer": number})
                records = self.evaluate(fixture)
                self.assertEqual(records[0]["Matching-Kategorie"], "review_address_suffix")
                self.assertIsNone(records[0]["EGID"])

    def test_single_without_suffix_keeps_existing_matching(self):
        record = self.evaluate(synthetic_pair((None,), (0,), ()))[0]
        self.assertEqual(record["Matching-Kategorie"], "perfect_match")
        self.assertEqual(record["EGID"], 900000001)

    def test_single_suffix_category_reaches_excel_coverage_and_manual_import(self):
        fixture = synthetic_pair((None,), (0,), ("12.1", "12a"))
        results = self.evaluate(fixture)
        workbook = self.workbook(fixture, results)
        category = matching.SUFFIX_SINGLE_REVIEW
        self.assertEqual(workbook[category].max_row, 2)
        self.assertEqual(workbook[category]["A2"].fill.fgColor.rgb, "00E6C200")
        summary = {row[0]: row[1] for row in list(workbook["Zusammenfassung"].values)[1:]}
        self.assertEqual(summary[category], 1)
        self.assertEqual(summary["Automatisch zugeordnet"], 0)
        outcome = list(workbook["Ergebnis"].values)
        self.assertIsNone(outcome[1][outcome[0].index("EGID")])
        rows, issues = abdeckung.analyze_coverage(set(fixture[2]), results, fixture[2], fixture[3])
        self.assertEqual(issues, [])
        categories, statuses = abdeckung.summarize_coverage(rows)
        self.assertEqual(categories[category], 1)
        self.assertEqual(statuses[abdeckung.AUTOMATIC], 0)
        self.assertEqual(statuses[abdeckung.DIRECT_ONLY], 1)
        self.assertEqual(statuses[abdeckung.NO_CANDIDATE], 2)
        with patch.object(store, "load_workbook", return_value=workbook):
            _, imported, _ = store.read_review_excel(Path("synthetic-not-created.xlsx"))
        self.assertEqual([row["gvbsid"] for row in imported], ["SYNTHETIC-PAIR-0"])

    def test_single_category_sheet_can_be_imported_on_its_own(self):
        fixture = synthetic_pair((None,), (0,))
        workbook = self.workbook(fixture, self.evaluate(fixture))
        for name in list(workbook.sheetnames):
            if name != matching.SUFFIX_SINGLE_REVIEW:
                del workbook[name]
        with patch.object(store, "load_workbook", return_value=workbook):
            _, imported, _ = store.read_review_excel(Path("synthetic-not-created.xlsx"))
        self.assertEqual([row["gvbsid"] for row in imported], ["SYNTHETIC-PAIR-0"])


if __name__ == "__main__":
    unittest.main()

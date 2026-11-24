"""Einmalige PLZ-Korrektur: synthetische Objekte, SQL nur in SQLite :memory:."""

from collections import defaultdict
import copy
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from egid_match import matching
from egid_match.zuordnung import store


def key(number="10", postal="4000"):
    return matching.address("Synthetische Postgasse", number, postal)


def record(control="SYNTHETIC", postal="9999", number="10", suffix=None, building="1", **extra):
    return {"Kontrollnummer": control, "Gebäudenummer": building, "Strasse": "Synthetische Postgasse",
            "Hausnummer": number, "Hausnummer Zusatz": suffix, "Postleitzahl": postal, **extra}


def fixture(records, addresses, shared_grid=False):
    candidates, grid_egids = defaultdict(set), defaultdict(set)
    grids = {}
    for egid, values in addresses.items():
        grid = "SYNTHETIC-GRID" if shared_grid else f"SYNTHETIC-GRID-{egid}"
        grids[egid] = {grid}
        grid_egids[grid].add(egid)
        for address in values:
            candidates[address].add(egid)
    return records, dict(candidates), addresses, grids, dict(grid_egids)


class PostalCorrectionTests(unittest.TestCase):
    def setUp(self):
        guard = patch("sqlite3.connect", side_effect=AssertionError("Kein Datenbankzugriff im reinen Matchingtest"))
        guard.start()
        self.addCleanup(guard.stop)
        guard = patch.object(matching, "load_workbook", side_effect=AssertionError("Kein Dateizugriff im Matchingtest"))
        guard.start()
        self.addCleanup(guard.stop)

    def evaluate(self, data, candidates):
        before = copy.deepcopy(data)
        lookup = Mock(return_value=candidates)
        results = matching.match(*data, postal_lookup=lookup)
        self.assertEqual(data, before)
        return results, lookup

    def test_unique_postal_corrects_and_runs_regular_matching_again(self):
        data = fixture([record()], {900001: {key()}})
        with patch.object(matching, "_match_regular", wraps=matching._match_regular) as regular:
            results, lookup = self.evaluate(data, {key()[:2]: {"4000"}})
        self.assertEqual(regular.call_count, 2)
        lookup.assert_called_once_with({key()[:2]})
        row = results[0]
        self.assertEqual((row["Postleitzahl"], row["Matching-Kategorie"], row["EGID"]),
                         ("4000", "perfect_match", 900001))
        self.assertEqual(row["PLZ ursprünglich"], "9999")
        self.assertEqual(row["PLZ korrigiert"], "Ja")
        self.assertIn("PLZ von 9999 auf 4000 korrigiert", row["Matching-Zusammenfassung"])

    def test_multiple_egids_at_one_postal_are_one_postal_but_remain_ambiguous_egids(self):
        data = fixture([record()], {900001: {key()}, 900002: {key()}})
        results, _ = self.evaluate(data, {key()[:2]: ["4000", "4000"]})
        self.assertEqual(results[0]["Postleitzahl"], "4000")
        self.assertEqual(results[0]["Matching-Kategorie"], "multiple_egid")
        self.assertIsNone(results[0]["EGID"])

    def test_no_or_multiple_postals_keep_original_postal_and_no_match(self):
        for candidates in ({}, {key()[:2]: {"4000", "4125"}}):
            with self.subTest(candidates=candidates):
                with patch.object(matching, "_match_regular", wraps=matching._match_regular) as regular:
                    results, lookup = self.evaluate(fixture([record()], {900001: {key()}}), candidates)
                self.assertEqual(regular.call_count, 1)
                lookup.assert_called_once()
                self.assertEqual(results[0]["Matching-Kategorie"], "no_match")
                self.assertEqual(results[0]["Postleitzahl"], "9999")
                self.assertNotIn("PLZ korrigiert", results[0])

    def test_only_original_no_match_rows_are_requested(self):
        records = [record("SYNTHETIC-EXISTING", "4000"), record("SYNTHETIC-NONE", number="20"),
                   record("SYNTHETIC-INVALID", postal="", number="30"),
                   record("SYNTHETIC-AMBIGUOUS", "4000", number="40")]
        addresses = {900001: {key()}, 900002: {key("20")},
                     900003: {key("40")}, 900004: {key("40")}}
        results, lookup = self.evaluate(fixture(records, addresses), {key("20")[:2]: {"4000"}})
        lookup.assert_called_once_with({key("20")[:2]})
        self.assertEqual([row["Matching-Kategorie"] for row in results],
                         ["perfect_match", "perfect_match", "invalid_input", "multiple_egid"])
        self.assertNotIn("PLZ korrigiert", results[0])
        self.assertEqual(results[2]["Postleitzahl"], "")

    def test_no_lookup_if_regular_matching_has_no_no_match_rows(self):
        results, lookup = self.evaluate(fixture([record(postal="4000")], {900001: {key()}}), {})
        lookup.assert_not_called()
        self.assertEqual(results[0]["Matching-Kategorie"], "perfect_match")

    def test_collision_reclassifies_previously_perfect_object_in_entire_inventory(self):
        data = fixture([record("SYNTHETIC-OLD", "4000"), record("SYNTHETIC-NEW")], {900001: {key()}})
        self.assertEqual(matching.match(*data)[0]["Matching-Kategorie"], "perfect_match")
        results, _ = self.evaluate(data, {key()[:2]: {"4000"}})
        self.assertEqual([row["Matching-Kategorie"] for row in results],
                         ["oneEgid_oneAddress_multipleGVBSIDs"] * 2)
        self.assertEqual([row["EGID"] for row in results], [900001, 900001])
        self.assertNotIn("PLZ korrigiert", results[0])

    def test_collision_across_different_addresses_reclassifies_existing_object(self):
        data = fixture([record("SYNTHETIC-OLD", "4000", "12"), record("SYNTHETIC-NEW")],
                       {900001: {key(), key("12")}})
        self.assertEqual(matching.match(*data)[0]["Matching-Kategorie"], "super_match")
        results, _ = self.evaluate(data, {key()[:2]: {"4000"}})
        self.assertEqual([row["Matching-Kategorie"] for row in results],
                         ["oneEgid_multipleAddresses_multipleGVBSIDs"] * 2)

    def test_suffix_owner_after_correction_reclassifies_unchanged_parent(self):
        data = fixture([record("SYNTHETIC-PARENT", "4000", building="0"),
                        record("SYNTHETIC-SUFFIX", suffix=".1")],
                       {900001: {key()}, 900002: {key("10.1")}}, shared_grid=True)
        self.assertEqual(matching.match(*data)[0]["Matching-Kategorie"], matching.SUFFIX_SINGLE_REVIEW)
        results, _ = self.evaluate(data, {key("10.1")[:2]: {"4000"}})
        self.assertEqual([row["Matching-Kategorie"] for row in results], ["super_match", "super_match"])
        self.assertEqual([row["EGID"] for row in results], [900001, 900002])

    def test_corrections_are_applied_together_and_can_form_a_suffix_pair(self):
        data = fixture([record(building="0", Kubatur=500), record(building="1", Kubatur=100)],
                       {900001: {key()}, 900002: {key("10.1")}}, shared_grid=True)
        results, lookup = self.evaluate(data, {key()[:2]: {"4000"}})
        lookup.assert_called_once_with({key()[:2]})
        self.assertEqual([row["Matching-Kategorie"] for row in results], [matching.SUFFIX_PAIR_AUTO] * 2)
        self.assertEqual([row["EGID"] for row in results], [900001, 900002])

    def test_legacy_postal_column_is_replaced_without_changing_input(self):
        item = record()
        item["PLZ"] = item.pop("Postleitzahl")
        item["Strassennamen"] = item.pop("Strasse")
        item["Nr."] = item.pop("Hausnummer")
        results, _ = self.evaluate(fixture([item], {900001: {key()}}), {key()[:2]: {"4000"}})
        self.assertEqual(results[0]["PLZ"], "4000")
        self.assertNotIn("Postleitzahl", results[0])
        self.assertEqual(item["PLZ"], "9999")

    def test_corrected_postal_and_search_address_reach_both_exports_and_import(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                item = record(building="0")
                postal_column = "PLZ" if legacy else "Postleitzahl"
                if legacy:
                    item["PLZ"] = item.pop("Postleitzahl")
                data = fixture([item], {900001: {key()}, 900002: {key("10.1")}}, shared_grid=True)
                results, _ = self.evaluate(data, {key()[:2]: {"4000"}})
                workbook = matching.Workbook()
                self.addCleanup(workbook.close)
                with patch.object(matching, "Workbook", return_value=workbook), patch.object(workbook, "save"):
                    matching.save_excel(ROOT / "synthetic-not-created.xlsx", list(item), results, [item])
                for name in ("Matching", "Ergebnis", matching.CATEGORY_SHEET_TITLES[matching.SUFFIX_SINGLE_REVIEW]):
                    headers, row = list(workbook[name].values)[:2]
                    fields = dict(zip(headers, row))
                    self.assertEqual(fields[postal_column], "4000")
                    self.assertEqual(fields["Suchadresse"], "Synthetische Postgasse 10, 4000")
                    self.assertEqual(fields["PLZ ursprünglich"], "9999")
                    self.assertEqual(fields["PLZ korrigiert"], "Ja")
                with patch.object(store, "load_workbook", return_value=workbook):
                    _, imported, _ = store.read_review_excel(ROOT / "synthetic-not-created.xlsx")
                self.assertEqual(imported[0]["address"], "Synthetische Postgasse 10, 4000")
                self.assertEqual(imported[0]["raw"][postal_column], "4000")


class PostalReaderTests(unittest.TestCase):
    def read_memory(self, field, buildings, entrances, requested=None):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute(f"CREATE TABLE building (EGID INTEGER, GSTAT INTEGER{', ' + field if field else ''})")
        connection.execute("CREATE TABLE entrance (EGID INTEGER, STRNAME TEXT, DEINR TEXT, DPLZ4 TEXT)")
        placeholders = ",".join("?" for _ in buildings[0])
        connection.executemany(f"INSERT INTO building VALUES ({placeholders})", buildings)
        connection.executemany("INSERT INTO entrance VALUES (?,?,?,?)", entrances)
        tracked = Mock(wraps=connection)
        with patch.object(matching.sqlite3, "connect", return_value=tracked) as connect:
            result = matching.read_postal_candidates(ROOT / "synthetic-not-created.sqlite", requested or {key()[:2]})
        self.assertTrue(connect.call_args.args[0].endswith("?mode=ro"))
        tracked.close.assert_called_once()
        return result

    def test_all_three_municipalities_and_supported_schema_fields(self):
        for field in ("GGDE", "GGDENR", "GGDENAME"):
            with self.subTest(field=field):
                municipalities = ("Basel", "Bettingen", "Riehen", "Andere Gemeinde") if field == "GGDENAME" else (2701, 2702, 2703, 9999)
                buildings = [(index, 1004, municipality) for index, municipality in enumerate(municipalities, 1)]
                buildings.append((5, 1005, municipalities[0]))
                entrances = [(1, "Synthetische Postgasse", "10", "4000"),
                             (1, "Synthetische Postgasse", "10", "4000"),
                             (2, "Synthetische Postgasse", "12", "4126"),
                             (3, "Synthetische Postgasse", "14", "4125"),
                             (4, "Synthetische Postgasse", "10", "4999"),
                             (5, "Synthetische Postgasse", "10", "4888")]
                result = self.read_memory(field, buildings, entrances, {key(number)[:2] for number in ("10", "12", "14")})
                self.assertEqual(result, {key()[:2]: {"4000"}, key("12")[:2]: {"4126"}, key("14")[:2]: {"4125"}})

    def test_exact_street_house_number_and_suffix_only(self):
        rows = [(1, "Synthetische Postgasse", number, postal) for number, postal in
                (("10", "4000"), ("10A", "4001"), ("10.1", "4002"), ("100", "4003"))]
        rows.append((1, "Synthetische Anderegasse", "10", "4004"))
        for number, postal in (("10", "4000"), ("10a", "4001"), ("10.1", "4002")):
            with self.subTest(number=number):
                self.assertEqual(self.read_memory("GGDE", [(1, 1004, 2701)], rows, {key(number)[:2]}),
                                 {key(number)[:2]: {postal}})

    def test_multiple_distinct_postals_and_duplicate_egids(self):
        rows = [(1, "Synthetische Postgasse", "10", "4000"), (2, "Synthetische Postgasse", "10", "4000"),
                (2, "Synthetische Postgasse", "10", "4001")]
        result = self.read_memory("GGDE", [(1, 1004, 2701), (2, 1004, 2701)], rows)
        self.assertEqual(result, {key()[:2]: {"4000", "4001"}})

    def test_foreign_only_or_missing_postal_do_not_supply_candidates(self):
        rows = [(1, "Synthetische Postgasse", "10", "4000"), (2, "Synthetische Postgasse", "10", None)]
        self.assertEqual(self.read_memory("GGDE", [(1, 1004, 9999), (2, 1004, 2701)], rows), {})

    def test_missing_municipality_information_is_not_treated_as_basel_stadt(self):
        with self.assertRaisesRegex(ValueError, "GWR-Gemeindeangabe"):
            self.read_memory(None, [(1, 1004)], [(1, "Synthetische Postgasse", "10", "4000")])

    def test_no_requested_addresses_does_not_open_a_database(self):
        with patch.object(matching.sqlite3, "connect", side_effect=AssertionError("Kein Zugriff ohne no_match")):
            self.assertEqual(matching.read_postal_candidates(ROOT / "synthetic-not-created.sqlite", set()), {})


if __name__ == "__main__":
    unittest.main()

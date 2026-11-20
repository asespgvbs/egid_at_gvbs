"""Ausschliesslich selbst erzeugte synthetische Daten im Arbeitsspeicher."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from egid_match.zuordnung.store import ConflictError, FINISHED, ReviewError, ReviewStore, prepare_rows, read_review_excel
from egid_match.zuordnung.geo import DEFAULTS, GeoBS, valid_geometry, validate_config


HEADERS = ["GVBSID", "Zweckbestimmung", "Strasse", "Hausnummer", "Postleitzahl", "EGID-Kandidaten", "EGID mit Hausnummernzusatz", "EGRID-Kandidaten", "Originalwert"]
VALUES = [
    ["SYNTHETIC-1", "Synthetisches Wohnhaus", "Teststrasse", "10", "0000", "101", "102", "CH-SYNTHETIC-1", "0012"],
    ["SYNTHETIC-2", "Synthetische Garage", "Teststrasse", "10a", "0000", "102", "", "CH-SYNTHETIC-1", 0],
    ["SYNTHETIC-3", "Synthetischer Zweck", "Teststrasse", "20", "0000", "103", "", "CH-SYNTHETIC-2", False],
]


class MemoryStore(ReviewStore):
    """Echte SQLite-Transaktionen, aber keine Datei und kein Dateisystemzugriff."""
    def __init__(self, path, connection=None):
        super().__init__(path)
        self.memory = connection if connection is not None else sqlite3.connect(":memory:")
        self.memory.row_factory = sqlite3.Row
        self.memory.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def connection(self, write=False):
        try:
            if write:
                self.memory.execute("BEGIN IMMEDIATE")
            yield self.memory
            if write:
                self.memory.commit()
            elif self.memory.in_transaction:
                self.memory.rollback()
        except BaseException:
            if self.memory.in_transaction:
                self.memory.rollback()
            raise


class SyntheticMemory(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT / "synthetic_not_created"
        self.memory_stores = []

    def tearDown(self):
        for store in self.memory_stores:
            store.memory.close()

    def empty_store(self, path=None):
        store = MemoryStore(path or self.folder / "synthetic.sqlite")
        self.memory_stores.append(store)
        store.open()
        return store

    def store(self):
        store = self.empty_store()
        store.import_rows(HEADERS, VALUES, automatic_egids=set())
        return store


class StoreTests(SyntheticMemory):
    def matching_workbook(self, automatic_rows):
        from openpyxl import Workbook
        workbook = Workbook()
        workbook.active.title = "review_address_suffix"
        workbook.active.append(HEADERS)
        for values in VALUES:
            workbook.active.append(values)
        matching_sheet = workbook.create_sheet("Matching")
        matching_sheet.append(["EGID", "Automatische Zuordnung", "Matching-Kategorie"])
        for row in automatic_rows:
            matching_sheet.append(row)
        self.addCleanup(workbook.close)
        return workbook

    def test_full_matching_import_persists_global_automatic_locks(self):
        workbook = self.matching_workbook([[101, "Ja", "perfect_match"], [999, "Ja", "address_suffix_pair_ge4"],
                                          [None, "Nein", "review_address_suffix"]])
        store = self.empty_store()
        with patch("egid_match.zuordnung.store.load_workbook", return_value=workbook):
            self.assertEqual(store.import_excel(self.folder / "synthetic.xlsx"), 3)
        self.assertEqual(store.automatic_egids(), {"101", "999"})
        reopened = MemoryStore(store.path, connection=store.memory)
        reopened.open()
        self.assertEqual(reopened.automatic_egids(), {"101", "999"})

    def test_automatic_locks_survive_reimport_and_export_round_trip(self):
        store = self.store()
        store.import_rows(HEADERS, VALUES, automatic_egids={"101"})
        store.import_rows(HEADERS, VALUES, automatic_egids={"999"})
        self.assertEqual(store.automatic_egids(), {"101", "999"})
        workbook = store.export_workbook()
        self.addCleanup(workbook.close)
        self.assertEqual(list(workbook["Automatische Zuordnungen"].values), [("EGID",), ("101",), ("999",)])
        second = self.empty_store(self.folder / "synthetic-second.sqlite")
        with patch("egid_match.zuordnung.store.load_workbook", return_value=workbook):
            second.import_excel(self.folder / "synthetic-export.xlsx")
        self.assertEqual(second.automatic_egids(), {"101", "999"})

    def test_automatic_lock_rejects_forged_allowed_candidates_and_rolls_back_batch(self):
        store = self.store()
        store.import_rows(HEADERS, VALUES, automatic_egids={"102"})
        before = store.records()
        with self.assertRaisesRegex(ReviewError, "automatisch zugeteilt"):
            store.save([
                {"gvbsid": "SYNTHETIC-1", "version": before[0]["version"], "assigned": ["101"]},
                {"gvbsid": "SYNTHETIC-2", "version": before[1]["version"], "assigned": ["102"]},
            ], {"101", "102"})
        self.assertEqual(store.records(), before)

    def test_unknown_automatic_assignments_block_saving_and_incomplete_excel_import(self):
        store = self.empty_store()
        store.import_rows(HEADERS, VALUES)
        self.assertIsNone(store.automatic_egids())
        with self.assertRaisesRegex(ReviewError, "Matching-Datei"):
            store.save([{"gvbsid": "SYNTHETIC-1", "version": 1, "assigned": []}], {"101"})
        workbook = self.matching_workbook([])
        del workbook["Matching"]
        before = store.records()
        with patch("egid_match.zuordnung.store.load_workbook", return_value=workbook), self.assertRaises(ReviewError):
            store.import_excel(self.folder / "synthetic-incomplete.xlsx")
        self.assertEqual(store.records(), before)
        self.assertIsNone(store.automatic_egids())

    def test_invalid_matching_locks_do_not_change_records_or_metadata(self):
        store = self.store()
        before = store.records()
        for row in ([101, "Nein", "perfect_match"], [None, "Ja", "perfect_match"],
                    [101, "Ja", "review_address_suffix"], ["=SYNTHETIC()", "Ja", "perfect_match"]):
            with self.subTest(row=row):
                workbook = self.matching_workbook([row])
                with patch("egid_match.zuordnung.store.load_workbook", return_value=workbook), self.assertRaises(ReviewError):
                    store.import_excel(self.folder / "synthetic-invalid.xlsx")
                self.assertEqual(store.records(), before)
                self.assertEqual(store.automatic_egids(), set())

    def test_import_preserves_existing_manual_assignment_but_blocks_resaving_conflict(self):
        store = self.store()
        store.save([{"gvbsid": "SYNTHETIC-1", "version": 1, "assigned": ["101"]}], {"101"})
        store.import_rows(HEADERS, VALUES, automatic_egids={"101"})
        record = store.records()[0]
        self.assertEqual(record["assigned"], ["101"])
        with self.assertRaises(ReviewError):
            store.save([{"gvbsid": record["gvbsid"], "version": record["version"], "assigned": ["101"]}], {"101"})
        store.save([{"gvbsid": record["gvbsid"], "version": record["version"], "assigned": []}], set())
        self.assertEqual(store.records()[0]["assigned"], [])

    def test_new_database_never_overwrites_existing_file(self):
        path = self.folder / "existing.sqlite"
        with patch.object(Path, "open", side_effect=FileExistsError) as exclusive_open, self.assertRaises(FileExistsError):
            ReviewStore.create(path)
        exclusive_open.assert_called_once_with("xb")

    def test_missing_database_is_not_created_by_open(self):
        path = self.folder / "missing.sqlite"
        with patch("egid_match.zuordnung.store.sqlite3.connect", side_effect=sqlite3.OperationalError("Synthetisch nicht vorhanden")) as connect, self.assertRaises(sqlite3.Error):
            ReviewStore(path).open()
        self.assertTrue(connect.call_args.args[0].endswith("?mode=rw"))

    def test_foreign_database_is_not_modified(self):
        path = self.folder / "foreign.sqlite"
        store = MemoryStore(path)
        self.memory_stores.append(store)
        connection = store.memory
        connection.execute("CREATE TABLE synthetic_other_app (value TEXT)")
        connection.execute("INSERT INTO synthetic_other_app VALUES ('SYNTHETIC')")
        connection.commit()
        with self.assertRaises(ReviewError):
            store.open()
        self.assertEqual([row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")], ["synthetic_other_app"])

    def test_reimport_is_idempotent_and_preserves_manual_decisions(self):
        store = self.store()
        first = store.records()[0]
        store.save([{"gvbsid": first["gvbsid"], "version": first["version"], "status": "Abgeschlossen", "comment": "Synthetisch bestätigt", "assigned": ["101", "102"]}], {"101", "102"})
        store.import_rows(HEADERS, VALUES)
        rows = store.records()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["status"], "Abgeschlossen")
        self.assertEqual(rows[0]["comment"], "Synthetisch bestätigt")
        self.assertEqual(rows[0]["assigned"], ["101", "102"])
        reopened = MemoryStore(store.path, connection=store.memory)
        reopened.open()
        self.assertEqual(reopened.records()[0]["assigned"], ["101", "102"])

    def test_many_to_many_relationships_and_per_gvbs_status(self):
        store = self.store()
        rows = store.records()
        store.save([
            {"gvbsid": rows[0]["gvbsid"], "version": 1, "status": "Abgeschlossen", "assigned": ["101", "102"]},
            {"gvbsid": rows[1]["gvbsid"], "version": 1, "status": "Unklar", "assigned": ["102"]},
            {"gvbsid": rows[2]["gvbsid"], "version": 1, "status": "Keine Zuordnung möglich", "assigned": []},
        ], {"101", "102", "103"})
        self.assertEqual(store.progress(), {"total": 3, "completed": 1, "impossible": 1, "special": 0, "remaining": 1})
        rows = store.records()
        self.assertEqual(rows[1]["assigned"], ["102"])
        store.save([{"gvbsid": rows[0]["gvbsid"], "version": rows[0]["version"], "status": "Zurückgestellt", "assigned": ["102"]}], {"102"})
        self.assertEqual(store.progress()["remaining"], 2)

    def test_batch_conflict_rolls_back_all_changes(self):
        store = self.store()
        with self.assertRaises(ConflictError):
            store.save([
                {"gvbsid": "SYNTHETIC-1", "version": 1, "status": "Unklar", "assigned": ["101"]},
                {"gvbsid": "SYNTHETIC-2", "version": 999, "status": "Unklar", "assigned": ["102"]},
            ], {"101", "102"})
        self.assertTrue(all(row["status"] == "Offen" and row["version"] == 1 and not row["assigned"] for row in store.records()))

    def test_invalid_decisions_do_not_modify_records(self):
        store = self.store()
        for status, assigned in (("Keine Zuordnung möglich", ["101"]), ("Unbekannt", []), ("Offen", ["999"])):
            with self.subTest(status=status, assigned=assigned), self.assertRaises(ReviewError):
                store.save([{"gvbsid": "SYNTHETIC-1", "version": 1, "status": status, "assigned": assigned}], {"101"})
        self.assertEqual(store.records()[0]["version"], 1)

    def test_special_status_persists_and_exports_separately_from_open_and_completed(self):
        store = self.store()
        store.save([
            {"gvbsid": "SYNTHETIC-1", "version": 1, "status": "Sonderfall", "assigned": []},
            {"gvbsid": "SYNTHETIC-2", "version": 1, "status": "Abgeschlossen", "assigned": []},
        ], set())
        self.assertEqual(store.progress(), {"total": 3, "completed": 1, "impossible": 0, "special": 1, "remaining": 1})
        store.import_rows(HEADERS, VALUES)
        reopened = MemoryStore(store.path, connection=store.memory)
        reopened.open()
        self.assertEqual(reopened.records()[0]["status"], "Sonderfall")
        workbook = store.export_workbook()
        try:
            self.assertEqual([row[0] for row in list(workbook["Sonderfälle"].values)[1:]], ["SYNTHETIC-1"])
            self.assertEqual([row[0] for row in list(workbook["Abgeschlossene Fälle"].values)[1:]], ["SYNTHETIC-2"])
            self.assertEqual([row[0] for row in list(workbook["Offene Fälle"].values)[1:]], ["SYNTHETIC-3"])
            self.assertEqual(list(workbook["Sonderfälle"].values)[1][-3], "Sonderfall")
        finally:
            workbook.close()

    def test_invalid_import_is_atomic(self):
        store = self.store()
        bad = [list(VALUES[0]), list(VALUES[0])]
        with self.assertRaises(ReviewError):
            store.import_rows(HEADERS, bad)
        self.assertEqual(len(store.records()), 3)
        self.assertTrue(all(row["version"] == 1 for row in store.records()))

    def test_original_values_and_dates_survive_export(self):
        store = self.store()
        headers = [*HEADERS, "Datum", "Zeitpunkt", "Dauer", "Formel"]
        values = [*VALUES[0], date(2020, 1, 2), datetime(2020, 1, 2, 3, 4), timedelta(hours=2), "=1+2"]
        store.import_rows(headers, [values])
        workbook = store.export_workbook()
        try:
            self.assertEqual(workbook.sheetnames, ["review_address_suffix", "Zuordnungen", "Offene Fälle", "Sonderfälle", "Abgeschlossene Fälle", "Automatische Zuordnungen"])
            exported = list(workbook.worksheets[0].values)
            self.assertEqual(exported[1][:len(values)], tuple(values))
            self.assertEqual(exported[2][8], 0)
            self.assertEqual(exported[3][8], False)
        finally:
            workbook.close()

    def test_export_includes_finished_pending_relations_and_purpose(self):
        store = self.store()
        store.save([
            {"gvbsid": "SYNTHETIC-1", "version": 1, "status": "Abgeschlossen", "assigned": ["101", "102"], "comment": "=SYNTHETIC()"},
            {"gvbsid": "SYNTHETIC-2", "version": 1, "status": "Keine Zuordnung möglich", "assigned": []},
        ], {"101", "102"})
        workbook = store.export_workbook()
        try:
            self.assertEqual(workbook.worksheets[0].max_row, 4)
            relations = list(workbook["Zuordnungen"].values)
            self.assertEqual(len(relations), 3)
            self.assertEqual(relations[1][1], "Synthetisches Wohnhaus")
            self.assertEqual([row[0] for row in list(workbook["Offene Fälle"].values)[1:]], ["SYNTHETIC-3"])
            self.assertEqual(workbook["Zuordnungen"]["E2"].data_type, "s")
        finally:
            workbook.close()

    def test_synthetic_workbook_import_uses_required_sheet_and_closes(self):
        from openpyxl import Workbook
        path = self.folder / "synthetic.xlsx"
        workbook = Workbook()
        workbook.active.title = "review_address_suffix"
        workbook.active.append(HEADERS)
        for values in VALUES:
            workbook.active.append(values)
        workbook.create_sheet("Matching").append(["EGID", "Automatische Zuordnung", "Matching-Kategorie"])
        store = self.empty_store()
        with patch("egid_match.zuordnung.store.load_workbook", return_value=workbook):
            self.assertEqual(store.import_excel(path), 3)
        self.assertEqual(store.records()[0]["raw"]["Originalwert"], "0012")
        fake = Mock()
        fake.sheetnames = ["SynthetischFalschesBlatt"]
        with patch("egid_match.zuordnung.store.load_workbook", return_value=fake), self.assertRaises(ReviewError):
            read_review_excel(path)
        fake.close.assert_called_once()


def geo_config():
    return {**DEFAULTS, "parcel_url": "https://synthetic.geo.bs.ch/parcels/items", "parcel_egrid": "egrid", "parcel_mode": "ogc",
            "parcel_section": "section", "parcel_number": "parcel_number", "parcel_extent": "", "parcel_crs": "CRS84",
            "building_url": "https://synthetic.geo.bs.ch/buildings/items", "building_egrid": "egrid", "building_egid": "egid",
            "building_mode": "ogc", "building_crs": "CRS84",
            "building_gstat": "gstat", "building_street": "street", "building_number": "number", "building_postal": "postal"}


POLYGON = {"type": "Polygon", "coordinates": [[[7.5, 47.5], [7.6, 47.5], [7.6, 47.6], [7.5, 47.5]]]}


def feature(properties, geometry=POLYGON):
    return {"type": "Feature", "properties": {"section": "SYNTHETIC", "parcel_number": "1", **properties}, "geometry": geometry}


class GeoTests(unittest.TestCase):
    def test_unconfigured_service_never_uses_network(self):
        fetch = Mock()
        value = GeoBS({"parcel_url": "", "building_url": ""}, fetch).context(["CH-SYNTHETIC-1"], ["101"])
        self.assertTrue(value["warnings"])
        fetch.assert_not_called()

    def test_only_confirmed_egrid_relationships_and_existing_buildings(self):
        responses = [
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
            {"type": "FeatureCollection", "features": [
                feature({"egrid": "CH-SYNTHETIC-1", "egid": 101, "gstat": 1004, "street": "PublicTest", "number": "1", "postal": "0000"}),
                feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004}),
                feature({"egrid": "CH-SYNTHETIC-1", "egid": 666, "gstat": 1005}),
            ]},
        ]
        fetch = Mock(side_effect=responses)
        value = GeoBS(geo_config(), fetch).context(["CH-SYNTHETIC-1"], ["101"])
        self.assertEqual({row["egid"] for row in value["buildings"]}, {"101", "999"})
        self.assertEqual(len(value["parcels"]), 1)
        for call in fetch.call_args_list:
            query = parse_qs(urlsplit(call.args[0]).query)
            self.assertEqual(query["filter"], ["egrid = 'CH-SYNTHETIC-1'"])
            self.assertNotIn("SYNTHETIC-1 –", call.args[0])

    def test_ambiguous_parcel_does_not_invent_relationships(self):
        fetch = Mock(return_value={"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"}), feature({"egrid": "CH-SYNTHETIC-1"})]})
        value = GeoBS(geo_config(), fetch).context(["CH-SYNTHETIC-1"], ["101"])
        self.assertEqual(value["parcels"], [])
        self.assertEqual(value["buildings"], [])
        self.assertTrue(value["warnings"])

    def test_missing_relationship_field_is_reported(self):
        config = geo_config()
        config["building_egrid"] = ""
        config["building_mode"] = "ods"
        fetch = Mock(return_value={"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]})
        value = GeoBS(config, fetch).context(["CH-SYNTHETIC-1"], ["101"])
        self.assertEqual(value["buildings"], [])
        self.assertEqual(value["sources"]["buildings"]["code"], "not_configured")

    def test_nonpublic_urls_and_filter_injection_are_rejected(self):
        for url in ("http://synthetic.bs.ch/items", "https://example.com/items", "https://user:password@synthetic.bs.ch/items", "https://127.0.0.1/items"):
            with self.subTest(url=url), self.assertRaises(ReviewError):
                validate_config({**geo_config(), "parcel_url": url})
        fetch = Mock()
        value = GeoBS(geo_config(), fetch).context(["CH' OR 1=1"], [])
        self.assertEqual(value["sources"]["parcels"]["code"], "invalid")
        fetch.assert_not_called()

    def test_wfs_uses_encoded_fes_filter_and_explicit_crs84(self):
        config = {**geo_config(), "parcel_mode": "wfs", "parcel_layer": "synthetic:parcels"}
        fetch = Mock(return_value={"type": "FeatureCollection", "features": []})
        GeoBS(config, fetch).features("parcel", "egrid", "CH-SYNTHETIC-1")
        query = parse_qs(urlsplit(fetch.call_args.args[0]).query)
        self.assertIn("PropertyIsEqualTo", query["filter"][0])
        self.assertEqual(query["srsName"], ["urn:ogc:def:crs:OGC:1.3:CRS84"])

    def test_projected_geometries_and_truncated_results_are_not_accepted(self):
        self.assertFalse(valid_geometry({"type": "Point", "coordinates": [2600000, 1200000]}))
        fetch = Mock(return_value={"type": "FeatureCollection", "features": [{}] * 1000})
        with self.assertRaises(ReviewError):
            GeoBS(geo_config(), fetch).features("parcel", "egrid", "CH-SYNTHETIC-1")


if __name__ == "__main__":
    unittest.main()

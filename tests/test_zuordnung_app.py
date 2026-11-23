"""Lokale HTTP-Tests mit synthetischen Daten und vollständig ersetzten Geodiensten."""

from pathlib import Path
from datetime import datetime, timedelta, timezone
import io
import json
import importlib.util
import sqlite3
import sys
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import Mock, patch
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from test_zuordnung_store import HEADERS, VALUES, SyntheticMemory, feature, geo_config
from egid_match.zuordnung.app import NativeDialogs, create_app, request_handler
from egid_match.zuordnung.store import ReviewError, ReviewStore, prepare_rows


class MemorySocket:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, *arguments):
        return self.input

    def sendall(self, payload):
        self.output.write(payload)


class LocalClient:
    """Den echten HTTP-Handler ohne Serverstart oder Netzwerk im Speicher prüfen."""
    def __init__(self, app):
        self.app = app

    def request(self, method, target, json_value=None, headers=None, query_string=None):
        if query_string:
            target += "?" + urlencode(query_string)
        payload = json.dumps(json_value).encode() if json_value is not None else b""
        actual_headers = {"Host": "localhost", "Content-Length": str(len(payload)), **(headers or {})}
        text = f"{method} {target} HTTP/1.0\r\n" + "".join(f"{key}: {value}\r\n" for key, value in actual_headers.items())
        socket = MemorySocket(text.encode() + b"\r\n" + payload)
        request_handler(self.app)(socket, ("127.0.0.1", 12345), SimpleNamespace())
        head, body = socket.output.getvalue().split(b"\r\n\r\n", 1)
        lines = head.decode().split("\r\n")
        response_headers = dict(line.split(": ", 1) for line in lines[1:])
        content = body.decode("utf-8")
        return SimpleNamespace(status_code=int(lines[0].split()[1]), text=content,
                               json=json.loads(content) if "application/json" in response_headers.get("Content-Type", "") else None,
                               headers=response_headers)

    def get(self, target, **kwargs):
        return self.request("GET", target, **kwargs)

    def post(self, target, json=None, **kwargs):
        return self.request("POST", target, json_value=json, **kwargs)


class AppTests(SyntheticMemory):
    def setUp(self):
        super().setUp()
        self.dialogs = Mock()
        self.fetch = Mock(side_effect=AssertionError("Kein echter Netzwerkzugriff in Tests"))
        self.database = self.store()
        def find_store(path):
            if Path(path).resolve() != self.database.path:
                raise OSError("Synthetische Datenbank fehlt")
            return self.database
        factory = Mock(side_effect=find_store)
        factory.create.side_effect = FileExistsError
        store_patch = patch("egid_match.zuordnung.app.ReviewStore", factory)
        store_patch.start()
        self.addCleanup(store_patch.stop)
        preference_patch = patch("egid_match.zuordnung.app.ReviewSession.remember")
        preference_patch.start()
        self.addCleanup(preference_patch.stop)
        address_patch = patch("egid_match.zuordnung.app.read_gwr_addresses", return_value={})
        self.gwr_addresses = address_patch.start()
        self.addCleanup(address_patch.stop)
        volume_patch = patch("egid_match.zuordnung.app.read_gwr_volumes", return_value={})
        self.gwr_volumes = volume_patch.start()
        self.addCleanup(volume_patch.stop)
        self.app = create_app(self.folder / "preferences.json", self.dialogs, resume=False, geo_fetcher=self.fetch)
        self.app.token = "synthetic-local-test-token"
        self.client = LocalClient(self.app)
        self.headers = {"X-Review-Token": "synthetic-local-test-token"}

    def post(self, path, data=None, **kwargs):
        return self.client.post(path, json=data if data is not None else {}, headers=self.headers, **kwargs)

    def select(self, activate=False):
        self.dialogs.choose.return_value = str(self.database.path)
        response = self.post("/api/database/select")
        self.assertEqual(response.status_code, 200)
        if activate:
            self.assertEqual(self.post("/api/activate").status_code, 200)
        return response.json

    def decision(self, status="Abgeschlossen", assigned=None, version=1, gvbsid="SYNTHETIC-1"):
        case = self.app.session.case("SYNTHETIC-1")
        decisions = []
        for record in case["records"]:
            if record["gvbsid"] == "SYNTHETIC-1":
                decisions.append({"gvbsid": gvbsid, "version": version, "status": status,
                                  "assigned": assigned if assigned is not None else ["101", "102"],
                                  "comment": "Synthetischer Kommentar"})
            else:
                decisions.append({"gvbsid": record["gvbsid"], "version": record["version"], "status": status,
                                  "assigned": record["assigned"], "comment": record["comment"]})
        return {"selected": "SYNTHETIC-1", "package_id": case["package_id"], "decisions": decisions}

    def test_two_stage_gating_and_existing_data_require_explicit_activation(self):
        for path, method in (("/api/queue", "get"), ("/api/import", "post"), ("/api/save", "post"), ("/api/export", "post"), ("/api/geo", "post")):
            response = self.client.get(path) if method == "get" else self.post(path)
            self.assertEqual(response.status_code, 400, path)
        self.dialogs.choose.assert_not_called()
        selected = self.select()
        self.assertFalse(selected["active"])
        self.assertEqual(selected["progress"]["total"], 3)
        self.assertEqual(self.client.get("/api/queue").status_code, 400)
        self.post("/api/activate")
        self.assertEqual(len(self.client.get("/api/queue").json["records"]), 2)

    def test_unassigned_count_without_database_and_in_empty_store_is_zero(self):
        self.assertEqual(self.client.get("/api/state").json["unassigned_count"], 0)
        self.database = self.empty_store(self.folder / "synthetic-empty.sqlite")
        self.select()
        self.assertEqual(self.client.get("/api/state").json["unassigned_count"], 0)
        self.fetch.assert_not_called()

    def test_unassigned_count_uses_saved_assignments_and_updates_after_saving(self):
        self.select(activate=True)
        self.assertEqual(self.client.get("/api/state").json["unassigned_count"], 3)
        response = self.post("/api/save", self.decision(assigned=["101", "102"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["unassigned_count"], 2)
        self.assertEqual(self.client.get("/api/state").json["unassigned_count"], 2)
        response = self.post("/api/save", self.decision("Sonderfall", [], version=2))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["unassigned_count"], 3)
        self.fetch.assert_not_called()

    def test_unassigned_count_is_independent_of_status_and_queue_filters(self):
        self.database.save([
            {"gvbsid": "SYNTHETIC-1", "version": 1, "status": "Abgeschlossen", "assigned": ["101", "102"]},
            {"gvbsid": "SYNTHETIC-2", "version": 1, "status": "Sonderfall", "assigned": []},
            {"gvbsid": "SYNTHETIC-3", "version": 1, "status": "Keine Zuordnung möglich", "assigned": []},
        ], {"101", "102"})
        self.select(activate=True)
        for view in ("open", "special", "completed"):
            for ratio in ("all", "equal", "different"):
                self.assertEqual(self.client.get("/api/queue", query_string={"view": view, "ratio": ratio}).status_code, 200)
                self.assertEqual(self.client.get("/api/state").json["unassigned_count"], 2)
        self.fetch.assert_not_called()

    def test_unassigned_count_deduplicates_gvbsids_in_multiple_egrid_packages(self):
        values = [list(row) for row in VALUES]
        values[1][7] = "CH-SYNTHETIC-1, CH-SYNTHETIC-2"
        self.database.import_rows(HEADERS, values, automatic_egids={"999"})
        self.select(activate=True)
        queue = self.client.get("/api/queue").json["records"]
        self.assertEqual(sum(row["record_count"] for row in queue), 4)
        self.assertEqual(self.client.get("/api/state").json["unassigned_count"], 3)
        self.fetch.assert_not_called()

    def test_assignment_counts_without_database_or_records_are_zero(self):
        expected = {ratio: {"total": 0, "unassigned": 0} for ratio in ("all", "equal", "different")}
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"], expected)
        self.database = self.empty_store(self.folder / "synthetic-empty.sqlite")
        self.select()
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"], expected)
        self.fetch.assert_not_called()

    def test_assignment_counts_follow_ratio_but_ignore_queue_status(self):
        values = [list(row) for row in VALUES]
        values[0][6] = "102,104"  # Pakete 2:3 und 1:1.
        self.database.import_rows(HEADERS, values)
        self.database.save([
            {"gvbsid": "SYNTHETIC-1", "version": 2, "status": "Abgeschlossen", "assigned": ["101", "102"]},
            {"gvbsid": "SYNTHETIC-2", "version": 2, "status": "Sonderfall", "assigned": []},
            {"gvbsid": "SYNTHETIC-3", "version": 2, "status": "Keine Zuordnung möglich", "assigned": []},
        ], {"101", "102"})
        self.select(activate=True)
        expected = {"all": {"total": 3, "unassigned": 2}, "equal": {"total": 1, "unassigned": 1},
                    "different": {"total": 2, "unassigned": 1}}
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"], expected)
        for view in ("open", "special", "completed"):
            for ratio in expected:
                response = self.client.get("/api/queue", query_string={"view": view, "ratio": ratio})
                self.assertEqual(response.json["assignment_counts"], expected)
        self.fetch.assert_not_called()
        self.gwr_addresses.assert_not_called()
        self.gwr_volumes.assert_not_called()

    def test_assignment_counts_update_after_saving_or_removing_assignments(self):
        self.select(activate=True)
        response = self.post("/api/save", self.decision(assigned=["101", "102"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["assignment_counts"], {
            "all": {"total": 3, "unassigned": 2}, "equal": {"total": 3, "unassigned": 2},
            "different": {"total": 0, "unassigned": 0}})
        response = self.post("/api/save", self.decision("Sonderfall", [], version=2))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["assignment_counts"]["equal"], {"total": 3, "unassigned": 3})
        self.fetch.assert_not_called()

    def test_assignment_counts_deduplicate_shared_gvbsids_within_each_ratio(self):
        values = [list(row) for row in VALUES]
        values[1][7] = "CH-SYNTHETIC-1, CH-SYNTHETIC-2, CH-SYNTHETIC-3"
        values[2][7] = "CH-SYNTHETIC-2, CH-SYNTHETIC-3"
        values.append(["SYNTHETIC-4", *VALUES[0][1:5], "104", "", "CH-SYNTHETIC-1", ""])
        self.database.import_rows(HEADERS, values)
        self.select(activate=True)
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"]["equal"],
                         {"total": 4, "unassigned": 4})
        values[0][6] = "102,105"
        self.database.import_rows(HEADERS, values)
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"], {
            "all": {"total": 4, "unassigned": 4}, "equal": {"total": 2, "unassigned": 2},
            "different": {"total": 3, "unassigned": 3}})
        self.fetch.assert_not_called()

    def test_assignment_counts_include_packages_without_egid(self):
        values = [list(row) for row in VALUES]
        values[2][5:8] = ["", "", ""]
        self.database.import_rows(HEADERS, values)
        self.select(activate=True)
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"], {
            "all": {"total": 3, "unassigned": 3}, "equal": {"total": 2, "unassigned": 2},
            "different": {"total": 1, "unassigned": 1}})
        self.fetch.assert_not_called()

    def test_assignment_counts_follow_cached_geodata_and_expiry(self):
        self.select(activate=True)
        self.app.session.geo_cache["SYNTHETIC-1"] = {
            "package_id": "egrid:CH-SYNTHETIC-1", "sources": {}, "parcels": [],
            "buildings": [{"egid": "999", "egrid": "CH-SYNTHETIC-1", "assignable": True}]}
        expected = {"all": {"total": 3, "unassigned": 3}, "equal": {"total": 1, "unassigned": 1},
                    "different": {"total": 2, "unassigned": 2}}
        for ratio, total in (("equal", 1), ("different", 2)):
            response = self.client.get("/api/queue", query_string={"ratio": ratio})
            self.assertEqual(response.json["assignment_counts"], expected)
            self.assertEqual(sum(row["gvbsid_count"] for row in response.json["records"]), total)
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"], expected)
        self.app.session.geo_cache["SYNTHETIC-1"]["sources"] = {"buildings": {
            "code": "complete", "fetched_at": (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()}}
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"], {
            "all": {"total": 3, "unassigned": 3}, "equal": {"total": 3, "unassigned": 3},
            "different": {"total": 0, "unassigned": 0}})
        self.fetch.assert_not_called()

    def test_status_queue_search_and_reopening_completed_cases(self):
        self.select(activate=True)
        response = self.post("/api/save", self.decision())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["progress"]["completed"], 2)
        self.assertNotIn("SYNTHETIC-1", [row["gvbsid"] for row in self.client.get("/api/queue").json["records"]])
        reopened = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertEqual(reopened["records"][0]["assigned"], ["101", "102"])
        self.assertEqual(reopened["records"][0]["status"], "Abgeschlossen")
        self.assertEqual(self.post("/api/save", self.decision("Unklar", ["102"], version=2)).status_code, 200)
        self.assertEqual(len(self.client.get("/api/queue").json["records"]), 2)
        self.assertEqual(self.post("/api/save", self.decision("Keine Zuordnung möglich", [], version=3)).status_code, 200)
        self.assertEqual(self.client.get("/api/state").json["progress"]["impossible"], 2)

    def test_special_and_completed_queues_follow_status_transitions_without_egid(self):
        self.select(activate=True)
        response = self.post("/api/save", self.decision("Sonderfall", [], version=1))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["progress"]["special"], 2)
        self.assertEqual(response.json["progress"]["remaining"], 1)
        self.assertEqual([row["gvbsid"] for row in self.client.get("/api/queue?view=special").json["records"]], ["SYNTHETIC-1"])
        self.assertNotIn("SYNTHETIC-1", [row["gvbsid"] for row in self.client.get("/api/queue").json["records"]])
        self.assertEqual(self.client.get("/api/queue?view=completed").json["records"], [])
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertEqual(case["records"][0]["status"], "Sonderfall")
        response = self.post("/api/save", self.decision("Abgeschlossen", [], version=2))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["progress"]["special"], 0)
        self.assertEqual(response.json["progress"]["completed"], 2)
        self.assertEqual(self.client.get("/api/queue?view=special").json["records"], [])
        self.assertEqual([row["gvbsid"] for row in self.client.get("/api/queue?view=completed").json["records"]], ["SYNTHETIC-1"])
        response = self.post("/api/save", self.decision("Sonderfall", [], version=3))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/queue?view=completed").json["records"], [])

    def test_filtered_queues_keep_package_ids_and_legacy_statuses(self):
        self.select(activate=True)
        self.database.save([
            {"gvbsid": "SYNTHETIC-1", "version": 1, "status": "Sonderfall", "assigned": []},
            {"gvbsid": "SYNTHETIC-2", "version": 1, "status": "Unklar", "assigned": []},
            {"gvbsid": "SYNTHETIC-3", "version": 1, "status": "Keine Zuordnung möglich", "assigned": []},
        ], set())
        special = self.client.get("/api/queue?view=special").json["records"]
        opened = self.client.get("/api/queue?view=open").json["records"]
        completed = self.client.get("/api/queue?view=completed").json["records"]
        self.assertEqual([row["gvbsid"] for row in special], ["SYNTHETIC-1"])
        self.assertEqual(opened, [])
        self.assertEqual([row["gvbsid"] for row in completed], ["SYNTHETIC-3"])
        self.assertEqual(special[0]["record_count"], 2)
        self.assertEqual(special[0]["package_id"], "egrid:CH-SYNTHETIC-1")
        self.assertEqual(self.client.get("/api/queue?view=unknown").status_code, 400)

    def test_ratio_filter_counts_unique_package_ids_and_matches_matrix(self):
        values = [list(row) for row in VALUES]
        values[0][5:7] = ["101,101", "102,102,104"]
        self.database.import_rows(HEADERS, values)
        self.select(activate=True)
        all_rows = self.client.get("/api/queue").json["records"]
        self.assertEqual([(row["gvbsid_count"], row["egid_count"]) for row in all_rows], [(2, 3), (1, 1)])
        for ratio, expected in (("all", ["CH-SYNTHETIC-1", "CH-SYNTHETIC-2"]),
                                ("equal", ["CH-SYNTHETIC-2"]), ("different", ["CH-SYNTHETIC-1"])):
            response = self.client.get("/api/queue", query_string={"ratio": ratio})
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row["egrid"] for row in response.json["records"]], expected)
        for row in all_rows:
            case = self.client.get("/api/case", query_string={"gvbsid": row["gvbsid"], "package_id": row["package_id"]}).json
            self.assertEqual(row["gvbsid_count"], len({record["gvbsid"] for record in case["records"]}))
            self.assertEqual(row["egid_count"], len(case["egids"]))
        self.assertEqual(self.client.get("/api/queue?ratio=unknown").status_code, 400)
        self.fetch.assert_not_called()
        self.gwr_addresses.assert_not_called()
        self.gwr_volumes.assert_not_called()

    def test_equal_ratio_includes_four_to_four_and_automatically_locked_egids(self):
        self.database.import_rows(HEADERS, [
            ["SYNTHETIC-4", *VALUES[0][1:5], "104", "", *VALUES[0][7:]],
            ["SYNTHETIC-5", *VALUES[0][1:5], "105", "", *VALUES[0][7:]],
        ], automatic_egids={"101"})
        self.select(activate=True)
        rows = self.client.get("/api/queue?ratio=equal").json["records"]
        self.assertEqual([(row["gvbsid_count"], row["egid_count"]) for row in rows], [(4, 4), (1, 1)])
        self.assertEqual(self.client.get("/api/queue?ratio=different").json["records"], [])
        case = self.app.session.case("SYNTHETIC-1")
        self.assertIn("101", case["egids"])
        self.assertIn("101", case["blocked_egids"])
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"], {
            "all": {"total": 5, "unassigned": 5}, "equal": {"total": 5, "unassigned": 5},
            "different": {"total": 0, "unassigned": 0}})

    def test_ratio_includes_saved_assignments_outside_imported_candidates(self):
        self.database.save([{"gvbsid": "SYNTHETIC-1", "version": 1, "status": "Offen", "assigned": ["999"]}], {"999"})
        self.select(activate=True)
        rows = self.client.get("/api/queue?ratio=different").json["records"]
        self.assertEqual([(row["egrid"], row["gvbsid_count"], row["egid_count"]) for row in rows],
                         [("CH-SYNTHETIC-1", 2, 3)])
        self.assertIn("999", self.app.session.case("SYNTHETIC-1")["egids"])
        self.assertEqual(self.client.get("/api/state").json["assignment_counts"], {
            "all": {"total": 3, "unassigned": 2}, "equal": {"total": 1, "unassigned": 1},
            "different": {"total": 2, "unassigned": 1}})

    def test_ratio_without_egid_is_unequal(self):
        values = list(VALUES[2])
        values[5:7] = ["", ""]
        self.database.import_rows(HEADERS, [values])
        self.select(activate=True)
        rows = self.client.get("/api/queue?ratio=different").json["records"]
        self.assertEqual([(row["egrid"], row["gvbsid_count"], row["egid_count"]) for row in rows],
                         [("CH-SYNTHETIC-2", 1, 0)])

    def test_ratio_combines_with_status_and_follows_package_status_changes(self):
        values = list(VALUES[0])
        values[6] = "102,104"
        self.database.import_rows(HEADERS, [values])
        self.select(activate=True)
        for view, status in (("special", "Sonderfall"), ("completed", "Abgeschlossen")):
            version = self.database.records()[0]["version"]
            self.assertEqual(self.post("/api/save", self.decision(status, [], version=version)).status_code, 200)
            rows = self.client.get("/api/queue", query_string={"view": view, "ratio": "different"}).json["records"]
            self.assertEqual([row["egrid"] for row in rows], ["CH-SYNTHETIC-1"])
            self.assertEqual(self.client.get("/api/queue", query_string={"view": view, "ratio": "equal"}).json["records"], [])
            self.assertEqual(self.client.get("/api/queue?view=open&ratio=different").json["records"], [])
            self.assertEqual([row["egrid"] for row in self.client.get("/api/queue?view=open&ratio=equal").json["records"]],
                             ["CH-SYNTHETIC-2"])

    def test_ratio_tracks_verified_geodata_on_any_member_and_expires_extra_candidates(self):
        self.database.import_rows(HEADERS, VALUES, automatic_egids={"999"})
        self.select(activate=True)
        self.assertEqual(len(self.client.get("/api/queue?ratio=equal").json["records"]), 2)
        self.app.session.config = geo_config()
        self.fetch.side_effect = [
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004})]},
        ]
        self.assertEqual(self.post("/api/geo", {"selected": "SYNTHETIC-2"}).status_code, 200)
        rows = self.client.get("/api/queue?ratio=different").json["records"]
        self.assertEqual([(row["gvbsid_count"], row["egid_count"]) for row in rows], [(2, 3)])
        for selected in ("SYNTHETIC-1", "SYNTHETIC-2"):
            case = self.app.session.case(selected)
            self.assertEqual(case["egids"], ["101", "102", "999"])
            self.assertIn("999", case["blocked_egids"])
        self.assertEqual(self.fetch.call_count, 2)
        for source in self.app.session.geo_cache["SYNTHETIC-2"]["sources"].values():
            source["fetched_at"] = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        self.assertEqual(self.client.get("/api/queue?ratio=different").json["records"], [])
        self.assertEqual(len(self.client.get("/api/queue?ratio=equal").json["records"]), 2)
        self.assertNotIn("999", self.app.session.case("SYNTHETIC-1")["egids"])
        self.assertEqual(self.fetch.call_count, 2)

    def test_cached_ratio_candidates_are_scoped_to_their_egrid_package(self):
        values = list(VALUES[1])
        values[7] = "CH-SYNTHETIC-1, CH-SYNTHETIC-2"
        self.database.import_rows(HEADERS, [values])
        self.select(activate=True)
        self.app.session.geo_cache["SYNTHETIC-2"] = {
            "package_id": "egrid:CH-SYNTHETIC-1", "parcels": [], "sources": {},
            "buildings": [
                {"egid": "999", "egrid": "CH-SYNTHETIC-1", "assignable": True},
                {"egid": "888", "egrid": "CH-SYNTHETIC-2", "assignable": True},
                {"egid": "777", "egrid": "CH-SYNTHETIC-1", "assignable": False},
            ],
        }
        self.assertEqual([row["egrid"] for row in self.client.get("/api/queue?ratio=equal").json["records"]], ["CH-SYNTHETIC-2"])
        self.assertEqual([row["egrid"] for row in self.client.get("/api/queue?ratio=different").json["records"]], ["CH-SYNTHETIC-1"])
        self.assertEqual(self.app.session.case("SYNTHETIC-1")["egids"], ["101", "102", "999"])
        self.assertEqual(self.app.session.case("SYNTHETIC-3")["egids"], ["102", "103"])
        self.fetch.assert_not_called()

    def test_resolved_geodata_is_counted_only_for_its_own_egrid(self):
        values = list(VALUES[1])
        values[7] = ""
        self.database.import_rows(HEADERS, [values])
        self.select(activate=True)
        self.app.session.geo_cache["SYNTHETIC-2"] = {
            "package_id": "gvbsid:SYNTHETIC-2", "sources": {},
            "parcels": [{"egrid": "CH-SYNTHETIC-1"}, {"egrid": "CH-SYNTHETIC-2"}],
            "buildings": [{"egid": "999", "egrid": "CH-SYNTHETIC-1", "assignable": True}],
        }
        rows = self.client.get("/api/queue").json["records"]
        self.assertEqual([(row["gvbsid_count"], row["egid_count"]) for row in rows], [(2, 3), (2, 2)])
        self.assertEqual([row["egrid"] for row in self.client.get("/api/queue?ratio=equal").json["records"]], ["CH-SYNTHETIC-2"])
        self.assertNotIn("999", self.app.session.case("SYNTHETIC-3")["egids"])
        self.fetch.assert_not_called()

    def test_stale_special_batch_preserves_all_statuses(self):
        self.select(activate=True)
        before = self.database.records()
        payload = {"selected": "SYNTHETIC-1", "decisions": [
            {"gvbsid": "SYNTHETIC-1", "version": 1, "status": "Sonderfall", "assigned": []},
            {"gvbsid": "SYNTHETIC-2", "version": 999, "status": "Sonderfall", "assigned": []},
        ]}
        self.assertEqual(self.post("/api/save", payload).status_code, 409)
        self.assertEqual(self.database.records(), before)
        self.assertEqual(self.database.progress()["special"], 0)

    def test_egrid_actions_cover_all_control_numbers_and_preserve_each_assignment(self):
        headers = [*HEADERS, "Kontrollnummer", "Gebäudenummer"]
        rows = [[*row, f"SYNTHETIC-CONTROL-{index}", 0] for index, row in enumerate(VALUES)]
        self.database.import_rows(headers, rows)
        second = self.database.records()[1]
        self.database.save([{"gvbsid": second["gvbsid"], "version": second["version"], "status": "Offen",
                             "assigned": ["102"], "comment": "Synthetisch erhalten"}], {"102"})
        self.select(activate=True)
        queue = self.client.get("/api/queue").json["records"]
        self.assertEqual(len(queue), 2)
        self.assertEqual(queue[0]["record_count"], 2)
        self.assertEqual(queue[0]["control_numbers"], ["SYNTHETIC-CONTROL-0", "SYNTHETIC-CONTROL-1"])
        version = self.database.records()[0]["version"]
        response = self.post("/api/save", self.decision("Sonderfall", ["101"], version=version))
        self.assertEqual(response.status_code, 200)
        records = self.database.records()
        self.assertEqual([row["status"] for row in records], ["Sonderfall", "Sonderfall", "Offen"])
        self.assertEqual([row["assigned"] for row in records], [["101"], ["102"], []])
        self.assertEqual(records[1]["comment"], "Synthetisch erhalten")
        self.assertEqual(response.json["package_progress"], {"total": 2, "completed": 0, "special": 1, "remaining": 1})
        self.assertEqual(len(self.client.get("/api/queue?view=special").json["records"]), 1)
        response = self.post("/api/save", self.decision("Abgeschlossen", ["101"], version=records[0]["version"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["status"] for row in self.database.records()], ["Abgeschlossen", "Abgeschlossen", "Offen"])
        self.assertEqual(response.json["package_progress"], {"total": 2, "completed": 1, "special": 0, "remaining": 1})

    def test_partial_or_mixed_status_package_save_is_rejected_without_changes(self):
        self.select(activate=True)
        before = self.database.records()
        partial = self.decision("Sonderfall", [])
        partial["decisions"].pop()
        self.assertEqual(self.post("/api/save", partial).status_code, 409)
        mixed = self.decision("Sonderfall", [])
        mixed["decisions"][1]["status"] = "Abgeschlossen"
        self.assertEqual(self.post("/api/save", mixed).status_code, 400)
        self.assertEqual(self.database.records(), before)

    def test_changed_package_membership_rejects_stale_complete_payload(self):
        self.select(activate=True)
        payload = self.decision("Sonderfall", [])
        self.database.import_rows(HEADERS, [["SYNTHETIC-NEW", *VALUES[0][1:]]])
        before = self.database.records()
        self.assertEqual(self.post("/api/save", payload).status_code, 409)
        self.assertEqual(self.database.records(), before)

    def test_new_member_between_request_validation_and_transaction_prevents_partial_save(self):
        self.select(activate=True)
        payload = self.decision("Sonderfall", [])
        save = self.database.save

        def concurrent_import(decisions, allowed_egids, **kwargs):
            self.database.import_rows(HEADERS, [["SYNTHETIC-CONCURRENT", *VALUES[0][1:]]])
            return save(decisions, allowed_egids, **kwargs)

        with patch.object(self.database, "save", side_effect=concurrent_import):
            response = self.post("/api/save", payload)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(all(record["status"] == "Offen" for record in self.database.records()))

    def test_same_parcel_group_is_saved_with_one_shared_status(self):
        self.select(activate=True)
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertEqual([row["gvbsid"] for row in case["records"]], ["SYNTHETIC-1", "SYNTHETIC-2"])
        self.assertEqual(case["records"][0]["purpose"], "Synthetisches Wohnhaus")
        self.assertEqual(case["egids"], ["101", "102"])
        self.assertEqual(self.post("/api/save", self.decision()).status_code, 200)
        self.assertEqual(self.database.records()[1]["status"], "Abgeschlossen")

    def test_queue_packages_keep_interleaved_parcel_members_together(self):
        self.database = self.empty_store(self.folder / "synthetic-packages.sqlite")
        self.database.import_rows(HEADERS, [VALUES[0], VALUES[2], VALUES[1]], automatic_egids=set())
        self.select(activate=True)
        queue = self.client.get("/api/queue").json["records"]
        self.assertEqual([row["gvbsid"] for row in queue], ["SYNTHETIC-1", "SYNTHETIC-3"])
        self.assertEqual([row["package_id"] for row in queue], ["egrid:CH-SYNTHETIC-1", "egrid:CH-SYNTHETIC-2"])
        self.assertEqual([row["package_index"] for row in queue], [0, 1])
        self.assertEqual([row["record_count"] for row in queue], [2, 1])
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-2"}).json
        self.assertEqual(case["package_id"], "egrid:CH-SYNTHETIC-1")
        self.assertEqual([row["gvbsid"] for row in case["records"]], ["SYNTHETIC-1", "SYNTHETIC-2"])

    def test_each_egrid_stays_a_separate_package_when_building_has_several_egrids(self):
        values = [list(row) for row in VALUES]
        values[1][7] = "CH-SYNTHETIC-1, CH-SYNTHETIC-2"
        self.database.import_rows(HEADERS, values)
        self.select(activate=True)
        middle = self.database.records()[1]
        self.database.save([{"gvbsid": "SYNTHETIC-2", "version": middle["version"], "assigned": ["102"]}], {"102"})
        queue = self.client.get("/api/queue").json["records"]
        self.assertEqual([row["package_id"] for row in queue], ["egrid:CH-SYNTHETIC-1", "egrid:CH-SYNTHETIC-2"])
        for number, expected in ((1, ["SYNTHETIC-1", "SYNTHETIC-2"]), (2, ["SYNTHETIC-2", "SYNTHETIC-3"])):
            case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-2", "package_id": f"egrid:CH-SYNTHETIC-{number}"}).json
            self.assertEqual([row["gvbsid"] for row in case["records"]], expected)
            self.assertEqual(case["egrids"], [f"CH-SYNTHETIC-{number}"])

    def test_missing_egrids_produce_individual_packages(self):
        values = [list(row) for row in VALUES]
        for row in values:
            row[7] = ""
        self.database.import_rows(HEADERS, values)
        self.select(activate=True)
        queue = self.client.get("/api/queue").json["records"]
        self.assertEqual(len({row["package_id"] for row in queue}), 3)
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertEqual(len(case["records"]), 1)
        payload = {"selected": case["selected"], "package_id": case["package_id"], "decisions": [
            {"gvbsid": row["gvbsid"], "version": row["version"], "assigned": [], "status": "Sonderfall"}
            for row in case["records"]]}
        self.assertEqual(self.post("/api/save", payload).status_code, 400)
        self.assertTrue(all(row["status"] == "Offen" for row in self.database.records()))

    def test_verified_cached_egrid_updates_packages_but_stale_cache_does_not(self):
        self.select(activate=True)
        self.app.session.geo_cache["SYNTHETIC-3"] = {"synthetic": True}
        context = {"parcels": [{"egrid": "CH-SYNTHETIC-1"}], "buildings": [], "sources": {"parcels": {"stale": False}}}
        with patch("egid_match.zuordnung.app.cached_context", return_value=context):
            queue = self.client.get("/api/queue").json["records"]
            self.assertEqual([row["record_count"] for row in queue], [3, 1])
            case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-3"}).json
            self.assertEqual(len(case["records"]), 3)
        context["sources"]["parcels"]["stale"] = True
        with patch("egid_match.zuordnung.app.cached_context", return_value=context):
            queue = self.client.get("/api/queue").json["records"]
            self.assertEqual(len({row["package_id"] for row in queue}), 2)
            self.assertEqual([row["record_count"] for row in queue], [2, 1])

    def test_automatic_egid_remains_visible_but_cannot_be_assigned(self):
        self.database.import_rows(HEADERS, VALUES, automatic_egids={"101"})
        self.select(activate=True)
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertEqual(case["egids"], ["101", "102"])
        self.assertEqual(case["blocked_egids"], ["101"])
        self.assertEqual(case["assignable_egids"], ["102"])
        self.assertTrue(case["automatic_assignments_loaded"])
        before = self.database.records()
        payload = self.decision(assigned=["101"], version=before[0]["version"])
        response = self.post("/api/save", payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("automatisch zugeteilt", response.json["error"])
        self.assertEqual(self.database.records(), before)

    def test_automatic_parcel_egid_from_geo_service_stays_locked(self):
        self.database.import_rows(HEADERS, VALUES, automatic_egids={"999"})
        self.select(activate=True)
        self.app.session.config = geo_config()
        self.fetch.side_effect = [
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004})]},
        ]
        response = self.post("/api/geo", {"selected": "SYNTHETIC-1"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["buildings"][0]["automatically_assigned"])
        self.assertFalse(response.json["buildings"][0]["assignable"])
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertIn("999", case["egids"])
        self.assertIn("999", case["blocked_egids"])
        self.assertNotIn("999", case["assignable_egids"])
        record = self.database.records()[0]
        self.assertEqual(self.post("/api/save", self.decision(assigned=["999"], version=record["version"])).status_code, 400)

    def test_legacy_database_requires_matching_import_before_assignment(self):
        with self.database.connection(write=True) as connection:
            connection.execute("DELETE FROM review_meta WHERE key='automatic_egids'")
        self.select(activate=True)
        self.assertIn("Matching-Datei", self.client.get("/api/state").json["warning"])
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertFalse(case["automatic_assignments_loaded"])
        self.assertEqual(case["assignable_egids"], [])
        self.assertEqual(self.post("/api/save", self.decision(assigned=[])).status_code, 400)

    def test_save_without_status_completes_decision_and_refreshes_progress_and_queue(self):
        self.select(activate=True)
        payload = self.decision(assigned=["101"])
        del payload["decisions"][0]["status"]
        response = self.post("/api/save", payload)
        self.assertEqual(response.status_code, 200)
        expected = {"total": 3, "completed": 2, "impossible": 0, "special": 0, "remaining": 1}
        self.assertEqual(response.json["progress"], expected)
        self.assertEqual(self.client.get("/api/state").json["progress"], expected)
        self.assertEqual([row["gvbsid"] for row in self.client.get("/api/queue").json["records"]], ["SYNTHETIC-3"])
        rows = self.database.records()
        self.assertEqual(rows[0]["status"], "Abgeschlossen")
        self.assertEqual(rows[0]["assigned"], ["101"])
        self.assertEqual(rows[0]["comment"], "Synthetischer Kommentar")
        self.assertEqual(rows[1]["status"], "Abgeschlossen")
        self.assertEqual(rows[1]["version"], 2)

    def test_save_empty_decision_without_status_completes_case(self):
        self.select(activate=True)
        payload = self.decision(assigned=[])
        del payload["decisions"][0]["status"]
        response = self.post("/api/save", payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["progress"], {"total": 3, "completed": 2, "impossible": 0, "special": 0, "remaining": 1})
        self.assertEqual(self.database.records()[0]["status"], "Abgeschlossen")
        self.assertNotIn("SYNTHETIC-1", [row["gvbsid"] for row in self.client.get("/api/queue").json["records"]])

    def test_previous_open_assignment_is_completed_by_saving_it_again(self):
        self.select(activate=True)
        previous = self.post("/api/save", self.decision("Offen", ["101"]))
        self.assertEqual(previous.json["progress"]["completed"], 0)
        payload = self.decision(assigned=["101"], version=2)
        del payload["decisions"][0]["status"]
        response = self.post("/api/save", payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["progress"]["completed"], 2)
        self.assertEqual(self.database.records()[0]["assigned"], ["101"])

    def test_reopened_decision_updates_counts_when_assignments_are_removed_or_added(self):
        self.select(activate=True)
        for version, assigned, completed, impossible in ((1, ["101"], 2, 0), (2, [], 2, 0), (3, ["102"], 2, 0)):
            payload = self.decision(assigned=assigned, version=version)
            del payload["decisions"][0]["status"]
            response = self.post("/api/save", payload)
            with self.subTest(assigned=assigned):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json["progress"]["completed"], completed)
                self.assertEqual(response.json["progress"]["impossible"], impossible)
                self.assertEqual(response.json["progress"]["remaining"], 1)

    def test_automatic_completion_batch_is_rolled_back_on_conflict(self):
        self.select(activate=True)
        payload = self.decision(assigned=["101"])
        del payload["decisions"][0]["status"]
        payload["decisions"].append({"gvbsid": "SYNTHETIC-2", "version": 999, "assigned": []})
        self.assertEqual(self.post("/api/save", payload).status_code, 409)
        self.assertEqual(self.client.get("/api/state").json["progress"], {"total": 3, "completed": 0, "impossible": 0, "special": 0, "remaining": 3})
        self.assertTrue(all(row["version"] == 1 and not row["assigned"] for row in self.database.records()))

    def test_stale_batch_and_unknown_egid_are_rejected_without_partial_write(self):
        self.select(activate=True)
        payload = self.decision()
        payload["decisions"].append({"gvbsid": "SYNTHETIC-2", "version": 999, "status": "Unklar", "assigned": ["102"]})
        self.assertEqual(self.post("/api/save", payload).status_code, 409)
        self.assertTrue(all(row["version"] == 1 for row in self.database.records()))
        self.assertEqual(self.post("/api/save", self.decision(assigned=["999"])).status_code, 400)
        self.assertEqual(self.database.records()[0]["assigned"], [])

    def test_records_outside_current_parcel_cannot_be_saved(self):
        self.select(activate=True)
        self.assertEqual(self.post("/api/save", self.decision(gvbsid="SYNTHETIC-3", assigned=["101"])).status_code, 400)

    def test_reimport_preserves_decisions_and_activates_dataset(self):
        self.select(activate=True)
        self.post("/api/save", self.decision())
        prepared = prepare_rows(HEADERS, VALUES)[1]
        self.dialogs.choose.return_value = str(self.folder / "synthetic_import.xlsx")
        with patch("egid_match.zuordnung.store.read_review_excel", return_value=(HEADERS, prepared, set())):
            response = self.post("/api/import")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["imported"], 3)
        self.assertEqual(self.database.progress()["total"], 3)
        self.assertEqual(self.database.records()[0]["assigned"], ["101", "102"])

    def test_last_database_is_remembered_but_next_start_requires_step_two(self):
        self.select(activate=True)
        with patch.object(Path, "is_file", return_value=True), patch.object(Path, "read_text", return_value=json.dumps({"database": str(self.database.path), "geo": {}})):
            resumed = create_app(self.folder / "preferences.json", self.dialogs, geo_fetcher=self.fetch)
        state = LocalClient(resumed).get("/api/state").json
        self.assertEqual(state["database"], str(self.database.path))
        self.assertEqual(state["progress"]["total"], 3)
        self.assertFalse(state["active"])

    def test_new_database_does_not_overwrite_existing_file(self):
        self.dialogs.choose.return_value = str(self.database.path)
        response = self.post("/api/database/create")
        self.assertEqual(response.status_code, 400)
        self.assertIn("nicht ueberschrieben", response.json["error"])
        self.assertEqual(self.database.progress()["total"], 3)

    def test_export_uses_saved_database_and_includes_all_cases(self):
        self.select(activate=True)
        self.post("/api/save", self.decision())
        target = self.folder / "synthetic_export.xlsx"
        self.dialogs.choose.return_value = str(target)
        captured = []
        with patch("egid_match.zuordnung.store.Workbook.save", autospec=True, side_effect=lambda workbook, path: captured.append((workbook, path))), patch("egid_match.zuordnung.store.load_workbook", side_effect=AssertionError("Export darf keinen Excel-Import auslösen")):
            response = self.post("/api/export")
        self.assertEqual(response.status_code, 200)
        workbook, path = captured[0]
        self.assertEqual(path, target)
        self.assertEqual(workbook.worksheets[0].max_row, 4)
        self.assertEqual(workbook["Zuordnungen"].max_row, 3)
        self.assertEqual(workbook["Offene Fälle"].max_row, 2)

    def test_geodata_loading_alone_does_not_save_assignments(self):
        self.select(activate=True)
        self.app.session.config.update(parcel_url="", building_url="")
        response = self.post("/api/geo", {"selected": "SYNTHETIC-1"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["warnings"])
        self.fetch.assert_not_called()
        self.assertTrue(all(row["version"] == 1 and not row["assigned"] for row in self.database.records()))

    def test_additional_verified_parcel_egid_becomes_assignable(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        self.fetch.side_effect = [
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004})]},
        ]
        self.assertEqual(self.post("/api/geo", {"selected": "SYNTHETIC-1"}).status_code, 200)
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertIn("999", case["egids"])
        self.assertEqual(self.post("/api/save", self.decision(assigned=["999"])).status_code, 200)
        self.assertEqual(self.database.records()[0]["assigned"], ["999"])

    def test_stale_geodata_cannot_be_activated_after_import_or_configuration_change(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        def synthetic_fetch(url):
            self.app.session.revision += 1
            return {"type": "FeatureCollection", "features": []}
        self.fetch.side_effect = synthetic_fetch
        self.assertEqual(self.post("/api/geo", {"selected": "SYNTHETIC-1"}).status_code, 409)
        self.assertEqual(self.app.session.geo_cache, {})

    def test_expired_cached_extra_egid_is_not_assignable(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        self.fetch.side_effect = [
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004})]},
        ]
        self.assertEqual(self.post("/api/geo", {"selected": "SYNTHETIC-1"}).status_code, 200)
        cached = self.app.session.geo_cache["SYNTHETIC-1"]
        for source in cached["sources"].values():
            source["fetched_at"] = (datetime.now(timezone.utc) - timedelta(minutes=6)).isoformat()
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertNotIn("999", case["egids"])
        self.assertTrue(case["geo"]["sources"]["buildings"]["stale"])
        self.assertEqual(self.post("/api/save", self.decision(assigned=["999"])).status_code, 400)

    def test_older_parallel_map_request_cannot_overwrite_newer_request(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        def fetch(url):
            self.app.session.geo_requests["SYNTHETIC-1"] += 1
            return {"type": "FeatureCollection", "features": []}
        self.fetch.side_effect = fetch
        self.assertEqual(self.post("/api/geo", {"selected": "SYNTHETIC-1"}).status_code, 409)
        self.assertEqual(self.app.session.geo_cache, {})

    def test_local_origin_and_session_token_are_required(self):
        self.assertEqual(self.client.post("/api/database/select", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/database/select", json={}, headers={**self.headers, "Origin": "https://synthetic.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/state", headers={"Host": "synthetic.example"}).status_code, 403)
        self.dialogs.choose.assert_not_called()

    def test_cancel_does_not_change_active_database(self):
        self.select(activate=True)
        self.dialogs.choose.return_value = ""
        self.assertTrue(self.post("/api/database/select").json["cancelled"])
        self.assertTrue(self.client.get("/api/state").json["active"])

    def test_import_has_no_database_network_or_browser_side_effects(self):
        with patch.object(sqlite3, "connect") as connection, patch("webbrowser.open") as browser, patch("egid_match.zuordnung.geo.fetch_json") as network:
            name = "egid_match.zuordnung.synthetic_import_only"
            spec = importlib.util.spec_from_file_location(name, ROOT / "src" / "egid_match" / "zuordnung" / "app.py")
            module = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {name: module}):
                spec.loader.exec_module(module)
        connection.assert_not_called()
        browser.assert_not_called()
        network.assert_not_called()

    def test_page_shows_disabled_features_and_purpose_matrix_container(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="import" disabled', response.text)
        self.assertIn('id="save" disabled', response.text)
        self.assertIn('id="matrix"', response.text)
        self.assertNotIn('id="geo-settings"', response.text)
        self.assertNotIn('id="geo-dialog"', response.text)
        self.assertNotIn('id="import-gwr"', response.text)
        self.assertNotIn('id="gwr-info"', response.text)
        self.assertNotIn("GWR-Bestand laden", response.text)
        self.assertNotIn('class="map-toolbar"', response.text)
        for identifier in ("active-parcel", "reload-map", "building-status", "pick-parcel"):
            self.assertNotIn(f'id="{identifier}"', response.text)
        self.assertIn("Gesamte Zuteilung als Excel exportieren", response.text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_page_uses_matching_palette_for_category_theme(self):
        from egid_match.matching import CATEGORY_ALIASES, CATEGORY_COLORS, SUFFIX_SINGLE_REVIEW
        response = self.client.get("/")
        config_text = response.text.split('<script id="review-config" type="application/json">', 1)[1].split("</script>", 1)[0]
        config = json.loads(config_text)
        self.assertEqual(config["category_colors"], CATEGORY_COLORS)
        self.assertEqual(config["category_colors"][SUFFIX_SINGLE_REVIEW], "E6C200")
        self.assertEqual(config["category_aliases"], CATEGORY_ALIASES)
        self.assertEqual(config["category_colors"]["address_suffix_pair_ge4"], "C4A484")
        self.assertIn('id="case-category"', response.text)

    def test_removed_geodata_configuration_endpoint_is_not_available(self):
        self.select(activate=True)
        self.assertEqual(self.post("/api/geo/config", geo_config()).status_code, 404)

    def test_native_windows_dialogs_are_distinct_and_always_destroyed(self):
        root = Mock()
        with patch("tkinter.Tk", return_value=root), patch("tkinter.filedialog.askopenfilename", return_value="synthetic.sqlite") as opened, patch("tkinter.filedialog.asksaveasfilename", return_value="synthetic_new.sqlite") as saved:
            dialogs = NativeDialogs()
            self.assertEqual(dialogs.choose("database"), "synthetic.sqlite")
            self.assertEqual(dialogs.choose("create"), "synthetic_new.sqlite")
        opened.assert_called_once()
        saved.assert_called_once()
        self.assertTrue(saved.call_args.kwargs["confirmoverwrite"])
        self.assertEqual(root.destroy.call_count, 2)

    def test_missing_remembered_database_requires_new_selection(self):
        with patch.object(Path, "is_file", return_value=True), patch.object(Path, "read_text", return_value=json.dumps({"database": "synthetic_missing.sqlite", "geo": {}})):
            app = create_app(self.folder / "preferences.json", self.dialogs, geo_fetcher=self.fetch)
        response = LocalClient(app).get("/api/state").json
        self.assertIsNone(response["database"])
        self.assertFalse(response["active"])
        self.assertTrue(response["warning"])

    def test_removed_gwr_import_endpoint_never_opens_a_file_dialog(self):
        self.assertEqual(self.post("/api/gwr/import").status_code, 404)
        self.dialogs.choose.assert_not_called()
        self.select(activate=True)
        self.dialogs.choose.reset_mock()
        before = self.database.records()
        self.assertEqual(self.post("/api/gwr/import").status_code, 404)
        self.dialogs.choose.assert_not_called()
        self.fetch.assert_not_called()
        self.assertEqual(self.database.records(), before)
        self.assertNotIn("gwr", self.client.get("/api/state").json)

    def test_legacy_snapshot_is_ignored_and_preserved_while_public_source_is_used(self):
        # Nur selbst erzeugte Altstruktur in SQLite :memory:. Ungültiges JSON
        # stellt sicher, dass alte Snapshot-Inhalte auch nicht dekodiert werden.
        connection = self.database.memory
        connection.execute("CREATE TABLE review_gwr (egid TEXT PRIMARY KEY, building TEXT NOT NULL)")
        connection.execute("INSERT INTO review_gwr VALUES ('555', 'synthetic legacy payload')")
        connection.execute("INSERT INTO review_meta VALUES ('gwr', 'synthetic legacy metadata')")
        connection.commit()
        def block_snapshot_access(action, table, column, database, trigger):
            return sqlite3.SQLITE_DENY if table == "review_gwr" else sqlite3.SQLITE_OK
        connection.set_authorizer(block_snapshot_access)
        try:
            self.select(activate=True)
            self.assertNotIn("gwr", self.client.get("/api/state").json)
            initial = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
            self.assertIsNone(initial["geo"])
            self.assertNotIn("555", initial["egids"])
            self.app.session.config = geo_config()
            self.fetch.side_effect = [
                {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
                {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004})]},
            ]
            response = self.post("/api/geo", {"selected": "SYNTHETIC-1"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.fetch.call_count, 2)
            self.assertEqual([row["egid"] for row in response.json["buildings"]], ["999"])
            self.assertEqual(self.post("/api/save", self.decision(assigned=["999"])).status_code, 200)
            self.select(activate=True)
            self.assertEqual(self.database.records()[0]["assigned"], ["999"])
        finally:
            connection.set_authorizer(None)
        self.assertEqual([tuple(row) for row in connection.execute("SELECT * FROM review_gwr")], [("555", "synthetic legacy payload")])
        self.assertEqual(connection.execute("SELECT value FROM review_meta WHERE key='gwr'").fetchone()[0], "synthetic legacy metadata")

    def test_map_always_uses_gstat_1004_even_when_request_overrides_filter(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        for statuses in (None, ["1004"], ["1001"], ["1007"], [], ["1004", "1001"], "all"):
            self.fetch.side_effect = [
                {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
                {"type": "FeatureCollection", "features": [
                    feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004}),
                    feature({"egrid": "CH-SYNTHETIC-1", "egid": 888, "gstat": 1001}),
                    feature({"egrid": "CH-SYNTHETIC-1", "egid": 777, "gstat": 1007}),
                    feature({"egrid": "CH-SYNTHETIC-1", "egid": 666, "gstat": ""}),
                ]},
            ]
            with self.subTest(statuses=statuses):
                payload = {"selected": "SYNTHETIC-1"}
                if statuses is not None:
                    payload["statuses"] = statuses
                response = self.post("/api/geo", payload)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["egid"] for row in response.json["buildings"]], ["999"])
                self.assertEqual(response.json["filters"]["gstat"], ["1004"])
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertIn("999", case["egids"])
        self.assertTrue({"888", "777", "666"}.isdisjoint(case["egids"]))

    def test_parcel_service_failure_does_not_block_public_building_points(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        position = {"type": "Point", "coordinates": [7.55, 47.52]}
        def fetch(url):
            if "/parcels/items" in url:
                raise TimeoutError("Synthetischer Parzellenausfall")
            return {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 101, "gstat": 1004}, position)]}
        self.fetch.side_effect = fetch
        with patch("egid_match.zuordnung.geo_transport.time.sleep"):
            response = self.post("/api/geo", {"selected": "SYNTHETIC-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["sources"]["parcels"]["code"], "unreachable")
        self.assertEqual(response.json["sources"]["buildings"]["code"], "complete")
        self.assertEqual(response.json["buildings"][0]["geometry"], position)

    def test_removed_gwr_dialog_kind_cannot_open_a_source_file(self):
        root = Mock()
        with patch("tkinter.Tk", return_value=root), patch("tkinter.filedialog.askopenfilename") as opened, patch("tkinter.filedialog.asksaveasfilename") as saved:
            with self.assertRaises(ReviewError):
                NativeDialogs().choose("gwr")
        opened.assert_not_called()
        saved.assert_not_called()
        root.destroy.assert_called_once()

    def test_map_uses_original_gwr_addresses_for_exact_egid_without_changing_decisions(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        self.app.session.gwr_path = self.folder / "synthetic-address-source.sqlite"
        original = self.database.records()
        self.fetch.side_effect = [
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004})]},
        ]
        addresses = [["Teststrasse", "10a", "0000"], ["Seitengasse", "3.1", "0000"]]
        self.gwr_addresses.return_value = {"999": addresses, "888": [["Fremder Testweg", "9", "0000"]]}
        response = self.post("/api/geo", {"selected": "SYNTHETIC-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["buildings"][0]["addresses"], addresses)
        self.assertEqual(response.json["gwr_address_status"]["code"], "complete")
        self.gwr_addresses.assert_called_once_with(self.app.session.gwr_path, ["999"])
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertEqual(case["geo"]["buildings"][0]["addresses"], addresses)
        self.assertEqual(self.database.records(), original)
        self.assertEqual(self.fetch.call_count, 2)

    def test_gwr_volumes_are_loaded_for_table_candidates_and_additional_map_egids(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        original = self.database.records()
        self.fetch.side_effect = [
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004})]},
        ]
        self.gwr_volumes.return_value = {"101": 1200, "999": 25.5, "888": 999999}
        response = self.post("/api/geo", {"selected": "SYNTHETIC-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["volumes"], {"101": 1200, "102": None, "999": 25.5})
        self.assertEqual(response.json["buildings"][0]["volume"], 25.5)
        self.gwr_volumes.assert_called_once_with(self.app.session.gwr_path, ["101", "102", "999"])
        case = self.client.get("/api/case", query_string={"gvbsid": "SYNTHETIC-1"}).json
        self.assertEqual(case["geo"]["volumes"], response.json["volumes"])
        self.assertEqual(self.database.records(), original)

    def test_unavailable_gwr_volume_does_not_remove_addresses_or_block_assignment(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        self.fetch.side_effect = [
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004})]},
        ]
        self.gwr_addresses.return_value = {"999": [["Synthetischer Testweg", "1", "0000"]]}
        self.gwr_volumes.side_effect = ReviewError("Synthetisch fehlendes GVOL")
        response = self.post("/api/geo", {"selected": "SYNTHETIC-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["gwr_volume_status"]["code"], "unreachable")
        self.assertEqual(response.json["volumes"], {})
        self.assertIsNone(response.json["buildings"][0]["volume"])
        self.assertEqual(response.json["buildings"][0]["addresses"], [["Synthetischer Testweg", "1", "0000"]])
        self.assertEqual(self.post("/api/save", self.decision(assigned=["999"])).status_code, 200)

    def test_unavailable_gwr_address_source_keeps_map_geometry_and_reports_reason(self):
        self.select(activate=True)
        self.app.session.config = geo_config()
        self.fetch.side_effect = [
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1"})]},
            {"type": "FeatureCollection", "features": [feature({"egrid": "CH-SYNTHETIC-1", "egid": 999, "gstat": 1004})]},
        ]
        self.gwr_addresses.side_effect = ReviewError("Synthetische GWR-Adressquelle nicht verfügbar")
        response = self.post("/api/geo", {"selected": "SYNTHETIC-1"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json["buildings"][0]["geometry"])
        self.assertEqual(response.json["buildings"][0]["addresses"], [])
        self.assertEqual(response.json["gwr_address_status"]["code"], "unreachable")
        self.assertIn("nicht verfügbar", response.json["gwr_address_status"]["message"])

    def test_gwr_address_path_can_be_configured_without_opening_it(self):
        path = self.folder / "synthetic-address-source.sqlite"
        app = create_app(self.folder / "synthetic-preferences.json", self.dialogs, resume=False, gwr_path=path)
        self.assertEqual(app.session.gwr_path, path)
        self.gwr_addresses.assert_not_called()
        self.gwr_volumes.assert_not_called()


if __name__ == "__main__":
    unittest.main()

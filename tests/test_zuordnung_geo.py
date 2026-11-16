"""Ausschliesslich synthetische Geometrien und vollständig ersetzte Netzwerkaufrufe."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import copy
import json
import sys
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from test_zuordnung_store import feature, geo_config
from egid_match.zuordnung.geo import DEFAULTS, GeoBS, cached_context
from egid_match.zuordnung.geometrie import GeometryError, geometry_relation, normalize_geometry, point_location, validate_geometry
from egid_match.zuordnung.geo_transport import SourceClient, SourceError, fetch_json


def square(x=0, y=0, size=10):
    return {"type": "Polygon", "coordinates": [[[x, y], [x + size, y], [x + size, y + size], [x, y + size], [x, y]]]}


def point(x, y):
    return {"type": "Point", "coordinates": [x, y]}


def collection(*features, **extra):
    return {"type": "FeatureCollection", "features": list(features), **extra}


def parcel(egrid="CH-SYNTHETIC-1", geometry=None):
    return feature({"egrid": egrid}, geometry if geometry is not None else square())


def building(egid=101, egrid="CH-SYNTHETIC-1", geometry=None, **properties):
    return feature({"egid": egid, "egrid": egrid, "gstat": 1004, **properties}, geometry if geometry is not None else point(1, 1))


def next_page(url, offset=1):
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    query["offset"] = [str(offset)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), ""))


class GeometryTests(unittest.TestCase):
    def test_polygon_hole_and_boundary(self):
        geometry = square()
        geometry["coordinates"].append(square(2, 2, 2)["coordinates"][0])
        validate_geometry(geometry, parcel=True)
        self.assertEqual(point_location([1, 1], geometry), "inside")
        self.assertEqual(point_location([3, 3], geometry), "outside")
        self.assertEqual(point_location([2, 3], geometry), "boundary")
        self.assertEqual(point_location([0, 5], geometry), "boundary")

    def test_multipolygon_preserves_disconnected_parts(self):
        geometry = {"type": "MultiPolygon", "coordinates": [square()["coordinates"], square(20, 0)["coordinates"]]}
        validate_geometry(geometry, parcel=True)
        self.assertEqual(point_location([21, 1], geometry), "inside")
        self.assertEqual(point_location([15, 1], geometry), "outside")

    def test_invalid_rings_and_overlapping_multipolygons_are_rejected(self):
        invalid = [
            {"type": "Polygon", "coordinates": [[[0, 0], [2, 2], [2, 0], [0, 2], [0, 0]]]},
            {"type": "Polygon", "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2]]]},
            {"type": "MultiPolygon", "coordinates": [square()["coordinates"], square()["coordinates"]]},
        ]
        for geometry in invalid:
            with self.subTest(geometry=geometry), self.assertRaises(GeometryError):
                validate_geometry(geometry, parcel=True)

    def test_normalization_removes_only_adjacent_duplicate_vertices(self):
        geometry = square()
        ring = geometry["coordinates"][0]
        ring.insert(2, ring[1][:])
        ring.insert(0, ring[0][:])
        ring.append(ring[-1][:])
        original = copy.deepcopy(geometry)
        result = normalize_geometry(geometry, parcel=True)
        self.assertEqual(result, square())
        self.assertEqual(geometry, original)
        self.assertEqual(point_location([1, 1], result), "inside")
        self.assertEqual(point_location([0, 5], result), "boundary")

    def test_normalization_preserves_multipolygon_parts_and_holes(self):
        geometry = {"type": "MultiPolygon", "coordinates": [
            [square()["coordinates"][0], square(2, 2, 2)["coordinates"][0]],
            square(20, 0)["coordinates"],
        ]}
        expected = copy.deepcopy(geometry)
        for polygon in geometry["coordinates"]:
            for ring in polygon:
                ring.insert(1, ring[0][:])
                ring.append(ring[-1][:])
        result = normalize_geometry(geometry, parcel=True)
        self.assertEqual(result, expected)
        self.assertEqual(point_location([3, 3], result), "outside")
        self.assertEqual(point_location([21, 1], result), "inside")

    def test_normalization_never_closes_or_repairs_invalid_rings(self):
        invalid = [
            [[[0, 0], [2, 0], [2, 2], [0, 2]]],  # offen
            [[[0, 0], [0, 0], [2, 0], [0, 0]]],  # zu kurz
            [[[0, 0], [2, 0], [2, 2], [2, 0], [0, 2], [0, 0]]],
            [[[0, 0], [2, 2], [2, 2], [2, 0], [0, 2], [0, 0]]],
        ]
        for coordinates in invalid:
            with self.subTest(coordinates=coordinates), self.assertRaises(GeometryError):
                normalize_geometry({"type": "Polygon", "coordinates": coordinates}, parcel=True)

    def test_duplicate_vertices_cannot_bypass_resource_limit(self):
        geometry = square()
        geometry["coordinates"][0].insert(1, [0, 0])
        with patch("egid_match.zuordnung.geometrie.MAX_VERTICES", 5), self.assertRaises(GeometryError) as error:
            normalize_geometry(geometry, parcel=True)
        self.assertEqual(error.exception.code, "incomplete")

    def test_spatial_relation_uses_polygon_not_bbox(self):
        geometry = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 2], [2, 2], [2, 10], [0, 10], [0, 0]]]}
        validate_geometry(geometry, parcel=True)
        self.assertEqual(geometry_relation(point(8, 8), geometry), "outside")
        self.assertEqual(geometry_relation(square(1, 1, 2), geometry), "crosses")
        self.assertEqual(geometry_relation(square(.2, .2, .5), geometry), "inside")

    def test_building_covering_parcel_hole_is_not_wholly_inside(self):
        geometry = square()
        geometry["coordinates"].append(square(2, 2, 2)["coordinates"][0])
        self.assertEqual(geometry_relation(square(1, 1, 4), geometry), "crosses")

    def test_explicit_axis_order_and_no_crs_guessing(self):
        result = normalize_geometry(point(47.5, 7.5), "CRS84", "yx")
        self.assertEqual(result["coordinates"], [7.5, 47.5])
        with self.assertRaises(GeometryError):
            normalize_geometry(point(7.5, 47.5), "EPSG:999999")
        with self.assertRaises(GeometryError):
            normalize_geometry(point(2600000, 1200000), "CRS84")

    def test_lv95_transformer_is_requested_with_always_xy(self):
        transformer = Mock()
        transformer.transform.return_value = (7.5, 47.5)
        factory = Mock(return_value=transformer)
        result = normalize_geometry(point(2600000, 1200000), "EPSG:2056", transformer_factory=factory)
        factory.assert_called_once_with("EPSG:2056", "EPSG:4326", always_xy=True)
        transformer.transform.assert_called_once_with(2600000, 1200000)
        self.assertEqual(result["coordinates"], [7.5, 47.5])

    def test_missing_transform_library_is_explicit(self):
        with patch.dict(sys.modules, {"pyproj": None}), self.assertRaises(GeometryError) as error:
            normalize_geometry(point(2600000, 1200000), "EPSG:2056")
        self.assertEqual(error.exception.code, "transform_missing")

    def test_invalid_projected_position_is_not_disguised_as_missing_library(self):
        with patch.dict(sys.modules, {"pyproj": None}), self.assertRaises(GeometryError) as error:
            normalize_geometry(point(float("nan"), 1200000), "EPSG:2056")
        self.assertEqual(error.exception.code, "invalid")

    def test_geometry_resource_limit_is_incomplete(self):
        with patch("egid_match.zuordnung.geometrie.MAX_VERTICES", 3), self.assertRaises(GeometryError) as error:
            validate_geometry(square(), parcel=True)
        self.assertEqual(error.exception.code, "incomplete")

    def test_geometry_work_obeys_context_deadline(self):
        with patch("egid_match.zuordnung.geometrie.time.monotonic", return_value=2), self.assertRaises(GeometryError) as error:
            validate_geometry(square(), parcel=True, deadline=1)
        self.assertEqual(error.exception.code, "incomplete")


class TransportTests(unittest.TestCase):
    def test_documented_qgis_property_filter_replaces_unproven_cql(self):
        fetch = Mock(return_value=collection())
        GeoBS(DEFAULTS, fetch).features("parcel", "EGRID", "CH-SYNTHETIC-1")
        query = parse_qs(urlsplit(fetch.call_args.args[0]).query)
        self.assertEqual(query["EGRID"], ["CH-SYNTHETIC-1"])
        self.assertEqual(query["MAP"], ["Public_latest_published"])
        self.assertIn("CRS84", query["crs"][0])
        self.assertNotIn("filter-lang", query)

    def test_all_pages_are_followed_with_filters_retained(self):
        def fetch(url):
            if "offset=" not in url:
                return collection(parcel(), numberMatched=2, links=[{"rel": "next", "href": next_page(url)}])
            return collection(parcel(), numberMatched=2)
        mocked = Mock(side_effect=fetch)
        result = GeoBS(geo_config(), mocked).features("parcel", "egrid", "CH-SYNTHETIC-1")
        self.assertEqual(len(result), 2)
        self.assertEqual(mocked.call_count, 2)

    def test_pagination_loops_and_page_limit_are_incomplete(self):
        for loop in (True, False):
            with self.subTest(loop=loop):
                counter = [0]
                def fetch(url):
                    counter[0] += 1
                    return collection(parcel(), links=[{"rel": "next", "href": url if loop else next_page(url, counter[0])}])
                with patch("egid_match.zuordnung.geo_transport.MAX_PAGES", 2), self.assertRaises(SourceError) as error:
                    GeoBS(geo_config(), fetch).features("parcel", "egrid", "CH-SYNTHETIC-1")
                self.assertEqual(error.exception.code, "incomplete")
                self.assertTrue(error.exception.partial)

    def test_next_page_cannot_leave_source_or_drop_filters(self):
        for external in (True, False):
            def fetch(url):
                target = "https://not-approved.example/items" if external else urlsplit(url)._replace(query="offset=1").geturl()
                return collection(parcel(), links=[{"rel": "next", "href": target}])
            mocked = Mock(side_effect=fetch)
            with self.subTest(external=external), self.assertRaises(SourceError):
                GeoBS(geo_config(), mocked).features("parcel", "egrid", "CH-SYNTHETIC-1")
            self.assertEqual(mocked.call_count, 1)

    def test_ignored_identifier_filter_is_invalid_not_empty(self):
        fetch = Mock(return_value=collection(parcel("CH-WRONG")))
        value = GeoBS(geo_config(), fetch).context(["CH-SYNTHETIC-1"], [])
        self.assertEqual(value["sources"]["parcels"]["code"], "invalid")
        self.assertFalse(value["sources"]["parcels"]["complete"])
        self.assertEqual(value["parcels"], [])

    def test_timeout_invalid_answer_and_true_empty_are_distinct(self):
        cases = [(TimeoutError("synthetisch"), "unreachable"), ("HTML statt GeoJSON", "invalid"), (collection(), "empty")]
        for response, expected in cases:
            with self.subTest(expected=expected), patch("egid_match.zuordnung.geo_transport.time.sleep"):
                fetch = Mock(side_effect=response) if isinstance(response, Exception) else Mock(return_value=response)
                value = GeoBS(geo_config(), fetch).context(["CH-SYNTHETIC-1"], [])
                self.assertEqual(value["sources"]["parcels"]["code"], expected)
                self.assertEqual(fetch.call_count, 4 if expected == "unreachable" else 2)

    def test_time_and_response_limits_do_not_claim_completeness(self):
        with patch("egid_match.zuordnung.geo_transport.MAX_TOTAL_BYTES", 20), self.assertRaises(SourceError) as error:
            GeoBS(geo_config(), Mock(return_value=collection(parcel()))).features("parcel", "egrid", "CH-SYNTHETIC-1")
        self.assertEqual(error.exception.code, "incomplete")
        with patch("egid_match.zuordnung.geo_transport.time.monotonic", side_effect=[0, 0, 46]), self.assertRaises(SourceError) as error:
            GeoBS(geo_config(), Mock(return_value=collection())).features("parcel", "egrid", "CH-SYNTHETIC-1")
        self.assertEqual(error.exception.code, "incomplete")

    def test_ods_uses_documented_total_offset_and_minimal_fields(self):
        rows = [{"egid": 101 + i, "egrid": "CH-SYNTHETIC-1", "gstat": 1004, "gkode": None, "gkodn": None} for i in range(3)]
        fetch = Mock(side_effect=[{"total_count": 3, "results": rows[:2]}, {"total_count": 3, "results": rows[2:]}])
        result = GeoBS(DEFAULTS, fetch).features("building", "egrid", "CH-SYNTHETIC-1")
        self.assertEqual(len(result), 3)
        self.assertEqual([parse_qs(urlsplit(call.args[0]).query)["offset"] for call in fetch.call_args_list], [["0"], ["2"]])
        self.assertIn('egrid = "CH-SYNTHETIC-1"', parse_qs(urlsplit(fetch.call_args_list[0].args[0]).query)["where"][0])

    def test_ods_numeric_egid_and_changing_total_are_checked(self):
        fetch = Mock(return_value={"total_count": 0, "results": []})
        GeoBS(DEFAULTS, fetch).features("building", "egid", "101")
        self.assertEqual(parse_qs(urlsplit(fetch.call_args.args[0]).query)["where"], ["egid = 101"])
        row = {"egid": 101, "egrid": "CH-SYNTHETIC-1"}
        fetch = Mock(side_effect=[{"total_count": 2, "results": [row]}, {"total_count": 3, "results": [row]}])
        with self.assertRaises(SourceError) as error:
            GeoBS(DEFAULTS, fetch).features("building", "egrid", "CH-SYNTHETIC-1")
        self.assertEqual(error.exception.code, "incomplete")

    def test_wms_image_is_never_treated_as_polygon(self):
        response = Mock()
        response.headers = {"Content-Type": "image/png"}
        manager = Mock()
        manager.__enter__ = Mock(return_value=response)
        manager.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = manager
        with patch("egid_match.zuordnung.geo_transport.build_opener", return_value=opener), self.assertRaises(SourceError) as error:
            fetch_json("https://synthetic.geo.bs.ch/wms")
        self.assertEqual(error.exception.code, "invalid")
        response.read.assert_not_called()


class AssociationTests(unittest.TestCase):
    def test_default_profiles_draw_lv95_points_without_optional_pyproj(self):
        raw_parcel = feature({"EGRID": "CH-SYNTHETIC-1", "Sektionsname": "SYNTHETIC", "Parzellennummer": "1"}, square(7.6, 47.55, .001))
        rows = [{"egid": 101 + i, "egrid": "CH-SYNTHETIC-1", "gstat": 1004,
                 "gkode": 2600000 + i, "gkodn": 1200000 + i, "gexpdat": "2020-01-01"} for i in range(2)]
        with patch.dict(sys.modules, {"pyproj": None}):
            result = GeoBS(DEFAULTS, Mock(side_effect=[collection(raw_parcel), {"total_count": 2, "results": rows}])).context(["CH-SYNTHETIC-1"], [])
        self.assertEqual(result["sources"]["parcels"]["code"], "complete")
        self.assertEqual(result["sources"]["buildings"]["code"], "complete")
        self.assertIn("Swisstopo-Näherung", result["sources"]["buildings"]["message"])
        self.assertEqual(len(result["buildings"]), 2)
        self.assertTrue(all(row["geometry"]["type"] == "Point" and row["assignable"] for row in result["buildings"]))
        self.assertTrue(all("Swisstopo-Näherung" in row["geometry_note"] for row in result["buildings"]))

    def test_repeated_parcel_vertices_do_not_remove_boundary_from_context(self):
        geometry = square()
        geometry["coordinates"][0].insert(2, [10, 0])
        geometry["coordinates"][0].append([0, 0])
        fetch = Mock(side_effect=[collection(parcel(geometry=geometry)), collection(building())])
        result = GeoBS(geo_config(), fetch).context(["CH-SYNTHETIC-1"], [])
        self.assertEqual(result["sources"]["parcels"]["code"], "complete")
        self.assertEqual(result["parcels"][0]["geometry"], square())
        self.assertTrue(result["buildings"][0]["assignable"])

    def test_missing_building_position_or_status_still_reports_incomplete(self):
        for missing in ("geometry", "gstat"):
            item = building()
            if missing == "geometry":
                item["geometry"] = None
            else:
                item["properties"]["gstat"] = ""
            fetch = Mock(side_effect=[collection(parcel()), collection(item)])
            result = GeoBS(geo_config(), fetch).context(["CH-SYNTHETIC-1"], [])
            with self.subTest(missing=missing):
                self.assertEqual(result["sources"]["buildings"]["code"], "incomplete")

    def test_approximate_point_without_egrid_cannot_enable_assignment(self):
        config = {**DEFAULTS, "parcel_url": "", "building_egrid": ""}
        rows = [{"egid": 101, "gstat": 1004, "gkode": 2600000, "gkodn": 1200000}]
        with patch.dict(sys.modules, {"pyproj": None}):
            result = GeoBS(config, Mock(return_value={"total_count": 1, "results": rows})).context([], ["101"])
        self.assertEqual(result["sources"]["buildings"]["code"], "ambiguous")
        self.assertFalse(result["buildings"][0]["assignable"])
        self.assertEqual(result["buildings"][0]["geometry"]["type"], "Point")

    def test_egid_points_still_load_when_parcel_service_is_unconfigured_or_empty(self):
        for configured in (True, False):
            config = geo_config()
            if not configured:
                config["parcel_url"] = ""
            fetch = Mock(side_effect=[collection(), collection(building())] if configured else [collection(building())])
            result = GeoBS(config, fetch).context(["CH-SYNTHETIC-1"], ["101"])
            self.assertEqual(result["parcels"], [])
            self.assertEqual(result["buildings"][0]["geometry"], point(1, 1))
            self.assertTrue(result["buildings"][0]["assignable"])

    def test_unrelated_display_point_does_not_become_a_new_assignment(self):
        config = {**geo_config(), "parcel_url": "", "building_egrid": ""}
        result = GeoBS(config, Mock(return_value=collection(building()))).context([], ["101"])
        self.assertEqual(result["buildings"][0]["geometry"], point(1, 1))
        self.assertFalse(result["buildings"][0]["assignable"])

    def test_parcel_available_while_building_source_unconfigured(self):
        fetch = Mock(return_value=collection(parcel()))
        result = GeoBS({**geo_config(), "building_url": ""}, fetch).context(["CH-SYNTHETIC-1"], [])
        self.assertEqual(result["sources"]["parcels"]["code"], "complete")
        self.assertEqual(result["sources"]["buildings"]["code"], "not_configured")
        self.assertEqual(len(result["parcels"]), 1)

    def test_section_and_number_are_combined_and_checked_locally(self):
        fetch = Mock(return_value=collection(parcel()))
        result = GeoBS({**geo_config(), "building_url": ""}, fetch).context([], [], section="SYNTHETIC", number="1")
        self.assertEqual(len(result["parcels"]), 1)
        query = parse_qs(urlsplit(fetch.call_args.args[0]).query)
        self.assertIn("section = 'SYNTHETIC'", query["filter"][0])
        self.assertIn("parcel_number = '1'", query["filter"][0])
        fetch.reset_mock()
        result = GeoBS(geo_config(), fetch).context([], [], number="1")
        self.assertEqual(result["sources"]["parcels"]["code"], "ambiguous")
        self.assertIsNone(result["sources"]["parcels"]["fetched_at"])
        self.assertIsNone(result["sources"]["parcels"]["attempted_at"])
        fetch.assert_not_called()

    def test_shared_boundary_and_multiple_candidates_are_ambiguous(self):
        for position in ([10, 5], [5, 5]):
            geometries = [parcel(geometry=square()), parcel("CH-OTHER", square(10 if position[0] == 10 else 0, 0))]
            result = GeoBS({**geo_config(), "building_url": ""}, Mock(return_value=collection(*geometries))).context([], [], point=position)
            self.assertEqual(result["sources"]["parcels"]["code"], "ambiguous")
            self.assertEqual(result["parcels"], [])

    def test_point_in_hole_and_multipolygon_are_handled(self):
        geometry = square()
        geometry["coordinates"].append(square(2, 2, 2)["coordinates"][0])
        config = {**geo_config(), "building_url": ""}
        result = GeoBS(config, Mock(return_value=collection(parcel(geometry=geometry)))).context([], [], point=[3, 3])
        self.assertEqual(result["sources"]["parcels"]["code"], "empty")
        multi = {"type": "MultiPolygon", "coordinates": [square()["coordinates"], square(20, 0)["coordinates"]]}
        result = GeoBS(config, Mock(return_value=collection(parcel(geometry=multi)))).context([], [], point=[21, 1])
        self.assertEqual(len(result["parcels"]), 1)

    def test_wrong_axes_contradicting_documented_extent_are_rejected(self):
        config = {**geo_config(), "parcel_extent": "7,47,8,48", "building_url": ""}
        result = GeoBS(config, Mock(return_value=collection(parcel(geometry=square(47, 7, .1))))).context(["CH-SYNTHETIC-1"], [])
        self.assertEqual(result["sources"]["parcels"]["code"], "invalid")

    def test_multiple_egids_and_duplicate_entrances_are_deduplicated(self):
        data = [collection(parcel()), collection(
            building(101, geometry=point(1, 1), street="Test", number="1"),
            building(101, geometry=point(1.5, 1.5), street="Test", number="2"), building(102, geometry=point(2, 1)))]
        result = GeoBS(geo_config(), Mock(side_effect=data)).context(["CH-SYNTHETIC-1"], [])
        self.assertEqual([item["egid"] for item in result["buildings"]], ["101", "102"])
        self.assertEqual(len(result["buildings"][0]["addresses"]), 2)
        self.assertEqual(result["buildings"][0]["geometry"]["type"], "MultiPoint")

    def test_building_inside_bbox_but_outside_polygon_is_not_assigned(self):
        geometry = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 2], [2, 2], [2, 10], [0, 10], [0, 0]]]}
        data = [collection(parcel(geometry=geometry)), collection(building(101, geometry=point(1, 1)), building(102, geometry=point(8, 8)))]
        config = {**geo_config(), "building_egrid": ""}
        result = GeoBS(config, Mock(side_effect=data)).context(["CH-SYNTHETIC-1"], [])
        self.assertEqual([item["egid"] for item in result["buildings"]], ["101"])
        self.assertIn("Räumlich abgeleitet", result["buildings"][0]["relation"])

    def test_entrance_point_without_authoritative_relation_needs_review(self):
        data = [collection(parcel()), collection(building())]
        result = GeoBS({**geo_config(), "building_egrid": "", "building_point_role": "entrance"}, Mock(side_effect=data)).context(["CH-SYNTHETIC-1"], [])
        self.assertFalse(result["buildings"][0]["assignable"])
        self.assertEqual(result["sources"]["buildings"]["code"], "ambiguous")

    def test_building_over_multiple_parcels_is_not_a_silent_unique_relation(self):
        polygon = square(8, 2, 4)
        fetch = Mock(side_effect=[collection(parcel("CH-OTHER", square(10, 0))), collection(parcel()),
                                  collection(building(101, "CH-OTHER", polygon)), collection(building(101, geometry=polygon))])
        result = GeoBS(geo_config(), fetch).context(["CH-SYNTHETIC-1", "CH-OTHER"], [])
        self.assertEqual(len(result["parcels"]), 2)
        self.assertEqual(len(result["buildings"]), 1)
        self.assertEqual(set(result["buildings"][0]["egrids"]), {"CH-SYNTHETIC-1", "CH-OTHER"})
        self.assertTrue(result["buildings"][0]["needs_review"])
        self.assertFalse(result["buildings"][0]["assignable"])
        self.assertEqual(result["sources"]["buildings"]["code"], "ambiguous")

    def test_status_filter_retains_status_and_does_not_hide_its_scope(self):
        def run(statuses):
            return GeoBS(geo_config(), Mock(side_effect=[collection(parcel()), collection(building(101), building(102, gstat=1007))])).context(["CH-SYNTHETIC-1"], [], statuses=statuses)
        existing = run(["1004"])
        self.assertEqual([row["gstat"] for row in existing["buildings"]], ["1004"])
        all_status = run([])
        self.assertEqual({row["gstat"] for row in all_status["buildings"]}, {"1004", "1007"})
        self.assertEqual(all_status["filters"]["gstat"], [])

    def test_old_cache_is_marked_and_new_relationships_are_disabled(self):
        result = GeoBS(geo_config(), Mock(side_effect=[collection(parcel()), collection(building())])).context(["CH-SYNTHETIC-1"], [])
        original = copy.deepcopy(result)
        later = datetime.now(timezone.utc) + timedelta(seconds=301)
        cached = cached_context(result, later)
        self.assertTrue(cached["sources"]["parcels"]["stale"])
        self.assertFalse(cached["buildings"][0]["assignable"])
        self.assertEqual(result, original)


if __name__ == "__main__":
    unittest.main()

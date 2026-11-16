"""Nur synthetische Koordinaten und GWR-Adressen in SQLite :memory:."""

from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
from egid_match.zuordnung.geometrie import GeometryError
from egid_match.zuordnung.gwr import APPROXIMATION, gwr_point, read_gwr_addresses
from egid_match.zuordnung.store import ReviewError


class GwrTests(unittest.TestCase):
    def test_addresses_are_read_only_and_selected_by_existing_egid(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE entrance (EGID INTEGER, STRNAME TEXT, DEINR TEXT, DPLZ4 TEXT)")
        connection.executemany("INSERT INTO entrance VALUES (?, ?, ?, ?)", [
            (101, "Teststrasse", "10a", "0000"),
            (101, "Teststrasse", "10a", "0000"),
            (101, "Seitengasse", "3.1", "0000"),
            (102, "Teststrasse", "10b", "0000"),
            (103, "Teststrasse", "10a", "0000"),
        ])
        connection.commit()
        denied = {sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE,
                  sqlite3.SQLITE_CREATE_TABLE, sqlite3.SQLITE_DROP_TABLE}
        connection.set_authorizer(lambda action, *args: sqlite3.SQLITE_DENY if action in denied else sqlite3.SQLITE_OK)
        tracked = Mock(wraps=connection)
        path = ROOT / "synthetic-not-created" / "gwr.sqlite"
        with patch("egid_match.zuordnung.gwr.sqlite3.connect", return_value=tracked) as connect:
            addresses = read_gwr_addresses(path, ["101", "999"])
        self.assertEqual(addresses, {"101": [["Seitengasse", "3.1", "0000"], ["Teststrasse", "10a", "0000"]], "999": []})
        self.assertTrue(connect.call_args.args[0].endswith("?mode=ro"))
        self.assertTrue(connect.call_args.kwargs["uri"])
        query = next(call for call in tracked.execute.call_args_list if call.args[0].startswith("SELECT"))
        self.assertIn("WHERE EGID IN (?,?)", query.args[0])
        self.assertEqual(query.args[1], ["101", "999"])
        tracked.close.assert_called_once()

    def test_no_ids_or_invalid_ids_never_open_a_database(self):
        with patch("egid_match.zuordnung.gwr.sqlite3.connect") as connect:
            self.assertEqual(read_gwr_addresses(ROOT / "synthetic.sqlite", []), {})
            with self.assertRaises(ReviewError):
                read_gwr_addresses(ROOT / "synthetic.sqlite", ["101 OR 1=1"])
        connect.assert_not_called()

    def test_large_egid_set_is_queried_in_parameterized_batches(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE entrance (EGID INTEGER, STRNAME TEXT, DEINR TEXT, DPLZ4 TEXT)")
        connection.executemany("INSERT INTO entrance VALUES (?, ?, ?, ?)",
                               [(value, "Testweg", "1", "0000") for value in range(1001, 1502)])
        connection.commit()
        tracked = Mock(wraps=connection)
        with patch("egid_match.zuordnung.gwr.sqlite3.connect", return_value=tracked):
            addresses = read_gwr_addresses(ROOT / "synthetic.sqlite", range(1001, 1502))
        self.assertEqual(len(addresses), 501)
        self.assertTrue(all(value == [["Testweg", "1", "0000"]] for value in addresses.values()))
        queries = [call for call in tracked.execute.call_args_list if call.args[0].startswith("SELECT")]
        self.assertEqual([len(call.args[1]) for call in queries], [500, 1])

    def test_source_errors_are_reported_and_connections_are_closed(self):
        connection = Mock()
        connection.execute.side_effect = sqlite3.OperationalError("Synthetisch fehlendes Schema")
        with patch("egid_match.zuordnung.gwr.sqlite3.connect", return_value=connection), self.assertRaises(ReviewError):
            read_gwr_addresses(ROOT / "synthetic.sqlite", ["101"])
        connection.close.assert_called_once()
        with patch("egid_match.zuordnung.gwr.sqlite3.connect", side_effect=sqlite3.OperationalError("Synthetisch nicht vorhanden")), self.assertRaises(ReviewError):
            read_gwr_addresses(ROOT / "synthetic.sqlite", ["101"])

    def test_foreign_egid_is_never_used_as_an_address_fallback(self):
        connection = Mock()
        connection.execute.side_effect = [None, None, [(999, "Fremder Testweg", "1", "0000")]]
        with patch("egid_match.zuordnung.gwr.sqlite3.connect", return_value=connection), self.assertRaises(ReviewError):
            read_gwr_addresses(ROOT / "synthetic.sqlite", ["101"])
        connection.close.assert_called_once()

    def test_pyproj_receives_easting_northing_and_always_xy(self):
        transformer = Mock()
        transformer.transform.return_value = (7.5, 47.5)
        factory = Mock(return_value=transformer)
        geometry, method = gwr_point(2600000, 1200000, factory)
        factory.assert_called_once_with("EPSG:2056", "EPSG:4326", always_xy=True)
        transformer.transform.assert_called_once_with(2600000.0, 1200000.0)
        self.assertEqual(geometry, {"type": "Point", "coordinates": [7.5, 47.5]})
        self.assertEqual(method, "pyproj")

    def test_official_formula_numerical_example_without_installation(self):
        # Reine Rechengrössen aus Swisstopo Abschnitt 2, keine Gebäudeprobe.
        with patch.dict(sys.modules, {"pyproj": None}):
            geometry, method = gwr_point(2700000, 1100000)
        self.assertEqual(method, APPROXIMATION)
        self.assertAlmostEqual(geometry["coordinates"][0], 8 + 43/60 + 49.80/3600, places=5)
        self.assertAlmostEqual(geometry["coordinates"][1], 46 + 2/60 + 38.86/3600, places=5)

    def test_invalid_coordinates_are_never_guessed_or_swapped(self):
        for pair in ((1200000, 2600000), (600000, 200000), (None, 1200000), (float("nan"), 1200000), (True, 1200000)):
            with self.subTest(pair=pair), self.assertRaises(GeometryError):
                gwr_point(*pair)

if __name__ == "__main__":
    unittest.main()

"""Paket-Einstiege und Quellcode-Ressourcen prüfen; keine echten Daten oder Dienste."""

import contextlib
import importlib
import io
from pathlib import Path
import runpy
import sqlite3
import sys
import tomllib
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import egid_match
from egid_match import matching
from egid_match.common import ReviewError
from egid_match.zuordnung import app, geo, geometrie, gwr, store


class PackageTests(unittest.TestCase):
    def test_declared_console_entries_resolve_and_show_help_without_data_access(self):
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        for command, target in config["project"]["scripts"].items():
            module, name = target.split(":", 1)
            entry = getattr(importlib.import_module(module), name)
            with self.subTest(command=command), patch.object(sys, "argv", [command, "--help"]), patch.object(sqlite3, "connect") as connection, patch.object(matching, "read_excel") as excel, patch.object(matching, "select_files") as dialog, patch.object(app, "create_app") as application, patch("webbrowser.open") as browser, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    entry()
                self.assertEqual(result.exception.code, 0)
                connection.assert_not_called()
                excel.assert_not_called()
                dialog.assert_not_called()
                application.assert_not_called()
                browser.assert_not_called()

    def test_python_module_entries_show_help_without_starting_application(self):
        for module in ("egid_match", "egid_match.zuordnung"):
            with self.subTest(module=module), patch.object(sys, "argv", [module, "--help"]), patch.object(sqlite3, "connect") as connection, patch.object(app, "create_app") as application, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    runpy.run_module(module, run_name="__main__", alter_sys=True)
                self.assertEqual(result.exception.code, 0)
                connection.assert_not_called()
                application.assert_not_called()

    def test_legacy_package_entry_delegates_to_matching(self):
        with patch.object(matching, "main") as entry:
            egid_match.main()
        entry.assert_called_once_with()

    def test_packaged_web_resources_are_served_independently_of_working_directory(self):
        application = app.create_app(ROOT / "synthetic-not-created" / "preferences.json", Mock(), resume=False)
        application.token = "synthetic-token"
        with patch.object(Path, "cwd", return_value=ROOT / "synthetic-other-directory"), patch.object(sqlite3, "connect") as connection:
            for target, content_type in (("/", "text/html"), ("/static/zuordnung.css", "text/css"), ("/static/zuordnung.js", "application/javascript"), ("/static/egid_punkte.js", "application/javascript")):
                with self.subTest(target=target):
                    response = application.handle("GET", target)
                    self.assertEqual(response.status, 200)
                    self.assertTrue(response.content_type.startswith(content_type))
                    self.assertTrue(response.body)
            connection.assert_not_called()

    def test_shared_review_error_has_same_identity_in_all_components(self):
        for module in (geo, geometrie, gwr, store, app):
            with self.subTest(module=module.__name__):
                self.assertIs(module.ReviewError, ReviewError)


if __name__ == "__main__":
    unittest.main()

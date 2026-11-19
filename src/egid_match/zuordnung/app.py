"""Lokale Windows-Anwendung für manuelle n:m-Zuordnungen; Import ohne Datenzugriff."""

import argparse
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
from urllib.parse import urlsplit
import webbrowser
from zipfile import BadZipFile

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs

from .geo import DEFAULTS, GeoBS, cached_context
from .gwr import read_gwr_addresses
from .store import FINISHED, ReviewStore, STATUSES
from ..common import ConflictError, ReviewError
from ..matching import DEFAULT_GWR_DB


class NativeDialogs:
    def __init__(self):
        self.lock = threading.Lock()

    def choose(self, kind):
        import tkinter as tk
        from tkinter import filedialog
        with self.lock:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                if kind == "database":
                    return filedialog.askopenfilename(parent=root, title="Zuordnungsdatenbank auswählen", filetypes=[("SQLite-Datenbank", "*.sqlite *.sqlite3 *.db"), ("Alle Dateien", "*.*")])
                if kind == "create":
                    return filedialog.asksaveasfilename(parent=root, title="Neue Zuordnungsdatenbank erstellen", defaultextension=".sqlite", initialfile="gvbsid_egid_zuordnung.sqlite", confirmoverwrite=True, filetypes=[("SQLite-Datenbank", "*.sqlite")])
                if kind == "excel":
                    return filedialog.askopenfilename(parent=root, title="Excel mit Adress-Suffix-Prüffällen auswählen", filetypes=[("Excel-Arbeitsmappe", "*.xlsx")])
                if kind == "export":
                    return filedialog.asksaveasfilename(parent=root, title="Gesamte Zuteilung als Excel exportieren", defaultextension=".xlsx", initialfile="gvbsid_egid_zuteilung.xlsx", confirmoverwrite=True, filetypes=[("Excel-Arbeitsmappe", "*.xlsx")])
                raise ReviewError("Unbekannter Dateidialog.")
            finally:
                root.destroy()


def settings_file():
    # Ausschliesslich beim bewussten Start der fertigen Anwendung aufrufen.
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / "egid_match" / "zuordnung.json"


class ReviewSession:
    def __init__(self, preferences, dialogs, resume=True, geo_fetcher=None, gwr_path=None):
        self.preferences = Path(preferences)
        self.dialogs = dialogs
        self.store = None
        self.active = False
        self.warning = ""
        self.config = dict(DEFAULTS)
        self.geo_fetcher = geo_fetcher
        self.gwr_path = Path(gwr_path) if gwr_path is not None else DEFAULT_GWR_DB
        self.geo_cache = {}
        self.lock = threading.RLock()
        self.revision = 0
        self.geo_requests = {}
        if resume and self.preferences.is_file():
            try:
                saved = json.loads(self.preferences.read_text(encoding="utf-8"))
                path = saved.get("database")
                if path:
                    self.store = ReviewStore(path)
                    self.store.open()
            except (OSError, ValueError, TypeError, AttributeError, sqlite3.Error):
                self.store = None
                self.warning = "Die zuletzt verwendete Datenbank oder Konfiguration ist nicht verfügbar. Bitte die Datenbank erneut auswählen."

    def remember(self):
        self.preferences.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.preferences.with_suffix(".tmp")
        payload = {"database": str(self.store.path) if self.store else None}
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.preferences)

    def require_store(self, active=False):
        if self.store is None:
            raise ReviewError("Bitte zuerst eine Zuordnungsdatenbank auswählen oder neu erstellen.")
        if active and not self.active:
            raise ReviewError("Bitte Schritt 2 mit Excel laden oder Gespeicherte Daten aktivieren bestätigen.")
        return self.store

    def state(self):
        progress = self.store.progress() if self.store else {"total": 0, "completed": 0, "impossible": 0, "remaining": 0}
        return {"database": str(self.store.path) if self.store else None, "active": self.active,
                "progress": progress, "warning": self.warning, "statuses": list(STATUSES)}

    def case(self, gvbsid):
        records = self.require_store(active=True).records()
        target = next((record for record in records if record["gvbsid"] == gvbsid), None)
        if target is None:
            raise ReviewError("GVBSID nicht gefunden. Die Suche berücksichtigt auch abgeschlossene Fälle.")
        cached = cached_context(self.geo_cache[gvbsid]) if gvbsid in self.geo_cache else {}
        grids = set(target["grids"])
        grids.update(parcel["egrid"] for parcel in cached.get("parcels", []) if parcel.get("egrid") and not cached.get("sources", {}).get("parcels", {}).get("stale"))
        grouped = [record for record in records if record["gvbsid"] == gvbsid or grids.intersection(record["grids"])]
        available = set()
        for record in grouped:
            available.update(record["candidates"] + record["suffix_candidates"] + record["assigned"])
        available.update(building["egid"] for building in cached.get("buildings", []) if building.get("assignable"))
        for record in grouped:
            record["raw"] = {key: value if isinstance(value, (str, int, float, bool, type(None))) else str(value)
                             for key, value in record["raw"].items()}
        return {"selected": gvbsid, "records": grouped, "egrids": sorted(grids),
                "egids": sorted(available, key=int), "geo": cached or None}


@dataclass
class Response:
    status: int
    body: bytes
    content_type: str = "application/json; charset=utf-8"


def json_response(value, status=200):
    return Response(status, json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))


class ReviewApplication:
    """Kleine lokale HTTP-Anwendung ohne zusaetzliches Webframework."""
    def __init__(self, preferences, dialogs, resume=True, geo_fetcher=None, gwr_path=None):
        self.session = ReviewSession(preferences, dialogs, resume, geo_fetcher, gwr_path)
        self.token = secrets.token_urlsafe(32)
        self.root = files("egid_match.zuordnung")

    def handle(self, method, target, body=b"", headers=None, remote_addr="127.0.0.1"):
        headers = {key.lower(): value for key, value in (headers or {}).items()}
        try:
            host = headers.get("host", "localhost")
            hostname = urlsplit("http://" + host).hostname
            if hostname not in ("127.0.0.1", "localhost", "::1") or remote_addr not in ("127.0.0.1", "::1"):
                return json_response({"error": "Nur lokale Zugriffe sind zugelassen."}, 403)
            if method not in ("GET", "POST"):
                return json_response({"error": "HTTP-Methode nicht zugelassen."}, 405)
            if len(body) > 1_000_000:
                return json_response({"error": "Die Anfrage ist zu gross."}, 413)
            if method == "POST":
                origin = headers.get("origin")
                if origin and origin != "http://" + host:
                    return json_response({"error": "Fremde Webseiten duerfen keine Aenderungen ausloesen."}, 403)
                token = headers.get("x-review-token", "")
                if not token.isascii() or not secrets.compare_digest(token, self.token):
                    return json_response({"error": "Ungueltige Sitzung. Bitte die Seite neu laden."}, 403)
                try:
                    data = json.loads(body or b"{}")
                except (ValueError, UnicodeError):
                    raise ReviewError("Die Anfrage enthaelt kein gueltiges JSON.")
                if not isinstance(data, dict):
                    raise ReviewError("Ungueltige Anfrage.")
            else:
                data = {}
            parts = urlsplit(target)
            path = parts.path
            if method == "GET" and path == "/":
                template = (self.root / "templates" / "zuordnung.html").read_text(encoding="utf-8")
                # Der Token enthaelt nur URL-sichere ASCII-Zeichen.
                template = template.replace("__REVIEW_CONFIG__", json.dumps({"token": self.token}))
                return Response(200, template.encode("utf-8"), "text/html; charset=utf-8")
            if method == "GET" and path in ("/static/zuordnung.css", "/static/zuordnung.js", "/static/egid_punkte.js"):
                name = path.rsplit("/", 1)[1]
                content_type = "text/css; charset=utf-8" if name.endswith(".css") else "application/javascript; charset=utf-8"
                return Response(200, (self.root / "static" / name).read_bytes(), content_type)
            if method == "GET":
                with self.session.lock:
                    if path == "/api/state":
                        return json_response(self.session.state())
                    if path == "/api/queue":
                        records = self.session.require_store(active=True).records()
                        return json_response({"records": [{key: row[key] for key in ("gvbsid", "purpose", "address", "status")} for row in records if row["status"] not in FINISHED]})
                    if path == "/api/case":
                        query = parse_qs(parts.query)
                        gvbsid = query.get("gvbsid", [""])[0]
                        return json_response(self.session.case(gvbsid))
            routes = {
                "/api/database/select": lambda: self.database("select"),
                "/api/database/create": lambda: self.database("create"),
                "/api/import": self.import_excel, "/api/activate": self.activate,
                "/api/save": lambda: self.save(data), "/api/export": self.export,
                "/api/geo": lambda: self.geo(data),
            }
            if method == "POST" and path in routes:
                return json_response(routes[path]())
            return json_response({"error": "Nicht gefunden."}, 404)
        except ConflictError as error:
            return json_response({"error": str(error)}, 409)
        except ReviewError as error:
            return json_response({"error": str(error)}, 400)
        except FileExistsError:
            return json_response({"error": "Die Datei existiert bereits und wird nicht ueberschrieben. Bitte einen neuen Dateinamen waehlen."}, 400)
        except sqlite3.Error:
            return json_response({"error": "Die Datenbank konnte nicht sicher gelesen oder gespeichert werden. Speicherort, Schreibrechte und Format pruefen."}, 400)
        except BadZipFile:
            return json_response({"error": "Die Datei ist keine lesbare .xlsx-Arbeitsmappe."}, 400)
        except OSError:
            return json_response({"error": "Die ausgewaehlte Datei ist nicht verfuegbar oder kann nicht geschrieben werden."}, 400)

    def database(self, action):
        session = self.session
        path = session.dialogs.choose("database" if action == "select" else "create")
        if not path:
            return {"cancelled": True}
        with session.lock:
            store = ReviewStore.create(path) if action == "create" else ReviewStore(path)
            if action == "select":
                store.open()
            session.store, session.active, session.warning = store, False, ""
            session.geo_cache.clear()
            session.revision += 1
            session.remember()
            return session.state()

    def import_excel(self):
        session = self.session
        with session.lock:
            store = session.require_store()
        path = session.dialogs.choose("excel")
        if not path:
            return {"cancelled": True}
        if Path(path).suffix.lower() != ".xlsx":
            raise ReviewError("Bitte eine .xlsx-Datei auswaehlen.")
        with session.lock:
            if store is not session.store:
                raise ConflictError("Die aktive Datenbank wurde inzwischen gewechselt. Bitte erneut importieren.")
            count = store.import_excel(path)
            session.active = True
            session.geo_cache.clear()
            session.revision += 1
            return {"imported": count, **session.state()}

    def activate(self):
        session = self.session
        with session.lock:
            if not session.require_store().progress()["total"]:
                raise ReviewError("Noch keine Importdaten vorhanden. Bitte Excel laden.")
            session.active = True
            return session.state()

    def save(self, data):
        session = self.session
        if not isinstance(data.get("decisions"), list):
            raise ReviewError("Ungueltige Entscheidungen.")
        with session.lock:
            current = session.case(data.get("selected", ""))
            allowed_records = {row["gvbsid"] for row in current["records"]}
            if not all(isinstance(row, dict) and row.get("gvbsid") in allowed_records for row in data["decisions"]):
                raise ReviewError("Die Entscheidungen gehoeren nicht zum geoeffneten Fall.")
            session.store.save(data["decisions"], current["egids"])
            return session.state()

    def export(self):
        session = self.session
        with session.lock:
            store = session.require_store(active=True)
        path = session.dialogs.choose("export")
        if not path:
            return {"cancelled": True}
        path = Path(path)
        if path.suffix.lower() != ".xlsx" or path.resolve() == store.path:
            raise ReviewError("Bitte einen separaten .xlsx-Ausgabepfad waehlen.")
        with session.lock:
            if store is not session.store:
                raise ConflictError("Die Datenbank wurde inzwischen gewechselt. Bitte erneut exportieren.")
            workbook = store.export_workbook()
            try:
                workbook.save(path)
            finally:
                workbook.close()
        return {"path": str(path)}

    def geo(self, data):
        session = self.session
        with session.lock:
            current = session.case(data.get("selected", ""))
            store, config, revision = session.store, dict(session.config), session.revision
            selected = next(record for record in current["records"] if record["gvbsid"] == current["selected"])
            request_id = session.geo_requests.get(current["selected"], 0) + 1
            session.geo_requests[current["selected"]] = request_id
        point = data.get("point")
        if point is not None and selected["grids"]:
            raise ReviewError("Bei bekannter EGRID wird der eindeutige Identifikatorfilter verwendet.")
        service = GeoBS(config, session.geo_fetcher) if session.geo_fetcher else GeoBS(config)
        context = service.context([] if point is not None else current["egrids"], current["egids"], section=selected["raw"].get("Sektionsname") if point is None else None,
                                  number=selected["raw"].get("Parzellennummer") if point is None else None, point=point, statuses=("1004",))
        # Ungeprüfte oder andere Status auch aus einem unvollständigen
        # Quellenprofil nicht als Kartenobjekte oder Zusatzkandidaten anbieten.
        context["buildings"] = [building for building in context["buildings"] if building["gstat"] == "1004"]
        try:
            addresses = read_gwr_addresses(session.gwr_path, [building["egid"] for building in context["buildings"]])
            for building in context["buildings"]:
                building["addresses"] = addresses.get(building["egid"], [])
                building["address"] = building["addresses"][0] if building["addresses"] else []
            context["gwr_address_status"] = {"code": "complete", "message": "GWR-Adressen über die vorhandene entrance.EGID-Verknüpfung gelesen."}
        except ReviewError as error:
            context["gwr_address_status"] = {"code": "unreachable", "message": str(error)}
        with session.lock:
            if store is not session.store or revision != session.revision or session.geo_requests.get(current["selected"]) != request_id:
                raise ConflictError("Datenbank oder Geokonfiguration wurde inzwischen geaendert. Bitte die Karte neu laden.")
            session.geo_cache[current["selected"]] = context
            return session.case(current["selected"])["geo"]


def create_app(preferences=None, dialogs=None, *, resume=True, geo_fetcher=None, gwr_path=None):
    return ReviewApplication(preferences if preferences is not None else settings_file(), dialogs or NativeDialogs(), resume, geo_fetcher, gwr_path)


def request_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.respond()

        def do_POST(self):
            self.respond()

        def log_message(self, *arguments):
            pass

        def respond(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 1_000_000:
                    response = json_response({"error": "Die Anfrage ist zu gross."}, 413)
                else:
                    body = self.rfile.read(length) if self.command == "POST" else b""
                    response = app.handle(self.command, self.path, body, dict(self.headers), self.client_address[0])
            except (ValueError, OSError):
                response = json_response({"error": "Die Anfrage konnte nicht verarbeitet werden."}, 400)
            except Exception:
                response = json_response({"error": "Die Aktion konnte nicht abgeschlossen werden. Bitte Eingaben und Konfiguration pruefen."}, 500)
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(response.body)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Lokales GVBSID-EGID-Zuordnungswerkzeug")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--gwr-db", type=Path, help="GWR-Datenbank für EGID-Adressen; Standard ist der im Matching konfigurierte GWR-Pfad.")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Der Port muss zwischen 1024 und 65535 liegen.")
    app = create_app(gwr_path=args.gwr_db)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), request_handler(app))
    url = f"http://127.0.0.1:{args.port}"
    print(f"Zuordnungswerkzeug: {url} (Beenden mit Strg+C)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

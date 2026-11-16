"""Begrenzte öffentliche Vektorabfragen; keine Adresssuche und kein WMS-Bildparser."""

import json
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.sax.saxutils import escape

from ..common import ReviewError


CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
MAX_BYTES = 12_000_000
MAX_TOTAL_BYTES = 24_000_000
MAX_PAGES = 20
MAX_SECONDS = 45


class SourceError(ReviewError):
    def __init__(self, code, message, partial=None):
        super().__init__(message)
        self.code = code
        self.partial = partial or []


def public_url(url):
    try:
        parts = urlsplit(url)
        valid = parts.scheme == "https" and (parts.hostname or "").endswith(".bs.ch") and not parts.username and not parts.password and not parts.fragment and parts.port in (None, 443)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise SourceError("invalid", "Nur freigegebene öffentliche HTTPS-Quellen unter *.bs.ch ohne Zugangsdaten sind zulässig.")
    return url


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, *arguments):
        raise SourceError("unreachable", "Der Dienst leitet weiter. Die freigegebene HTTPS-Zieladresse muss geprüft werden.")


def fetch_json(url, timeout=15):
    public_url(url)
    request = Request(url, headers={"Accept": "application/geo+json, application/json", "User-Agent": "EGID-Zuordnungswerkzeug/1.1"})
    with build_opener(_NoRedirects).open(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if "json" not in content_type:
            raise SourceError("invalid", "Der Dienst antwortet nicht mit JSON/GeoJSON.")
        raw = response.read(MAX_BYTES + 1)
        content_crs = response.headers.get("Content-Crs")
    if len(raw) > MAX_BYTES:
        raise SourceError("incomplete", "Das Antwortgrössenlimit wurde erreicht.")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise SourceError("invalid", "Die Dienstantwort ist kein gültiges JSON.") from error
    if isinstance(result, dict) and content_crs:
        result["_response_crs"] = content_crs.strip("<>")
    return result


class SourceClient:
    def __init__(self, config, fetcher=None):
        self.config = config
        self.fetcher = fetcher
        self.deadline = None
        self.requested = {"parcel": 0, "building": 0}
        self.received = {"parcel": 0, "building": 0}

    def start(self):
        self.deadline = time.monotonic() + MAX_SECONDS
        self.requested = {"parcel": 0, "building": 0}
        self.received = {"parcel": 0, "building": 0}

    def _call(self, url, prefix):
        for attempt in range(2):
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise SourceError("incomplete", "Die maximale Abfragedauer ist erreicht.")
            try:
                self.requested[prefix] += 1
                result = self.fetcher(url) if self.fetcher else fetch_json(url, timeout=min(15, remaining))
                self.received[prefix] += 1
                if time.monotonic() > self.deadline:
                    raise SourceError("incomplete", "Die maximale Abfragedauer ist erreicht.")
                return result
            except HTTPError as error:
                transient = error.code in (408, 429, 500, 502, 503, 504)
                if not transient or attempt:
                    raise SourceError("unreachable", f"Der öffentliche Dienst antwortet mit HTTP {error.code}.") from error
            except (URLError, TimeoutError, OSError) as error:
                if attempt:
                    raise SourceError("unreachable", "Der öffentliche Dienst ist nicht erreichbar oder die Zeitüberschreitung besteht weiter.") from error
            if self.deadline - time.monotonic() < .1:
                raise SourceError("incomplete", "Keine Zeit für eine begrenzte Wiederholung vorhanden.")
            time.sleep(.1)

    def features(self, prefix, filters=None, bbox=None):
        if self.deadline is None:
            self.start()
        config = self.config
        base = config[prefix + "_url"]
        if not base:
            raise SourceError("not_configured", "Für diese Quelle ist kein belegter öffentlicher Endpunkt hinterlegt.")
        public_url(base)
        mode = config[prefix + "_mode"]
        filters = filters or {}
        for name, value in filters.items():
            if not re.fullmatch(r"[A-Za-z_][\w.:-]*", name) or not re.fullmatch(r"[\w -]+", str(value)):
                raise SourceError("invalid", "Ein Identifikatorfilter ist ungültig.")
        parts = urlsplit(base)
        params = {}
        limit = 100 if mode == "ods" else 1000
        if mode == "ods":
            if not filters:
                raise SourceError("not_configured", "Die GWR-Quelle benötigt einen belegten EGID-/EGRID-Filter; eine Koordinatensuche wird nicht erfunden.")
            names = [config.get("building_" + suffix, "") for suffix in ("egid", "egrid", "gstat", "easting", "northing", "updated")]
            params = {"limit": limit, "offset": 0, "select": ",".join(name for name in names if name),
                      "where": " AND ".join(f"{field} = {int(value) if field == config['building_egid'] and str(value).isdigit() else json.dumps(str(value))}" for field, value in filters.items()),
                      "order_by": config["building_egid"] + " ASC"}
        elif mode in ("qgis", "ogc"):
            params = {"limit": limit, "crs": CRS84}
            if mode == "qgis":
                params.update(filters)
                if config.get(prefix + "_map"):
                    params["MAP"] = config[prefix + "_map"]
            elif filters:
                params.update({"filter-lang": "cql2-text", "filter": " AND ".join(f"{field} = '{value}'" for field, value in filters.items())})
            if bbox:
                params["bbox"] = ",".join(str(number) for number in bbox)
                params["bbox-crs"] = CRS84
        elif mode == "wfs":
            expressions = "".join("<ogc:PropertyIsEqualTo><ogc:PropertyName>" + escape(field) + "</ogc:PropertyName><ogc:Literal>" + escape(str(value)) + "</ogc:Literal></ogc:PropertyIsEqualTo>" for field, value in filters.items())
            if len(filters) > 1:
                expressions = "<ogc:And>" + expressions + "</ogc:And>"
            params = {"service": "WFS", "version": "1.1.0", "request": "GetFeature", "typeName": config[prefix + "_layer"],
                      "outputFormat": "application/json", "srsName": "urn:ogc:def:crs:OGC:1.3:CRS84", "maxFeatures": limit,
                      "filter": '<ogc:Filter xmlns:ogc="http://www.opengis.net/ogc">' + expressions + '</ogc:Filter>'}
            if bbox:
                raise SourceError("not_configured", "Räumliche Abfragen sind für dieses WFS-Profil nicht belegt.")
        else:
            raise SourceError("not_configured", "Das Quellenprotokoll ist nicht eingerichtet.")
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))
        required_params = {key: str(value) for key, value in params.items() if key not in ("limit", "offset", "maxFeatures")}
        result, seen, total_bytes, expected_total = [], set(), 0, None
        try:
            for _ in range(MAX_PAGES):
                normalized_url = urlunsplit((*urlsplit(url)[:3], urlencode(sorted((key, value) for key, values in parse_qs(urlsplit(url).query).items() for value in values)), ""))
                if normalized_url in seen:
                    raise SourceError("incomplete", "Die Seitennavigation enthält eine Schleife.")
                seen.add(normalized_url)
                data = self._call(url, prefix)
                if not isinstance(data, dict):
                    raise SourceError("invalid", "Die Antwort besitzt nicht das erwartete Objektschema.")
                total_bytes += len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
                if total_bytes > MAX_TOTAL_BYTES:
                    raise SourceError("incomplete", "Die Gesamtgrösse aller Antwortseiten überschreitet das Sicherheitslimit.")
                if mode == "ods":
                    records = data.get("results")
                    total = data.get("total_count")
                    if not isinstance(records, list) or type(total) is not int or total < 0:
                        raise SourceError("invalid", "Die GWR-API liefert kein gültiges results-/total_count-Schema.")
                    features = []
                    for record in records:
                        if not isinstance(record, dict):
                            raise SourceError("invalid", "Ein GWR-Datensatz ist kein Objekt.")
                        x, y = record.get(config["building_easting"]), record.get(config["building_northing"])
                        geometry = {"type": "Point", "coordinates": [x, y]} if x is not None and y is not None else None
                        features.append({"type": "Feature", "properties": record, "geometry": geometry, "_source_crs": config["building_crs"]})
                else:
                    features = data.get("features")
                    if data.get("type") != "FeatureCollection" or not isinstance(features, list):
                        raise SourceError("invalid", "HTTP 200 ohne gültige GeoJSON-FeatureCollection.")
                    crs = data.get("crs")
                    if crs is not None and (not isinstance(crs, dict) or not isinstance(crs.get("properties"), dict) or not crs["properties"].get("name")):
                        raise SourceError("invalid", "Die CRS-Deklaration ist ungültig.")
                    declaration = data.get("_response_crs") or (crs or {}).get("properties", {}).get("name") or "CRS84"
                    for feature in features:
                        if isinstance(feature, dict):
                            feature["_source_crs"] = declaration
                    total = data.get("numberMatched")
                    if total is not None and (type(total) is not int or total < 0):
                        if total != "unknown":
                            raise SourceError("invalid", "Die Treffergesamtzahl ist ungültig.")
                        total = None
                    if data.get("numberReturned") is not None and data["numberReturned"] != len(features):
                        raise SourceError("invalid", "numberReturned stimmt nicht mit der Antwort überein.")
                if any(not isinstance(feature, dict) or feature.get("type") != "Feature" or not isinstance(feature.get("properties"), dict) for feature in features):
                    raise SourceError("invalid", "Ein Feature besitzt kein gültiges Attributschema.")
                if any(str(feature["properties"].get(field, "")) != str(value) for feature in features for field, value in filters.items()):
                    raise SourceError("invalid", "Der Dienst hat einen Identifikatorfilter ignoriert oder liefert fremde Kennungen.")
                result.extend(features)
                if expected_total is not None and total != expected_total:
                    raise SourceError("incomplete", "Der Quellenbestand hat sich während der Seitenabfrage geändert.")
                if total is not None:
                    expected_total = total
                if total is not None and len(result) > total:
                    raise SourceError("invalid", "Mehr Treffer als in der Gesamtsumme angegeben.")
                if mode == "ods":
                    if len(result) == total:
                        return result
                    if not features or len(result) >= 10000:
                        raise SourceError("incomplete", "Die GWR-Seitenbegrenzung verhindert eine vollständige Antwort.")
                    params["offset"] = len(result)
                    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), ""))
                    continue
                links = data.get("links", [])
                if not isinstance(links, list) or any(not isinstance(link, dict) for link in links):
                    raise SourceError("invalid", "Die Seitennavigation ist ungültig.")
                next_urls = [link.get("href") for link in links if link.get("rel") == "next"]
                if len(next_urls) > 1:
                    raise SourceError("invalid", "Mehrere widersprüchliche nächste Seiten.")
                if next_urls:
                    if not isinstance(next_urls[0], str):
                        raise SourceError("invalid", "Die nächste Seite besitzt keine gültige URL.")
                    target = urlsplit(urljoin(url, next_urls[0]))
                    # QGIS publiziert hinter dem HTTPS-Proxy teilweise HTTP-Selbstlinks.
                    # Ausschliesslich derselbe bereits freigegebene Host/Pfad wird auf HTTPS angehoben.
                    if target.scheme == "http" and target.hostname == parts.hostname and target.port is None:
                        target = target._replace(scheme="https")
                    next_url = public_url(urlunsplit(target))
                    query = parse_qs(target.query)
                    if target.netloc != parts.netloc or target.path != parts.path or any(query.get(key) != [value] for key, value in required_params.items()):
                        raise SourceError("incomplete", "Die nächste Seite verlässt die freigegebene Quelle oder verliert Filter/CRS.")
                    url = next_url
                    continue
                if (total is not None and len(result) != total) or (total is None and len(features) >= limit):
                    raise SourceError("incomplete", "Weitere Treffer sind möglich, aber es fehlt eine vollständige Seitennavigation.")
                return result
            raise SourceError("incomplete", "Das Seitenlimit wurde erreicht.")
        except SourceError as error:
            if not error.partial:
                error.partial = result
            raise

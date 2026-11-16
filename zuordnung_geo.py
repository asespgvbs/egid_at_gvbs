"""Getrennte, belegte Parzellen-/Gebäudequellen mit nachvollziehbaren Zuständen."""

import copy
from datetime import datetime, timezone
import re
from urllib.parse import urlsplit

from zuordnung_geometrie import GeometryError, bounds, geometry_relation, normalize_geometry, point_location, validate_geometry
from zuordnung_geo_transport import SourceClient, SourceError, fetch_json, public_url
from zuordnung_quellen import PUBLIC_SOURCES
from zuordnung_store import ReviewError, egid_text, identifiers
from zuordnung_gwr import gwr_point, APPROXIMATION

DEFAULTS = dict(PUBLIC_SOURCES)
FIELDS = tuple(DEFAULTS)
LABELS = {"not_configured": "Nicht konfiguriert", "unreachable": "Dienst nicht erreichbar",
          "invalid": "Antwort oder Schema ungültig", "empty": "Erfolgreich abgefragt, keine Treffer",
          "ambiguous": "Zuordnung mehrdeutig", "incomplete": "Ergebnis unvollständig",
          "complete": "Vollständig im dokumentierten Quellenumfang", "stale": "Cache veraltet",
          "transform_missing": "Koordinatentransformation nicht verfügbar"}
CACHE_SECONDS = 300


def validate_config(config):
    if not isinstance(config, dict):
        raise ReviewError("Ungültiges Quellenprofil.")
    result = {key: str(config.get(key, default)).strip() for key, default in DEFAULTS.items()}
    for prefix in ("parcel", "building"):
        if not result[prefix + "_url"]:
            continue
        public_url(result[prefix + "_url"])
        if urlsplit(result[prefix + "_url"]).query or result[prefix + "_mode"] not in ("qgis", "ogc", "wfs", "ods"):
            raise ReviewError("Ungültige Quellen-URL oder nicht belegtes Protokoll.")
        if result[prefix + "_mode"] == "wfs" and not re.fullmatch(r"[\w.:-]+", result[prefix + "_layer"]):
            raise ReviewError("Für WFS fehlt der belegte Layername.")
        if not result["parcel_egrid" if prefix == "parcel" else "building_egid"]:
            raise ReviewError("Ein erforderlicher Identifikator-Feldname fehlt.")
    for field in ("parcel_egrid", "parcel_section", "parcel_number", "building_egrid", "building_egid", "building_gstat", "building_easting", "building_northing", "building_updated", "building_street", "building_number", "building_postal"):
        if result[field] and not re.fullmatch(r"[A-Za-z_][\w.:-]*", result[field]):
            raise ReviewError("Ein Quellen-Feldname ist ungültig.")
    return result


def valid_geometry(geometry, parcel=False):
    try:
        validate_geometry(geometry, parcel=parcel)
        return True
    except GeometryError:
        return False


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def source_state(config, prefix, code, message, queried=False, received=False):
    return {"code": code, "label": LABELS[code], "message": message,
            "source": config[prefix + "_source"], "url": config[prefix + "_url"], "scope": config[prefix + "_scope"],
            "fetched_at": _now() if received else None,
            "attempted_at": _now() if queried else None, "complete": code in ("complete", "empty"), "stale": False}


def cached_context(context, now=None):
    result = copy.deepcopy(context)
    now = now or datetime.now(timezone.utc)
    for state in result.get("sources", {}).values():
        if state.get("fetched_at") and (now - datetime.fromisoformat(state["fetched_at"])).total_seconds() > CACHE_SECONDS:
            state.update(previous_code=state["code"], code="stale", label=LABELS["stale"], complete=False, stale=True)
    if any(state.get("stale") for state in result.get("sources", {}).values()):
        result.setdefault("warnings", []).append("Geodaten älter als fünf Minuten; vor neuen Zuordnungen Karte neu laden.")
        for building in result.get("buildings", []):
            building["assignable"] = False
    return result


class GeoBS:
    def __init__(self, config=None, fetcher=None, transformer_factory=None):
        self.config = validate_config(config if config is not None else DEFAULTS)
        self.client = SourceClient(self.config, fetcher)
        self.transformer_factory = transformer_factory

    def features(self, prefix, field, identifier):
        return self.client.features(prefix, {field: identifier})

    def _state(self, prefix, code, message):
        return source_state(self.config, prefix, code, message, bool(self.client.requested[prefix]), bool(self.client.received[prefix]))

    def _geometry(self, feature, prefix, parcel=False):
        return normalize_geometry(feature.get("geometry"), feature.get("_source_crs", self.config[prefix + "_crs"]),
                                  self.config[prefix + "_axis"], self.transformer_factory, parcel=parcel, deadline=self.client.deadline)

    def _parcels(self, egrids, section, number, point):
        config = self.config
        if not config["parcel_url"]:
            raise SourceError("not_configured", "Keine belegte Parzellenquelle eingerichtet.")
        if egrids:
            queries = [{config["parcel_egrid"]: value} for value in sorted(egrids)]
        elif section and number:
            queries = [{config["parcel_section"]: section, config["parcel_number"]: number}]
        elif section or number:
            raise SourceError("ambiguous", "Sektionsname und Parzellennummer müssen gemeinsam bekannt sein.")
        elif point is not None:
            normalize_geometry({"type": "Point", "coordinates": point}, "CRS84")
            queries = [{}]
        else:
            raise SourceError("ambiguous", "Keine EGRID, keine vollständige Sektion/Parzellennummer und kein Kartenpunkt vorhanden.")
        if len(queries) > 20:
            raise SourceError("incomplete", "Zu viele Grundstücksschlüssel für eine begrenzte Abfrage.")
        selected = []
        for filters in queries:
            bbox = None if point is None else [max(-180, point[0] - .000001), max(-90, point[1] - .000001), min(180, point[0] + .000001), min(90, point[1] + .000001)]
            features = self.client.features("parcel", filters, bbox)
            candidates, boundary = [], False
            for feature in features:
                properties = feature["properties"]
                if any(config[field] not in properties for field in ("parcel_egrid", "parcel_section", "parcel_number")):
                    raise SourceError("invalid", "Im Parzellenschema fehlt ein dokumentiertes Schlüsselattribut.")
                geometry = self._geometry(feature, "parcel", parcel=True)
                if config["parcel_extent"]:
                    extent = [float(value) for value in config["parcel_extent"].split(",")]
                    box = bounds(geometry)
                    if box[2] < extent[0] or box[0] > extent[2] or box[3] < extent[1] or box[1] > extent[3]:
                        raise SourceError("invalid", "Die Geometrie widerspricht der publizierten Collection-Ausdehnung. CRS und Achsen prüfen; es wird nichts automatisch vertauscht.")
                if point is not None:
                    location = point_location(point, geometry, self.client.deadline)
                    boundary |= location == "boundary"
                    if location != "inside":
                        continue
                egrid, sec, num = (str(properties.get(config[field]) or "").strip() for field in ("parcel_egrid", "parcel_section", "parcel_number"))
                if not egrid and not (sec and num):
                    raise SourceError("invalid", "Das Polygon besitzt keinen belegten Grundstücksschlüssel.")
                candidates.append({"key": egrid or f"section:{sec}:number:{num}", "egrid": egrid or None,
                                   "section": sec, "number": num, "label": egrid or f"Sektion {sec}, Nr. {num}", "geometry": geometry})
            if boundary or len(candidates) > 1:
                raise SourceError("ambiguous", "Mehrere Parzellen oder ein Punkt auf einer Grundstücks-/Innenringgrenze; kein erster Treffer wird übernommen.")
            selected.extend(candidates)
        return selected

    def _building(self, feature, parcel, authoritative, statuses):
        config, properties = self.config, feature["properties"]
        if config["building_egid"] not in properties:
            raise SourceError("invalid", "Das Gebäudeschema enthält kein dokumentiertes EGID-Feld.")
        try:
            egid = egid_text(properties[config["building_egid"]])
        except ReviewError as error:
            raise SourceError("invalid", "Ein Gebäudedatensatz hat keine gültige EGID.") from error
        status_field = config["building_gstat"]
        status = str(properties.get(status_field, "")) if status_field else ""
        if status_field and status_field not in properties:
            raise SourceError("invalid", "Das konfigurierte GSTAT-Feld fehlt in der Antwort.")
        if status and statuses and status not in statuses:
            return None
        geometry, note, review, geometry_error = None, "", False, ""
        approximate = False
        if feature.get("geometry") is not None:
            try:
                geometry = self._geometry(feature, "building")
            except GeometryError as error:
                note = str(error)
                geometry_error = error.code
                review = error.code != "transform_missing"
                if error.code == "transform_missing" and feature["geometry"].get("type") == "Point" and config["building_axis"] == "xy":
                    try:
                        geometry, method = gwr_point(*feature["geometry"]["coordinates"][:2])
                        approximate = method == APPROXIMATION
                        note, geometry_error = method, ""
                    except GeometryError:
                        pass
                if not authoritative:
                    review = True
        else:
            note, review = "Keine Gebäudeposition/-geometrie in der Quelle vorhanden.", not authoritative
        relation = "Amtliche EGRID-Beziehung der Quelle" if authoritative else "Position nicht verlässlich prüfbar"
        if geometry is not None and parcel.get("geometry") is not None and not approximate:
            spatial = geometry_relation(geometry, parcel["geometry"], self.client.deadline)
            if not authoritative and spatial == "outside":
                return None
            if spatial in ("boundary", "crosses") or (authoritative and spatial == "outside"):
                review, relation = True, "Grenzlage, mehrere Grundstücke oder Widerspruch zur Geometrie; klärungsbedürftig"
            elif not authoritative:
                relation = "Räumlich abgeleitet über vollständige Gebäudegeometrie"
                if geometry["type"] in ("Point", "MultiPoint"):
                    relation = "Räumlich abgeleitet über Gebäudepunkt"
                    if config["building_point_role"] != "building":
                        review, relation = True, "Eingangs-/Punktlage beweist keine eindeutige Gebäudezugehörigkeit"
        if not authoritative and (parcel.get("geometry") is None or approximate):
            review, relation = True, "Punkt zur Anzeige; Grundstückszugehörigkeit nicht bestätigt"
        address = [str(properties.get(config[name]) or "").strip() if config[name] else "" for name in ("building_street", "building_number", "building_postal")]
        return {"egid": egid, "geometry": geometry, "egrid": parcel["egrid"], "egrids": [parcel["egrid"]] if parcel["egrid"] else [],
                "address": address, "addresses": [address] if any(address) else [], "gstat": status, "gstat_verified": bool(status),
                "relation": relation, "needs_review": review, "assignable": not review,
                "geometry_note": note, "geometry_error": geometry_error,
                "source_updated": properties.get(config["building_updated"]), "position_role": config["building_point_role"]}

    def context(self, egrids, candidate_egids, *, section=None, number=None, point=None, statuses=("1004",)):
        self.client.start()
        config, egrids = self.config, set(egrids)
        section = str(section).strip() if section is not None else None
        number = str(number).strip() if number is not None else None
        statuses = tuple(str(value) for value in statuses)
        if any(not re.fullmatch(r"\d{4}", value) for value in statuses):
            raise ReviewError("Ungültiger Gebäudestatusfilter.")
        sources = {key: source_state(config, prefix, "not_configured", "Quelle noch nicht abgefragt.") for key, prefix in (("parcels", "parcel"), ("buildings", "building"))}
        parcels, buildings, warnings = [], [], []
        if not egrids and not (section or number) and point is None and config["building_url"] and config["building_egrid"]:
            try:
                if len(candidate_egids) > 20:
                    raise SourceError("incomplete", "Zu viele Kandidaten für eine begrenzte Grundstücksidentifikation.")
                for egid in sorted(candidate_egids):
                    for feature in self.client.features("building", {config["building_egid"]: egid}):
                        egrids.update(identifiers(feature["properties"].get(config["building_egrid"])))
            except SourceError as error:
                sources["buildings"] = self._state("building", error.code, str(error))
        try:
            parcels = self._parcels(egrids, section, number, point)
            sources["parcels"] = self._state("parcel", "complete" if parcels else "empty",
                f"{len(parcels)} eindeutige Grundstücksgeometrie(n)." if parcels else "Keine zum vollständigen Schlüssel oder Punkt passende Parzelle.")
        except (SourceError, GeometryError) as error:
            sources["parcels"] = self._state("parcel", error.code, str(error))
        if not config["building_url"]:
            sources["buildings"] = source_state(config, "building", "not_configured", "Keine belegte öffentliche EGID-Quelle eingerichtet; die Parzellenquelle bleibt unabhängig nutzbar.")
        else:
            failure = None
            queries = [(parcel, bool(config["building_egrid"] and parcel["egrid"]),
                        {config["building_egrid"]: parcel["egrid"]} if config["building_egrid"] and parcel["egrid"] else None) for parcel in parcels]
            if not parcels:
                if egrids and config["building_egrid"] and len(egrids) <= 20:
                    queries = [({"egrid": egrid, "geometry": None}, True, {config["building_egrid"]: egrid}) for egrid in sorted(egrids)]
                elif len(candidate_egids) <= 20:
                    queries = [({"egrid": None, "geometry": None}, False, {config["building_egid"]: egid}) for egid in sorted(candidate_egids)]
                else:
                    failure = SourceError("incomplete", "Zu viele Kandidaten für eine begrenzte unabhängige EGID-Abfrage.")
            for parcel, authoritative, filters in queries:
                try:
                    features = self.client.features("building", filters) if filters is not None else self.client.features("building", bbox=bounds(parcel["geometry"]))
                except SourceError as error:
                    failure, features = error, error.partial
                try:
                    for feature in features:
                        building = self._building(feature, parcel, authoritative, statuses)
                        if building is not None:
                            buildings.append(building)
                except (SourceError, GeometryError) as error:
                    failure = error
            deduplicated = {}
            for building in buildings:
                existing = deduplicated.get(building["egid"])
                if existing is None:
                    building["_geometries"] = [building["geometry"]] if building["geometry"] else []
                    deduplicated[building["egid"]] = building
                    continue
                for field in ("addresses", "egrids"):
                    for value in building[field]:
                        if value not in existing[field]:
                            existing[field].append(value)
                if building["geometry"] and building["geometry"] not in existing["_geometries"]:
                    existing["_geometries"].append(building["geometry"])
                existing["needs_review"] |= building["needs_review"] or existing["gstat"] != building["gstat"] or existing["position_role"] != building["position_role"]
                existing["assignable"] &= building["assignable"]
                if building["geometry_error"]:
                    existing["geometry_error"] = building["geometry_error"]
                    existing["geometry_note"] = building["geometry_note"]
            buildings = list(deduplicated.values())
            for building in buildings:
                geometries = building.pop("_geometries")
                if len(geometries) > 1:
                    building["geometry"] = ({"type": "MultiPoint", "coordinates": [geometry["coordinates"] for geometry in geometries]}
                                            if all(geometry["type"] == "Point" for geometry in geometries)
                                            else {"type": "GeometryCollection", "geometries": geometries})
                if len(building["egrids"]) > 1 or building["needs_review"]:
                    building.update(needs_review=True, assignable=False)
                    if len(building["egrids"]) > 1:
                        building["relation"] = "Beziehung zu mehreren Parzellen; klärungsbedürftig"
            if failure:
                sources["buildings"] = self._state("building", failure.code, str(failure))
            elif any(building["geometry_error"] == "invalid" for building in buildings):
                sources["buildings"] = self._state("building", "invalid", "Die Quelle enthält eine ungültige Gebäudegeometrie; die betreffende Beziehung wird nicht freigeschaltet.")
            elif any(building["geometry_error"] == "incomplete" for building in buildings):
                sources["buildings"] = self._state("building", "incomplete", "Die Geometrieprüfung hat ein Sicherheitslimit erreicht.")
            elif any(building["needs_review"] for building in buildings):
                sources["buildings"] = self._state("building", "ambiguous", "Mindestens eine Gebäudezugehörigkeit oder Geometrie ist klärungsbedürftig.")
            elif any(building["geometry"] is None or not building["gstat_verified"] for building in buildings) or (statuses and not config["building_gstat"]):
                sources["buildings"] = self._state("building", "incomplete", "EGID-Beziehungen geladen; Positionen oder der gewählte GSTAT-Filter sind nicht vollständig prüfbar.")
            else:
                approximate = sum(building["geometry_note"] == APPROXIMATION for building in buildings)
                message = f"{len(buildings)} unterschiedliche EGID im Quellenumfang und Statusfilter."
                if approximate:
                    message += f" {approximate} Position(en) mit Swisstopo-Näherung nur zur Kartendarstellung; keine räumliche Grenzprüfung."
                sources["buildings"] = self._state("building", "complete" if buildings else "empty", message)
        for state in sources.values():
            if state["code"] not in ("complete", "empty"):
                warnings.append(state["message"])
        warnings.extend(f"EGID {building['egid']}: {building['geometry_note']}" for building in buildings if building["geometry_note"])
        if len(parcels) > 1:
            warnings.append("Mehrere eindeutige Grundstücke gehören zum Fall; aktive Parzelle ausdrücklich auswählen.")
        return {"parcels": parcels, "buildings": sorted(buildings, key=lambda building: int(building["egid"])), "sources": sources,
                "warnings": sorted(set(warnings)), "filters": {"gstat": list(statuses)}, "query_point": point, "retrieved_at": _now()}

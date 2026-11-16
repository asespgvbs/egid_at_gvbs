"""Explizite CRS-Behandlung und konservative Polygonprüfungen ohne Dateneinlesung."""

import copy
import math
import time

from zuordnung_store import ReviewError


EPSILON = 1e-11
MAX_VERTICES = 4000


class GeometryError(ReviewError):
    def __init__(self, message, code="invalid"):
        super().__init__(message)
        self.code = code


def _budget(deadline):
    if deadline is not None and time.monotonic() > deadline:
        raise GeometryError("Die maximale Dauer der Geometrieprüfung ist erreicht.", "incomplete")


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(point, a, b):
    return abs(_cross(a, b, point)) <= EPSILON and all(
        min(a[axis], b[axis]) - EPSILON <= point[axis] <= max(a[axis], b[axis]) + EPSILON
        for axis in (0, 1))


def segments_intersect(a, b, c, d, proper=False):
    if any(max(a[axis], b[axis]) < min(c[axis], d[axis]) - EPSILON or max(c[axis], d[axis]) < min(a[axis], b[axis]) - EPSILON for axis in (0, 1)):
        return False
    ab_c, ab_d, cd_a, cd_b = _cross(a, b, c), _cross(a, b, d), _cross(c, d, a), _cross(c, d, b)
    crosses = ((ab_c > EPSILON and ab_d < -EPSILON) or (ab_c < -EPSILON and ab_d > EPSILON)) and (
        (cd_a > EPSILON and cd_b < -EPSILON) or (cd_a < -EPSILON and cd_b > EPSILON))
    if proper:
        return crosses
    return crosses or any((on_segment(c, a, b), on_segment(d, a, b), on_segment(a, c, d), on_segment(b, c, d)))


def _edges(ring):
    return zip(ring, ring[1:])


def point_in_ring(point, ring, deadline=None):
    _budget(deadline)
    inside = False
    for a, b in _edges(ring):
        if on_segment(point, a, b):
            return "boundary"
        if (a[1] > point[1]) != (b[1] > point[1]):
            x = a[0] + (point[1] - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if point[0] < x:
                inside = not inside
    return "inside" if inside else "outside"


def polygons(geometry):
    return [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]


def point_location(point, geometry, deadline=None):
    """Innenringe sind ausserhalb; jeder gemeinsame Rand bleibt mehrdeutig."""
    result = "outside"
    for polygon in polygons(geometry):
        outer = point_in_ring(point, polygon[0], deadline)
        if outer == "boundary":
            return "boundary"
        if outer != "inside":
            continue
        hole_locations = [point_in_ring(point, hole, deadline) for hole in polygon[1:]]
        if "boundary" in hole_locations:
            return "boundary"
        if "inside" not in hole_locations:
            result = "inside"
    return result


def _ring_valid(ring, deadline=None):
    _budget(deadline)
    if len(ring) < 4:
        raise GeometryError("Ein Polygonring besitzt weniger als drei unterschiedliche Eckpunkte und einen Schlusspunkt.")
    if ring[0][:2] != ring[-1][:2]:
        raise GeometryError("Ein Polygonring ist offen: Anfangs- und Schlusspunkt stimmen nicht überein.")
    if len({tuple(point[:2]) for point in ring[:-1]}) != len(ring) - 1:
        raise GeometryError("Ein Polygonring enthält wiederkehrende Stützpunkte oder berührt sich selbst.")
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in _edges(ring))
    if abs(area) <= EPSILON:
        raise GeometryError("Ein Polygonring besitzt keine verlässliche Fläche.")
    edges = list(_edges(ring))
    for i, (a, b) in enumerate(edges):
        _budget(deadline)
        for j in range(i + 1, len(edges)):
            if j == i + 1 or (i == 0 and j == len(edges) - 1):
                continue
            if segments_intersect(a, b, *edges[j]):
                raise GeometryError("Ein Polygonring überschneidet sich selbst.")


def _rings_touch(first, second, proper=False, deadline=None):
    for a, b in _edges(first):
        _budget(deadline)
        if any(segments_intersect(a, b, c, d, proper) for c, d in _edges(second)):
            return True
    return False


def _shared_edge(first, second, deadline=None):
    for a, b in _edges(first):
        _budget(deadline)
        for c, d in _edges(second):
            if abs(_cross(a, b, c)) <= EPSILON and abs(_cross(a, b, d)) <= EPSILON:
                axis = 0 if abs(b[0] - a[0]) > abs(b[1] - a[1]) else 1
                if min(max(a[axis], b[axis]), max(c[axis], d[axis])) - max(min(a[axis], b[axis]), min(c[axis], d[axis])) > EPSILON:
                    return True
    return False


def validate_geometry(geometry, parcel=False, deadline=None):
    _budget(deadline)
    if not isinstance(geometry, dict):
        raise GeometryError("Die Antwort enthält keine Geometrie.")
    kind = geometry.get("type")
    allowed = {"Polygon", "MultiPolygon"} if parcel else {"Point", "MultiPoint", "Polygon", "MultiPolygon"}
    if kind not in allowed:
        raise GeometryError("Die Geometrieart ist für diese Quelle nicht geeignet.")
    count = 0

    def check_coordinates(value, depth):
        nonlocal count
        if not isinstance(value, list) or not value:
            raise GeometryError("Die Geometrie enthält leere oder ungültige Koordinaten.")
        if depth == 0:
            if len(value) not in (2, 3) or any(isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) for number in value):
                raise GeometryError("Eine Position enthält ungültige Zahlen.")
            if not -180 <= value[0] <= 180 or not -90 <= value[1] <= 90:
                raise GeometryError("Die angeforderten WGS84-Koordinaten liegen ausserhalb des gültigen Bereichs.")
            count += 1
            if count > MAX_VERTICES:
                raise GeometryError("Das Sicherheitslimit für die Geometrieprüfung ist erreicht.", "incomplete")
        else:
            for part in value:
                check_coordinates(part, depth - 1)

    check_coordinates(geometry.get("coordinates"), {"Point": 0, "MultiPoint": 1, "Polygon": 2, "MultiPolygon": 3}[kind])
    if kind in ("Polygon", "MultiPolygon"):
        components = polygons(geometry)
        for polygon in components:
            for ring in polygon:
                _ring_valid(ring, deadline)
            for i, hole in enumerate(polygon[1:]):
                if point_in_ring(hole[0], polygon[0], deadline) != "inside" or _rings_touch(hole, polygon[0], deadline=deadline):
                    raise GeometryError("Ein Innenring liegt nicht vollständig innerhalb des Aussenrings.")
                for other in polygon[1:i + 1]:
                    if _rings_touch(hole, other, deadline=deadline) or point_in_ring(hole[0], other, deadline) != "outside" or point_in_ring(other[0], hole, deadline) != "outside":
                        raise GeometryError("Die Innenringe überlagern oder berühren sich.")
        for i, component in enumerate(components):
            first = {"type": "Polygon", "coordinates": component}
            for other in components[:i]:
                second = {"type": "Polygon", "coordinates": other}
                if _shared_edge(component[0], other[0], deadline) or _rings_touch(component[0], other[0], proper=True, deadline=deadline) or any(point_location(p, second, deadline) == "inside" for p in component[0]) or any(point_location(p, first, deadline) == "inside" for p in other[0]):
                    raise GeometryError("Die Teilflächen eines MultiPolygons überlagern sich.")
    return geometry


def normalize_geometry(geometry, source_crs="CRS84", axis_order="xy", transformer_factory=None, parcel=False, deadline=None):
    """CRS niemals aus Zahlen erraten; GeoJSON bleibt Longitude, Latitude."""
    if not isinstance(geometry, dict) or geometry.get("type") not in ("Point", "MultiPoint", "Polygon", "MultiPolygon"):
        raise GeometryError("Keine unterstützte Geometrie geliefert.")
    depth = {"Point": 0, "MultiPoint": 1, "Polygon": 2, "MultiPolygon": 3}[geometry["type"]]
    count = 0
    def validate_raw(value, level):
        nonlocal count
        _budget(deadline)
        if not isinstance(value, list) or not value:
            raise GeometryError("Ungültige Koordinatenstruktur.")
        if level:
            for part in value:
                validate_raw(part, level - 1)
        else:
            if len(value) not in (2, 3) or any(isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) for number in value):
                raise GeometryError("Ungültige Position.")
            count += 1
            if count > MAX_VERTICES:
                raise GeometryError("Das Sicherheitslimit für die Geometrieprüfung ist erreicht.", "incomplete")
    validate_raw(geometry.get("coordinates"), depth)
    if axis_order not in ("xy", "yx"):
        raise GeometryError("Die Achsenreihenfolge der Quelle ist nicht belegt.")
    crs = str(source_crs).upper()
    crs = {"HTTP://WWW.OPENGIS.NET/DEF/CRS/EPSG/0/2056": "EPSG:2056", "URN:OGC:DEF:CRS:EPSG::2056": "EPSG:2056",
           "HTTP://WWW.OPENGIS.NET/DEF/CRS/EPSG/0/4326": "EPSG:4326", "URN:OGC:DEF:CRS:EPSG::4326": "EPSG:4326"}.get(crs, crs)
    if crs in ("CRS84", "OGC:CRS84", "URN:OGC:DEF:CRS:OGC:1.3:CRS84", "EPSG:4326", "HTTP://WWW.OPENGIS.NET/DEF/CRS/OGC/1.3/CRS84"):
        transform = None
    elif crs == "EPSG:2056":
        if transformer_factory is None:
            try:
                from pyproj import Transformer
            except ImportError as error:
                raise GeometryError("EPSG:2056 erfordert pyproj. Es wird nichts installiert; Gebäudepositionen können derzeit nicht transformiert werden.", "transform_missing") from error
            transformer_factory = Transformer.from_crs
        transform = transformer_factory("EPSG:2056", "EPSG:4326", always_xy=True).transform
    else:
        raise GeometryError("Das Koordinatensystem der Quelle ist nicht unterstützt oder nicht belegt.")
    normalized = copy.deepcopy(geometry)

    def convert(value, level):
        _budget(deadline)
        if not isinstance(value, list) or not value:
            raise GeometryError("Ungültige Koordinatenstruktur.")
        if level:
            return [convert(part, level - 1) for part in value]
        if len(value) not in (2, 3) or any(isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) for number in value):
            raise GeometryError("Ungültige Position.")
        x, y = value[:2] if axis_order == "xy" else value[1::-1]
        if transform:
            x, y = transform(x, y)
        return [x, y, *value[2:]]

    normalized["coordinates"] = convert(geometry.get("coordinates"), depth)
    if normalized["type"] in ("Polygon", "MultiPolygon"):
        # Nullkanten entfernen, ohne Eckpunkte zu verschieben oder offene Ringe
        # zu schliessen. Nicht benachbarte Wiederholungen bleiben prüfpflichtig.
        # Das Ressourcenlimit wurde bereits auf die vollständige Eingabe angewandt.
        for polygon in polygons(normalized):
            for index, ring in enumerate(polygon):
                compact = []
                for position in ring:
                    if not compact or position[:2] != compact[-1][:2]:
                        compact.append(position)
                polygon[index] = compact
    return validate_geometry(normalized, parcel=parcel, deadline=deadline)


def bounds(geometry):
    points = []
    def walk(value):
        if isinstance(value[0], (int, float)):
            points.append(value)
        else:
            for part in value:
                walk(part)
    walk(geometry["coordinates"])
    return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]


def geometry_relation(building, parcel, deadline=None):
    """Eine BBOX oder ein Eingang allein wird nie zur Gebäudezuordnung erklärt."""
    kind = building["type"]
    if kind == "Point":
        return point_location(building["coordinates"], parcel, deadline)
    if kind == "MultiPoint":
        locations = {point_location(point, parcel, deadline) for point in building["coordinates"]}
        return locations.pop() if len(locations) == 1 else "crosses"
    locations = {point_location(point, parcel, deadline) for polygon in polygons(building) for point in polygon[0][:-1]}
    for polygon in polygons(building):
        for boundary in polygons(parcel):
            if any(_rings_touch(ring, limit, proper=True, deadline=deadline) for ring in polygon for limit in boundary):
                return "crosses"
    if "inside" in locations and "outside" in locations:
        return "crosses"
    midpoints = [[(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] for polygon in polygons(building) for a, b in _edges(polygon[0])]
    if "outside" not in locations and all(point_location(point, parcel, deadline) != "outside" for point in midpoints):
        for polygon in polygons(parcel):
            if any(point_location(hole[0], building, deadline) == "inside" for hole in polygon[1:]):
                return "crosses"
        return "inside"
    if "boundary" in locations:
        return "boundary"
    if any(point_location(polygon[0][0], building, deadline) == "inside" for polygon in polygons(parcel)):
        return "crosses"
    return "outside"

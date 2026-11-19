"""GWR-Koordinaten und gezielte, schreibgeschützte Adressabfragen zur vorhandenen EGID."""

import math
from pathlib import Path
import sqlite3

from .geometrie import GeometryError, normalize_geometry
from ..common import ReviewError, egid_text, txt


APPROXIMATION = "Swisstopo-Näherung (nur Kartendarstellung, keine Grenzprüfung)"
FORMULA_SOURCE = "https://www.swisstopo.admin.ch/dam/en/sd-web/KLRCX9XIdXDu/ch1903wgs84-EN.pdf"


def read_gwr_addresses(path, egids):
    """Nur bestehende entrance.EGID-Beziehungen lesen; keine Adresszuordnung erzeugen."""
    requested = sorted({egid_text(value) for value in egids}, key=int)
    if not requested:
        return {}
    result = {egid: [] for egid in requested}
    connection = None
    try:
        connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        for start in range(0, len(requested), 500):
            batch = requested[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                "SELECT DISTINCT EGID, STRNAME, DEINR, DPLZ4 FROM entrance "
                f"WHERE EGID IN ({placeholders}) ORDER BY EGID, STRNAME, DEINR, DPLZ4", batch)
            for value, street, number, postal in rows:
                egid = egid_text(value)
                if egid not in batch:
                    raise ReviewError("Die GWR-Adressantwort enthält eine nicht angefragte EGID.")
                address = [txt(street), txt(number), txt(postal)]
                if any(address) and address not in result[egid]:
                    result[egid].append(address)
        return result
    except (sqlite3.Error, OSError) as error:
        raise ReviewError("Die konfigurierte GWR-Datenbank ist nicht lesbar oder enthält nicht entrance(EGID, STRNAME, DEINR, DPLZ4).") from error
    finally:
        if connection is not None:
            connection.close()


def read_gwr_volumes(path, egids):
    """GVOL ausschliesslich über angefragte EGIDs; keine Schätzung oder Adresssuche."""
    requested = sorted({egid_text(value) for value in egids}, key=int)
    if not requested:
        return {}
    values = {egid: set() for egid in requested}
    connection = None
    try:
        connection = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        for start in range(0, len(requested), 500):
            batch = requested[start:start + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                "SELECT DISTINCT EGID, GVOL FROM building WHERE GSTAT = 1004 "
                f"AND EGID IN ({placeholders}) ORDER BY EGID, GVOL", batch)
            for value, volume in rows:
                egid = egid_text(value)
                if egid not in batch:
                    raise ReviewError("Die GWR-Volumenantwort enthält eine nicht angefragte EGID.")
                if volume is None or isinstance(volume, bool):
                    continue
                try:
                    number = float(volume)
                except (TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(number) and number >= 0:
                    values[egid].add(int(number) if number.is_integer() else number)
        # Mehrere widersprüchliche Werte werden nicht willkürlich ausgewählt.
        return {egid: next(iter(volumes)) if len(volumes) == 1 else None
                for egid, volumes in values.items()}
    except (sqlite3.Error, OSError) as error:
        raise ReviewError("Die konfigurierte GWR-Datenbank ist nicht lesbar oder enthält nicht building(EGID, GVOL, GSTAT).") from error
    finally:
        if connection is not None:
            connection.close()


def gwr_point(easting, northing, transformer_factory=None):
    """GKODE/GKODN (LV95), Ergebnis explizit [Longitude, Latitude]."""
    try:
        if isinstance(easting, bool) or isinstance(northing, bool):
            raise ValueError
        east, north = float(easting), float(northing)
        if not math.isfinite(east) or not math.isfinite(north):
            raise ValueError
        # Explizites LV95-Eingabeformat, kein Raten oder Vertauschen von Achsen.
        if not (2_400_000 <= east <= 2_900_000 and 1_000_000 <= north <= 1_400_000):
            raise ValueError
    except (TypeError, ValueError, OverflowError) as error:
        raise GeometryError("GKODE/GKODN fehlen oder sind keine gültigen LV95-Koordinaten.") from error
    geometry = {"type": "Point", "coordinates": [east, north]}
    try:
        return normalize_geometry(geometry, "EPSG:2056", transformer_factory=transformer_factory), "pyproj"
    except GeometryError as error:
        if error.code != "transform_missing":
            raise
    # Swisstopo, Dezember 2016, Abschnitt 2. Nur Anzeige, keine Vermessung.
    y, x = (east - 2_600_000) / 1_000_000, (north - 1_200_000) / 1_000_000
    longitude = (2.6779094 + 4.728982*y + .791484*y*x + .1306*y*x*x - .0436*y**3) * 100/36
    latitude = (16.9023892 + 3.238272*x - .270978*y*y - .002528*x*x - .0447*y*y*x - .0140*x**3) * 100/36
    return {"type": "Point", "coordinates": [longitude, latitude]}, APPROXIMATION



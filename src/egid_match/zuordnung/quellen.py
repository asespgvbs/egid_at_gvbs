"""Öffentliche Quellenprofile. Keine Zugangsdaten, keine Datensätze.

Geprüft am 13.11.2026: ausschliesslich offizielle Dienst-/Schemabeschreibungen,
keine Items-/Records-Abfragen. Details und Grenzen stehen in docs/GEODATEN.md.
"""

PARCEL_COLLECTION = "ch.bs.av_parzellen_rechtliche_abgrenzungen_avpz.liegenschaft"
PARCEL_ITEMS = f"https://api.geo.bs.ch/ogc/v1/wfs3/collections/{PARCEL_COLLECTION}/items.json"
PARCEL_METADATA = f"https://api.geo.bs.ch/ogc/v1/wfs3/collections/{PARCEL_COLLECTION}.json?MAP=Public_latest_published"
GWR_METADATA = "https://data.bs.ch/api/explore/v2.1/catalog/datasets/100230"

PUBLIC_SOURCES = {
    "parcel_url": PARCEL_ITEMS,
    "parcel_mode": "qgis",
    "parcel_layer": PARCEL_COLLECTION,
    "parcel_map": "Public_latest_published",
    "parcel_egrid": "EGRID",
    "parcel_section": "Sektionsname",
    "parcel_number": "Parzellennummer",
    "parcel_crs": "CRS84",
    "parcel_axis": "xy",
    "parcel_extent": "7.547906530071878,47.51484853136913,7.700462812745155,47.60539714664085",
    "parcel_source": "GeoBS / Amtliche Vermessung Basel-Stadt – Liegenschaft",
    "parcel_scope": "Publizierte Liegenschaftsgeometrien dieser Collection; keine Vollständigkeitszusage für andere Grundstücksarten.",
    "building_url": "https://data.bs.ch/api/explore/v2.1/catalog/datasets/100230/records",
    "building_mode": "ods",
    "building_layer": "100230",
    "building_map": "",
    "building_egrid": "egrid",
    "building_egid": "egid",
    "building_gstat": "gstat",
    "building_easting": "gkode",
    "building_northing": "gkodn",
    "building_updated": "gexpdat",
    "building_street": "",
    "building_number": "",
    "building_postal": "",
    "building_crs": "EPSG:2056",
    "building_axis": "xy",
    "building_point_role": "building",
    "building_source": "Statistisches Amt Basel-Stadt – Gebäude (GWR), Datensatz 100230, CC BY",
    "building_scope": "GWR-Publikation und deren EGRID-Feld; kein Beleg für sämtliche grundbuchlichen Mehrfachbeziehungen oder vollständige Gebäudegrundrisse.",
}

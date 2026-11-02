import argparse
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# ============================================================
# KONFIGURATION
# ============================================================

DEFAULT_GWR_DB = Path(
    r"C:\dev\private\gvbs_dash\gwr_daten_bs\data.sqlite"
)

REQUIRED = (
    "Kontrollnummer",
    "Gebäude (Nr.)",
    "Strasse",
    "Nr.",
    "PLZ",
)

CATEGORIES = [
    (
        "perfect_match",
        "Genau eine GVBSID an der GVBS-Adresse und genau ein "
        "EGID-Kandidat. Die EGID besitzt genau eine GWR-Adresse, "
        "genau eine EGRID und ist die einzige bestehende EGID "
        "auf dieser EGRID. Keine andere GVBSID beansprucht "
        "dieselbe EGID.",
        "EGID automatisch zuordnen.",
    ),
    (
        "super_match",
        "Genau eine GVBSID an der GVBS-Adresse und genau ein "
        "EGID-Kandidat. Keine andere GVBSID beansprucht dieselbe "
        "EGID. Die Bedingungen für perfect_match sind jedoch "
        "nicht vollständig erfüllt, beispielsweise wegen "
        "mehrerer GWR-Adressen, weiterer EGIDs auf derselben "
        "EGRID oder mehrerer EGRIDs. Es liegt kein erkannter "
        "Konflikt mit Hausnummernzusätzen vor.",
        "EGID automatisch zuordnen. Alle Abweichungen von "
        "perfect_match einzeln begründen.",
    ),
    (
        "review_address_suffix",
        "Eine GVBSID besitzt einen eindeutigen direkten "
        "EGID-Adresstreffer. Auf derselben EGRID befindet sich "
        "mindestens eine weitere EGID mit derselben Strasse "
        "und PLZ sowie einer Hausnummer, die durch einen "
        "Zusatz aus der GVBS-Hausnummer entsteht. Für diese "
        "zusätzliche Adresse ist keine eigene GVBSID im "
        "eingelesenen Datensatz vorhanden.",
        "Keine automatische Zuordnung. Prüfen, ob die GVBSID "
        "mehrere EGIDs umfasst.",
    ),
    (
        "multiple_gvbsid_same_address_one_egid",
        "Mehrere unterschiedliche GVBSIDs besitzen dieselbe "
        "GVBS-Adresse und haben dieselbe EGID als einzigen "
        "Adresskandidaten. Es liegt keine zusätzliche "
        "konkurrierende GVBS-Adresse vor.",
        "Keine automatische Zuordnung. Mehrfacherfassung prüfen.",
    ),
    (
        "multiple_gvbsid_one_egid",
        "Mehrere unterschiedliche GVBSIDs mit unterschiedlichen "
        "GVBS-Adressen haben dieselbe EGID als einzigen "
        "Adresskandidaten. Mischfälle gehören ebenfalls hierher.",
        "Keine automatische Zuordnung. Beziehung prüfen.",
    ),
    (
        "multiple_egid",
        "Eine GVBSID besitzt mehrere direkte EGID-Kandidaten "
        "an ihrer GVBS-Adresse.",
        "Keine automatische Zuordnung.",
    ),
    (
        "multiple_gvbsid_multiple_egid",
        "Mehrere GVBSIDs an derselben GVBS-Adresse und "
        "mehrere EGID-Kandidaten an dieser Adresse.",
        "Keine automatische Zuordnung.",
    ),
    (
        "review_parcel",
        "Historische Kategorie für zusätzliche EGIDs "
        "auf derselben EGRID.",
        "Wird aktuell nicht vergeben. Die Fälle werden "
        "durch super_match oder andere Prüfkategorien erfasst.",
    ),
    (
        "review_missing_egrid",
        "Genau ein EGID-Kandidat vorhanden, aber keine "
        "verwertbare EGRID im GWR hinterlegt.",
        "Keine automatische Zuordnung. Daten prüfen.",
    ),
    (
        "no_match",
        "Keine passende bestehende EGID an der GVBS-Adresse.",
        "Keine automatische Zuordnung.",
    ),
    (
        "invalid_input",
        "Mindestens ein Pflichtfeld fehlt.",
        "Eingabedaten korrigieren.",
    ),
]

AUTO_CATEGORIES = {
    "perfect_match",
    "super_match",
}


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def txt(value):
    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value).strip()


def anzahl_text(anzahl, singular, plural):
    wort = singular if anzahl == 1 else plural
    return f"{anzahl} {wort}"


def address(street, number, postal):
    return (
        re.sub(
            r"\s+",
            " ",
            txt(street).casefold().replace("ß", "ss"),
        ).strip(),
        re.sub(
            r"\s+",
            "",
            txt(number).casefold(),
        ),
        txt(postal),
    )


def address_text(key):
    if not key:
        return "unbekannte Adresse"

    street, number, postal = key

    return " ".join(
        part
        for part in (
            f"{street} {number}".strip(),
            postal,
        )
        if part
    )


def list_text(values):
    values = [str(value) for value in values]
    return ", ".join(values) if values else "keine"


def gvbsid_text(gvbsid):
    return f"{gvbsid[0]}-{gvbsid[1]}"


def sorted_egids(values):
    return sorted(values, key=lambda value: str(value))


# ============================================================
# HAUSNUMMERNZUSÄTZE
# ============================================================

def is_address_suffix(gvbs_number, gwr_number):
    """
    Prüft ausschliesslich von der GVBS-Hausnummer aus,
    ob die GWR-Hausnummer eine Erweiterung darstellt.

    Beispiele:

    GVBS 30 -> GWR 30.1    Ja
    GVBS 30 -> GWR 30.2    Ja
    GVBS 30 -> GWR 30a     Ja
    GVBS 30 -> GWR 30A     Ja

    GVBS 30 -> GWR 30      Nein
    GVBS 30 -> GWR 31      Nein
    GVBS 30 -> GWR 300     Nein
    GVBS 30 -> GWR 30.    Nein
    GVBS 30 -> GWR 30/31   Nein

    Der Vergleich ist gerichtet: Die GVBS-Hausnummer
    muss die Basis der GWR-Hausnummer sein.
    """

    base = re.sub(
        r"\s+",
        "",
        txt(gvbs_number).casefold(),
    )

    candidate = re.sub(
        r"\s+",
        "",
        txt(gwr_number).casefold(),
    )

    if not base or not candidate:
        return False

    if candidate == base:
        return False

    if not candidate.startswith(base):
        return False

    suffix = candidate[len(base):]

    # Nummerierte Zusätze wie 30.1 oder 30.12
    if re.fullmatch(r"\.\d+", suffix):
        return True

    # Buchstabenzusätze wie 30a oder 30ab
    if re.fullmatch(r"[a-z]+", suffix):
        return True

    return False


def find_address_suffix_conflicts(
    gvbs_address,
    direct_egid,
    egid_addresses,
    egid_grids,
    grid_egids,
    gvbs_by_address,
):
    """
    Sucht weitere EGIDs mit abgeleiteten Hausnummern.

    Ausgangspunkt:
        GVBS-Adresse -> direkter EGID-Adresstreffer.

    Anschliessend:
        Direkte EGID -> EGRID -> weitere EGIDs.

    Eine weitere EGID wird als möglicher Konflikt
    erfasst, wenn:

    1. Sie auf einer EGRID der direkten EGID liegt.
    2. Ihre GWR-Adresse dieselbe Strasse und PLZ hat.
    3. Ihre Hausnummer eine Erweiterung der
       GVBS-Hausnummer ist.
    4. Für ihre GWR-Adresse keine eigene GVBSID
       im eingelesenen Datensatz existiert.

    Rückgabe:
        Liste von Dictionaries mit:
            EGID
            EGRID
            GWR-Adresse
    """

    if direct_egid is None:
        return []

    gvbs_street, gvbs_number, gvbs_postal = gvbs_address

    conflicts = []
    seen = set()

    grids = sorted(
        egid_grids.get(direct_egid, set())
    )

    for grid in grids:
        other_egids = sorted_egids(
            grid_egids.get(grid, set()) - {direct_egid}
        )

        for other_egid in other_egids:
            gwr_addresses = sorted(
                egid_addresses.get(other_egid, set())
            )

            for gwr_address in gwr_addresses:
                gwr_street, gwr_number, gwr_postal = gwr_address

                # Gleiche Strasse
                if gwr_street != gvbs_street:
                    continue

                # Gleiche PLZ
                if gwr_postal != gvbs_postal:
                    continue

                # Gerichteter Hausnummernvergleich
                if not is_address_suffix(
                    gvbs_number,
                    gwr_number,
                ):
                    continue

                # Keine eigene GVBSID an dieser Adresse
                if gvbs_by_address.get(gwr_address):
                    continue

                identifier = (
                    other_egid,
                    grid,
                    gwr_address,
                )

                if identifier in seen:
                    continue

                seen.add(identifier)

                conflicts.append({
                    "EGID": other_egid,
                    "EGRID": grid,
                    "GWR-Adresse": gwr_address,
                })

    return conflicts


def suffix_conflicts_text(conflicts):
    """
    Erstellt eine vollständige textliche Dokumentation
    aller erkannten Hausnummernzusatz-Konflikte.
    """

    if not conflicts:
        return ""

    descriptions = []

    for conflict in conflicts:
        descriptions.append(
            f"EGID {conflict['EGID']} "
            f"mit GWR-Adresse "
            f"{address_text(conflict['GWR-Adresse'])} "
            f"auf EGRID {conflict['EGRID']}"
        )

    return "; ".join(descriptions)


# ============================================================
# GWR EINLESEN
# ============================================================

def read_gwr(db):
    if not db.is_file():
        raise FileNotFoundError(
            f"GWR-Datenbank nicht gefunden: {db}"
        )

    con = sqlite3.connect(
        db.resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        buildings = con.execute(
            """
            SELECT EGID, EGRID
            FROM building
            WHERE GSTAT = 1004
              AND EGID IS NOT NULL
            """
        ).fetchall()

        entrances = con.execute(
            """
            SELECT
                e.EGID,
                e.STRNAME,
                e.DEINR,
                e.DPLZ4
            FROM entrance e
            JOIN building b
                ON e.EGID = b.EGID
            WHERE b.GSTAT = 1004
              AND b.EGID IS NOT NULL
            """
        ).fetchall()

    finally:
        con.close()

    addr_egids = defaultdict(set)
    egid_addresses = defaultdict(set)
    egid_grids = defaultdict(set)
    grid_egids = defaultdict(set)

    for egid, grid in buildings:
        if txt(grid):
            grid = txt(grid)

            egid_grids[egid].add(grid)
            grid_egids[grid].add(egid)

    for egid, street, number, postal in entrances:
        key = address(
            street,
            number,
            postal,
        )

        if all(key):
            addr_egids[key].add(egid)
            egid_addresses[egid].add(key)

    return (
        addr_egids,
        egid_addresses,
        egid_grids,
        grid_egids,
    )


# ============================================================
# GVBS-EXCEL EINLESEN
# ============================================================

def read_excel(path):
    wb = load_workbook(
        path,
        read_only=True,
        data_only=True,
    )

    try:
        rows = wb.active.iter_rows(values_only=True)
        first = next(rows, None)

        if first is None:
            raise ValueError(
                "Excel-Datei ist leer."
            )

        headers = [
            txt(value)
            for value in first
        ]

        if len(headers) != len(set(headers)):
            raise ValueError(
                "Doppelte Spaltennamen in der Eingabe."
            )

        missing = [
            column
            for column in REQUIRED
            if column not in headers
        ]

        if missing:
            raise ValueError(
                f"Fehlende Spalten: {missing}"
            )

        records = [
            dict(zip(headers, row))
            for row in rows
            if any(value is not None for value in row)
        ]

        return headers, records

    finally:
        wb.close()


# ============================================================
# SUPER-MATCH: INDIVIDUELLE BEGRÜNDUNG
# ============================================================

def super_match_reasons(
    egid,
    egid_addresses,
    egid_grids,
    grid_egids,
):
    """
    Ermittelt sämtliche Gründe, weshalb ein eindeutiger
    EGID-Kandidat kein perfect_match ist.
    """

    reasons = []

    gwr_addresses = sorted(
        egid_addresses.get(egid, set())
    )

    grids = sorted(
        egid_grids.get(egid, set())
    )

    # --------------------------------------------------------
    # GRUND 1: MEHRERE GWR-ADRESSEN
    # --------------------------------------------------------

    if len(gwr_addresses) > 1:
        reasons.append(
            "Die EGID besitzt "
            f"{anzahl_text(len(gwr_addresses), 'GWR-Adresse', 'GWR-Adressen')}: "
            f"{list_text(address_text(a) for a in gwr_addresses)}."
        )

    # --------------------------------------------------------
    # GRUND 2: MEHRERE EGRIDs
    # --------------------------------------------------------

    if len(grids) > 1:
        reasons.append(
            "Für diese EGID sind "
            f"{anzahl_text(len(grids), 'EGRID', 'EGRIDs')} "
            f"hinterlegt: {list_text(grids)}."
        )

    # --------------------------------------------------------
    # GRUND 3: WEITERE EGIDs AUF DERSELBEN EGRID
    # --------------------------------------------------------

    for grid in grids:
        other_egids = sorted_egids(
            grid_egids.get(grid, set()) - {egid}
        )

        if other_egids:
            reasons.append(
                f"Auf EGRID {grid} befinden sich zusätzlich "
                f"{anzahl_text(len(other_egids), 'weitere EGID', 'weitere EGIDs')}: "
                f"{list_text(other_egids)}."
            )

            for other_egid in other_egids:
                other_addresses = sorted(
                    egid_addresses.get(other_egid, set())
                )

                reasons.append(
                    f"Die zusätzliche EGID {other_egid} "
                    "besitzt folgende GWR-Adressen: "
                    f"{list_text(address_text(a) for a in other_addresses)}."
                )

    return reasons


# ============================================================
# AUSFÜHRLICHE MATCHING-ZUSAMMENFASSUNG
# ============================================================

def create_summary(
    gvbsid,
    gvbs_address,
    category,
    candidates,
    grids,
    parcel_egids,
    egid_addresses,
    egid_grids,
    grid_egids,
    gvbs_by_egid,
    gvbs_addresses_by_id,
    suffix_conflicts,
):
    parts = [
        f"GVBSID {gvbsid}, "
        f"GVBS-Adresse {address_text(gvbs_address)}."
    ]

    if category == "invalid_input":
        parts.append(
            "Die Eingabedaten sind unvollständig. "
            "Eine zuverlässige Zuordnung ist nicht möglich."
        )

        return " ".join(parts)

    if not candidates:
        parts.append(
            "Für diese GVBS-Adresse wurde im GWR "
            "kein passender Adresstreffer eines bestehenden "
            "Gebäudes (GSTAT 1004) gefunden."
        )

        parts.append(
            "Es wird keine EGID zugeordnet."
        )

        return " ".join(parts)

    parts.append(
        "EGID-Kandidaten aufgrund des direkten "
        "Adressvergleichs: "
        f"{list_text(candidates)}."
    )

    # --------------------------------------------------------
    # ALLE DIREKTEN EGID-KANDIDATEN DOKUMENTIEREN
    # --------------------------------------------------------

    for egid in candidates:
        gwr_addresses = sorted(
            egid_addresses.get(egid, set())
        )

        egid_grid_values = sorted(
            egid_grids.get(egid, set())
        )

        parts.append(
            f"EGID {egid} besitzt "
            f"{anzahl_text(len(gwr_addresses), 'GWR-Adresse', 'GWR-Adressen')}: "
            f"{list_text(address_text(a) for a in gwr_addresses)}."
        )

        parts.append(
            f"Für EGID {egid} sind "
            f"{anzahl_text(len(egid_grid_values), 'EGRID', 'EGRIDs')} "
            f"hinterlegt: {list_text(egid_grid_values)}."
        )

        # ----------------------------------------------------
        # ALLE EGIDs AUF DEN EGRIDs DOKUMENTIEREN
        # ----------------------------------------------------

        for grid in egid_grid_values:
            other_egids = sorted_egids(
                grid_egids.get(grid, set()) - {egid}
            )

            if other_egids:
                parts.append(
                    f"Auf EGRID {grid} befinden sich zusätzlich "
                    f"{anzahl_text(len(other_egids), 'weitere EGID', 'weitere EGIDs')}: "
                    f"{list_text(other_egids)}."
                )

                for other_egid in other_egids:
                    other_addresses = sorted(
                        egid_addresses.get(other_egid, set())
                    )

                    parts.append(
                        f"Zusätzliche EGID {other_egid}: "
                        "GWR-Adressen "
                        f"{list_text(address_text(a) for a in other_addresses)}."
                    )

            else:
                parts.append(
                    f"Auf EGRID {grid} ist EGID {egid} "
                    "die einzige bestehende EGID "
                    "im verwendeten GWR-Datensatz."
                )

        # ----------------------------------------------------
        # KONKURRIERENDE GVBSIDs DOKUMENTIEREN
        # ----------------------------------------------------

        related_gvbsids = sorted(
            gvbs_by_egid.get(egid, set()),
            key=gvbsid_text,
        )

        if related_gvbsids:
            descriptions = []

            for other_gvbsid in related_gvbsids:
                addresses = sorted(
                    gvbs_addresses_by_id.get(
                        other_gvbsid,
                        set(),
                    )
                )

                descriptions.append(
                    f"{gvbsid_text(other_gvbsid)} "
                    f"({list_text(address_text(a) for a in addresses)})"
                )

            parts.append(
                "Folgende GVBSIDs besitzen diese EGID "
                "als einzigen direkten Adresskandidaten: "
                + "; ".join(descriptions)
                + "."
            )

    # --------------------------------------------------------
    # KATEGORIENSPEZIFISCHE BEWERTUNG
    # --------------------------------------------------------

    if category == "perfect_match":
        parts.append(
            "Bewertung: perfect_match. "
            "Es besteht genau ein EGID-Kandidat. "
            "Keine andere GVBSID beansprucht diese EGID. "
            "Die EGID besitzt genau eine GWR-Adresse "
            "und ist die einzige bestehende EGID "
            "auf ihrer EGRID. "
            "Die EGID wird automatisch zugeordnet."
        )

    elif category == "super_match":
        egid = candidates[0]

        reasons = super_match_reasons(
            egid=egid,
            egid_addresses=egid_addresses,
            egid_grids=egid_grids,
            grid_egids=grid_egids,
        )

        parts.append(
            "Bewertung: super_match. "
            f"Die GVBSID {gvbsid} kann anhand "
            f"des Adressvergleichs eindeutig "
            f"der EGID {egid} zugeordnet werden. "
            "Es besteht genau ein direkter EGID-Kandidat, "
            "und keine andere GVBSID beansprucht diese EGID."
        )

        parts.append(
            "Kein perfect_match aus folgenden Gründen:"
        )

        for index, reason in enumerate(reasons, start=1):
            parts.append(
                f"Grund {index}: {reason}"
            )

        parts.append(
            "Diese Besonderheiten verhindern die "
            "automatische Zuordnung nach der "
            "festgelegten Matchinglogik nicht. "
            "Die EGID wird automatisch zugeordnet."
        )

    elif category == "review_address_suffix":
        direct_egid = candidates[0]

        parts.append(
            "Bewertung: review_address_suffix."
        )

        parts.append(
            f"Für die GVBSID {gvbsid} mit der Adresse "
            f"{address_text(gvbs_address)} "
            f"wurde die EGID {direct_egid} "
            "als eindeutiger direkter Adresstreffer gefunden."
        )

        parts.append(
            "Auf mindestens einer EGRID dieser EGID "
            "befinden sich jedoch weitere EGIDs mit "
            "abgeleiteten Hausnummern."
        )

        parts.append(
            "Folgende zusätzlichen EGIDs wurden erkannt: "
            + suffix_conflicts_text(suffix_conflicts)
            + "."
        )

        parts.append(
            "Für die genannten zusätzlichen GWR-Adressen "
            "ist im eingelesenen GVBS-Datensatz keine "
            "eigene GVBSID vorhanden."
        )

        parts.append(
            "Es muss geprüft werden, ob die GVBSID "
            "ausschliesslich dem direkt gefundenen Gebäude "
            "entspricht oder mehrere EGIDs umfasst. "
            "Es erfolgt keine automatische EGID-Zuordnung."
        )

    elif category == "multiple_gvbsid_same_address_one_egid":
        parts.append(
            "Bewertung: multiple_gvbsid_same_address_one_egid. "
            "Mehrere unterschiedliche GVBSIDs besitzen "
            "dieselbe GVBS-Adresse und führen zur "
            "gleichen EGID. "
            "Die Beziehung muss geprüft werden. "
            "Die EGID bleibt leer."
        )

    elif category == "multiple_gvbsid_one_egid":
        parts.append(
            "Bewertung: multiple_gvbsid_one_egid. "
            "Mehrere unterschiedliche GVBSIDs mit "
            "unterschiedlichen GVBS-Adressen führen "
            "zur gleichen EGID. "
            "Diese Beziehung muss manuell geprüft werden. "
            "Die EGID bleibt leer."
        )

    elif category == "multiple_egid":
        parts.append(
            "Bewertung: multiple_egid. "
            "Die GVBS-Adresse liefert mehrere "
            "EGID-Kandidaten. "
            "Eine eindeutige Zuordnung ist nicht möglich."
        )

    elif category == "multiple_gvbsid_multiple_egid":
        parts.append(
            "Bewertung: multiple_gvbsid_multiple_egid. "
            "Mehrere GVBSIDs besitzen dieselbe GVBS-Adresse, "
            "und der GWR-Adressvergleich liefert "
            "mehrere EGIDs. "
            "Eine automatische Zuordnung ist nicht möglich."
        )

    elif category == "review_missing_egrid":
        parts.append(
            "Bewertung: review_missing_egrid. "
            "Es wurde genau ein EGID-Kandidat gefunden, "
            "aber keine EGRID ist hinterlegt. "
            "Die Zuordnung wird zur Prüfung zurückgestellt."
        )

    else:
        parts.append(
            f"Bewertung: {category}. "
            "Die Zuordnung wird zur Prüfung zurückgestellt."
        )

    return " ".join(parts)


# ============================================================
# MATCHING
# ============================================================

def match(
    records,
    addr_egids,
    egid_addresses,
    egid_grids,
    grid_egids,
):
    # --------------------------------------------------------
    # GVBS-ADRESSEN UND GVBSIDs AUFBEREITEN
    # --------------------------------------------------------

    keys = [
        address(
            record["Strasse"],
            record["Nr."],
            record["PLZ"],
        )
        for record in records
    ]

    gvbs_keys = [
        (
            txt(record["Kontrollnummer"]),
            txt(record["Gebäude (Nr.)"]),
        )
        for record in records
    ]

    valid = [
        all(key) and all(gvbs_key)
        for key, gvbs_key in zip(
            keys,
            gvbs_keys,
        )
    ]

    # --------------------------------------------------------
    # GESAMTEN GVBS-DATENSATZ ANALYSIEREN
    # --------------------------------------------------------

    gvbs_by_address = defaultdict(set)
    gvbs_by_egid = defaultdict(set)
    gvbs_addresses_by_id = defaultdict(set)

    for key, gvbs_key, ok in zip(
        keys,
        gvbs_keys,
        valid,
    ):
        if not ok:
            continue

        gvbs_by_address[key].add(gvbs_key)
        gvbs_addresses_by_id[gvbs_key].add(key)

        candidates = addr_egids.get(
            key,
            set(),
        )

        if len(candidates) == 1:
            egid = next(iter(candidates))
            gvbs_by_egid[egid].add(gvbs_key)

    # --------------------------------------------------------
    # EINZELNE DATENSÄTZE BEWERTEN
    # --------------------------------------------------------

    results = []

    for record, key, gvbs_key, ok in zip(
        records,
        keys,
        gvbs_keys,
        valid,
    ):
        candidates = (
            sorted_egids(
                addr_egids.get(key, set())
            )
            if ok
            else []
        )

        grids = set()

        for egid in candidates:
            grids.update(
                egid_grids.get(egid, set())
            )

        parcel_egids = set()

        for grid in grids:
            parcel_egids.update(
                grid_egids.get(grid, set())
            )

        n_gvbs_at_address = (
            len(gvbs_by_address[key])
            if ok
            else 0
        )

        direct_egid = (
            candidates[0]
            if len(candidates) == 1
            else None
        )

        n_gwr_addresses = (
            len(
                egid_addresses.get(
                    direct_egid,
                    set(),
                )
            )
            if direct_egid is not None
            else None
        )

        gvbsids_for_egid = (
            gvbs_by_egid.get(
                direct_egid,
                set(),
            )
            if direct_egid is not None
            else set()
        )

        n_gvbs_for_egid = (
            len(gvbsids_for_egid)
            if direct_egid is not None
            else None
        )

        gvbs_addresses_for_egid = set()

        for other_gvbsid in gvbsids_for_egid:
            gvbs_addresses_for_egid.update(
                gvbs_addresses_by_id.get(
                    other_gvbsid,
                    set(),
                )
            )

        n_gvbs_addresses_for_egid = (
            len(gvbs_addresses_for_egid)
            if direct_egid is not None
            else None
        )

        # ----------------------------------------------------
        # NEU: HAUSNUMMERNZUSÄTZE PRÜFEN
        # ----------------------------------------------------

        suffix_conflicts = []

        if (
            ok
            and direct_egid is not None
            and grids
        ):
            suffix_conflicts = find_address_suffix_conflicts(
                gvbs_address=key,
                direct_egid=direct_egid,
                egid_addresses=egid_addresses,
                egid_grids=egid_grids,
                grid_egids=grid_egids,
                gvbs_by_address=gvbs_by_address,
            )

        # ----------------------------------------------------
        # KATEGORIE BESTIMMEN
        # ----------------------------------------------------

        if not ok:
            category = "invalid_input"

        elif not candidates:
            category = "no_match"

        elif len(candidates) > 1:
            if n_gvbs_at_address > 1:
                category = "multiple_gvbsid_multiple_egid"
            else:
                category = "multiple_egid"

        elif (
            n_gvbs_for_egid > 1
            and n_gvbs_addresses_for_egid > 1
        ):
            category = "multiple_gvbsid_one_egid"

        elif n_gvbs_for_egid > 1:
            category = (
                "multiple_gvbsid_same_address_one_egid"
            )

        elif not grids:
            category = "review_missing_egrid"

        # ----------------------------------------------------
        # NEUE KATEGORIE VOR PERFECT UND SUPER MATCH
        # ----------------------------------------------------

        elif suffix_conflicts:
            category = "review_address_suffix"

        elif (
            n_gwr_addresses == 1
            and len(grids) == 1
            and len(parcel_egids) == 1
        ):
            category = "perfect_match"

        else:
            category = "super_match"

        # ----------------------------------------------------
        # AUTOMATISCHE EGID-ZUORDNUNG
        # ----------------------------------------------------

        assigned_egid = (
            direct_egid
            if category in AUTO_CATEGORIES
            else None
        )

        # ----------------------------------------------------
        # KOMPAKTER KOMMENTAR
        # ----------------------------------------------------

        comment_parts = [
            anzahl_text(
                n_gvbs_at_address,
                "GVBSID",
                "GVBSIDs",
            )
            + " an GVBS-Adresse",

            anzahl_text(
                len(candidates),
                "EGID-Kandidat",
                "EGID-Kandidaten",
            ),

            anzahl_text(
                len(grids),
                "EGRID",
                "EGRIDs",
            )
            + " der Adresskandidaten",

            anzahl_text(
                len(parcel_egids),
                "bestehende EGID",
                "bestehende EGIDs",
            )
            + " auf diesen EGRIDs",
        ]

        if direct_egid is not None:
            comment_parts.append(
                anzahl_text(
                    n_gwr_addresses,
                    "GWR-Adresse",
                    "GWR-Adressen",
                )
                + f" für EGID {direct_egid}"
            )

            comment_parts.append(
                anzahl_text(
                    n_gvbs_for_egid,
                    "GVBSID",
                    "GVBSIDs",
                )
                + " mit dieser EGID als eindeutigem "
                  "Adresskandidaten"
            )

            comment_parts.append(
                anzahl_text(
                    n_gvbs_addresses_for_egid,
                    "unterschiedliche GVBS-Adresse",
                    "unterschiedliche GVBS-Adressen",
                )
                + " für diese EGID"
            )

        comment = "; ".join(comment_parts) + "."

        if category == "no_match":
            comment += (
                " Kein passender GWR-Adresstreffer."
            )

        elif category == "invalid_input":
            comment += (
                " Mindestens ein Pflichtfeld fehlt."
            )

        elif category == "perfect_match":
            comment += (
                " Eindeutige Zuordnung ohne Besonderheiten."
            )

        elif category == "super_match":
            reasons = super_match_reasons(
                egid=direct_egid,
                egid_addresses=egid_addresses,
                egid_grids=egid_grids,
                grid_egids=grid_egids,
            )

            comment += (
                " Eindeutige Zuordnung als super_match. "
                "Kein perfect_match, weil: "
                + " ".join(reasons)
            )

        elif category == "review_address_suffix":
            comment += (
                " Mögliche zusätzliche EGIDs mit "
                "Hausnummernzusätzen erkannt. "
                "Direkter EGID-Kandidat: "
                f"{direct_egid}. "
                "Weitere mögliche EGIDs: "
                + suffix_conflicts_text(suffix_conflicts)
                + ". Keine automatische Zuordnung."
            )

        elif category == (
            "multiple_gvbsid_same_address_one_egid"
        ):
            comment += (
                " Mehrere GVBSIDs mit identischer "
                "GVBS-Adresse beanspruchen dieselbe EGID."
            )

        elif category == "multiple_gvbsid_one_egid":
            comment += (
                " Mehrere GVBSIDs mit unterschiedlichen "
                "GVBS-Adressen beanspruchen dieselbe EGID."
            )

        # ----------------------------------------------------
        # AUSFÜHRLICHE ZUSAMMENFASSUNG
        # ----------------------------------------------------

        summary = create_summary(
            gvbsid=gvbsid_text(gvbs_key),
            gvbs_address=key,
            category=category,
            candidates=candidates,
            grids=grids,
            parcel_egids=parcel_egids,
            egid_addresses=egid_addresses,
            egid_grids=egid_grids,
            grid_egids=grid_egids,
            gvbs_by_egid=gvbs_by_egid,
            gvbs_addresses_by_id=gvbs_addresses_by_id,
            suffix_conflicts=suffix_conflicts,
        )

        # ----------------------------------------------------
        # ZUSÄTZLICHE EGIDs AUS HAUSNUMMERNZUSÄTZEN
        # ----------------------------------------------------

        suffix_egids = sorted_egids({
            conflict["EGID"]
            for conflict in suffix_conflicts
        })

        suffix_addresses = sorted({
            conflict["GWR-Adresse"]
            for conflict in suffix_conflicts
        })

        suffix_grids = sorted({
            conflict["EGRID"]
            for conflict in suffix_conflicts
        })

        # ----------------------------------------------------
        # ERGEBNIS
        # ----------------------------------------------------

        results.append({
            **record,

            "GVBSID":
                gvbsid_text(gvbs_key),

            "EGID":
                assigned_egid,

            "Matching-Kategorie":
                category,

            "Match-Kommentar":
                comment,

            "Anzahl GVBSID an Adresse":
                n_gvbs_at_address,

            "Anzahl EGID an Adresse":
                len(candidates),

            "Anzahl GWR-Adressen pro EGID":
                n_gwr_addresses,

            "Anzahl EGRID":
                len(grids),

            "Anzahl EGID auf EGRID":
                len(parcel_egids),

            "Anzahl GVBSID pro EGID":
                n_gvbs_for_egid,

            "Anzahl GVBS-Adressen pro EGID":
                n_gvbs_addresses_for_egid,

            "EGID-Kandidaten":
                list_text(candidates)
                if candidates
                else "",

            "EGRID-Kandidaten":
                list_text(sorted(grids))
                if grids
                else "",

            "Automatische Zuordnung":
                "Ja"
                if assigned_egid is not None
                else "Nein",

            # -----------------------------------------------
            # NEUE SPALTEN FÜR HAUSNUMMERNZUSÄTZE
            # -----------------------------------------------

            "Anzahl EGID mit Hausnummernzusatz":
                len(suffix_egids),

            "EGID mit Hausnummernzusatz":
                list_text(suffix_egids)
                if suffix_egids
                else "",

            "GWR-Adressen mit Hausnummernzusatz":
                list_text(
                    address_text(a)
                    for a in suffix_addresses
                )
                if suffix_addresses
                else "",

            "EGRID der Hausnummernzusätze":
                list_text(suffix_grids)
                if suffix_grids
                else "",

            "Matching-Zusammenfassung":
                summary,
        })

    return results


# ============================================================
# EXCEL-AUSGABE
# ============================================================

def save_excel(path, headers, results):
    wb = Workbook()

    ws = wb.active
    ws.title = "Matching"

    extras = [
        "GVBSID",
        "EGID",
        "Matching-Kategorie",
        "Match-Kommentar",
        "Anzahl GVBSID an Adresse",
        "Anzahl EGID an Adresse",
        "Anzahl GWR-Adressen pro EGID",
        "Anzahl EGRID",
        "Anzahl EGID auf EGRID",
        "Anzahl GVBSID pro EGID",
        "Anzahl GVBS-Adressen pro EGID",
        "EGID-Kandidaten",
        "EGRID-Kandidaten",
        "Automatische Zuordnung",
        "Anzahl EGID mit Hausnummernzusatz",
        "EGID mit Hausnummernzusatz",
        "GWR-Adressen mit Hausnummernzusatz",
        "EGRID der Hausnummernzusätze",
        "Matching-Zusammenfassung",
    ]

    columns = headers + [
        column
        for column in extras
        if column not in headers
    ]

    ws.append(columns)

    for result in results:
        ws.append([
            result.get(column)
            for column in columns
        ])

    # --------------------------------------------------------
    # ZUSAMMENFASSUNG
    # --------------------------------------------------------

    summary = wb.create_sheet(
        "Zusammenfassung"
    )

    summary.append([
        "Kategorie",
        "Anzahl",
    ])

    counts = Counter(
        result["Matching-Kategorie"]
        for result in results
    )

    for name, _, _ in CATEGORIES:
        summary.append([
            name,
            counts[name],
        ])

    summary.append([
        "Gesamt",
        len(results),
    ])

    summary.append([
        "Automatisch zugeordnet",
        sum(
            result["Automatische Zuordnung"] == "Ja"
            for result in results
        ),
    ])

    summary.append([
        "Nicht automatisch zugeordnet",
        sum(
            result["Automatische Zuordnung"] == "Nein"
            for result in results
        ),
    ])

    # --------------------------------------------------------
    # KATEGORIEN-HINWEISE
    # --------------------------------------------------------

    notes = wb.create_sheet(
        "Kategorien-Hinweise"
    )

    notes.append([
        "Kategorie",
        "Definition",
        "Vorgehen",
    ])

    for row in CATEGORIES:
        notes.append(row)

    notes.append([
        "Grundregel",
        "Die automatische Zuordnung erfolgt ausschliesslich "
        "für perfect_match und super_match.",
        "",
    ])

    notes.append([
        "GVBSID",
        "Eine GVBSID besteht aus Kontrollnummer "
        "und Gebäude (Nr.).",
        "",
    ])

    notes.append([
        "GWR-Adressen",
        "Eine EGID kann mehrere GWR-Adressen besitzen. "
        "Dies ist allein kein Ausschlussgrund.",
        "",
    ])

    notes.append([
        "GVBS-Adressen",
        "Mehrere unterschiedliche GVBSIDs, die dieselbe "
        "EGID als einzigen Adresskandidaten haben, "
        "verhindern die automatische Zuordnung.",
        "",
    ])

    notes.append([
        "EGRID",
        "Weitere EGIDs auf derselben EGRID oder mehrere "
        "EGRIDs für dieselbe EGID sind allein "
        "kein Ausschlussgrund für super_match.",
        "",
    ])

    notes.append([
        "review_address_suffix",
        "Ausgangspunkt ist immer die GVBSID mit ihrer "
        "GVBS-Adresse. Nach einem eindeutigen direkten "
        "EGID-Adresstreffer werden weitere EGIDs "
        "auf denselben EGRIDs untersucht. "
        "Bei gleicher Strasse und PLZ sowie einer "
        "Hausnummer mit Zusatz wird geprüft, ob "
        "für diese zusätzliche GWR-Adresse eine "
        "eigene GVBSID im eingelesenen Datensatz "
        "vorhanden ist.",
        "Bei fehlender eigener GVBSID wird die "
        "automatische Zuordnung verhindert.",
    ])

    notes.append([
        "Hausnummernzusätze",
        "Erkannt werden nummerierte Zusätze wie "
        "30.1 oder 30.12 sowie Buchstabenzusätze "
        "wie 30a oder 30ab. "
        "Nicht erkannt werden beispielsweise "
        "30/31 oder abweichende Hausnummern wie 31.",
        "",
    ])

    notes.append([
        "super_match",
        "Die konkrete Begründung wird für jede GVBSID "
        "einzeln berechnet. Alle Abweichungen von "
        "perfect_match werden mit EGIDs, EGRIDs "
        "und GWR-Adressen dokumentiert.",
        "",
    ])

    notes.append([
        "GWR-Datenbestand",
        "Es werden ausschliesslich bestehende Gebäude "
        "mit GSTAT = 1004 berücksichtigt.",
        "",
    ])

    notes.append([
        "Einschränkung",
        "Die verwendete GWR-building.EGRID-Spalte "
        "kann nicht sämtliche Grundstücksbeziehungen "
        "eines Gebäudes abbilden.",
        "",
    ])

    notes.append([
        "Prüfumfang",
        "Konkurrierende GVBSIDs und das Fehlen einer "
        "eigenen GVBSID an einer zusätzlichen GWR-Adresse "
        "werden ausschliesslich anhand der eingelesenen "
        "GVBS-Excel-Datei beurteilt. "
        "Ein fehlender Eintrag in dieser Datei beweist "
        "nicht, dass bei der GVBS keine entsprechende "
        "GVBSID existiert.",
        "",
    ])

    notes.append([
        "Eindeutigkeit",
        "Ein eindeutiger Adresstreffer ist eine "
        "datenbasierte Zuordnung, aber kein unabhängiger "
        "Nachweis der tatsächlichen Gebäudeidentität.",
        "",
    ])

    # --------------------------------------------------------
    # FORMATIERUNG
    # --------------------------------------------------------

    for sheet in wb.worksheets:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

        for cell in sheet[1]:
            cell.font = Font(
                bold=True,
                color="FFFFFF",
            )

            cell.fill = PatternFill(
                "solid",
                fgColor="17365D",
            )

            cell.alignment = Alignment(
                wrap_text=True,
                vertical="center",
            )

        sheet.row_dimensions[1].height = 32

    for index, column in enumerate(
        columns,
        start=1,
    ):
        letter = get_column_letter(index)

        if column == "Matching-Zusammenfassung":
            width = 110

        elif column == "Match-Kommentar":
            width = 75

        elif column == "Matching-Kategorie":
            width = 43

        elif column in (
            "EGID-Kandidaten",
            "EGRID-Kandidaten",
            "EGID mit Hausnummernzusatz",
            "GWR-Adressen mit Hausnummernzusatz",
            "EGRID der Hausnummernzusätze",
        ):
            width = 45

        else:
            width = min(
                max(len(column) + 4, 16),
                32,
            )

        ws.column_dimensions[letter].width = width

    # --------------------------------------------------------
    # KATEGORIEN EINFÄRBEN
    # --------------------------------------------------------

    for row in ws.iter_rows(min_row=2):
        category = None

        for cell in row:
            if (
                columns[cell.column - 1]
                == "Matching-Kategorie"
            ):
                category = cell.value
                break

        if category == "perfect_match":
            fill_color = "E2F0D9"

        elif category == "super_match":
            fill_color = "DDEBF7"

        elif category == "review_address_suffix":
            fill_color = "FFF2CC"

        elif category in (
            "multiple_gvbsid_same_address_one_egid",
            "multiple_gvbsid_one_egid",
        ):
            fill_color = "FCE4D6"

        else:
            fill_color = None

        for cell in row:
            if fill_color:
                cell.fill = PatternFill(
                    "solid",
                    fgColor=fill_color,
                )

            if columns[cell.column - 1] in (
                "Match-Kommentar",
                "Matching-Zusammenfassung",
            ):
                cell.alignment = Alignment(
                    wrap_text=True,
                    vertical="top",
                )

    summary.column_dimensions["A"].width = 48
    summary.column_dimensions["B"].width = 20

    notes.column_dimensions["A"].width = 48
    notes.column_dimensions["B"].width = 110
    notes.column_dimensions["C"].width = 75

    for row in notes.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(
                wrap_text=True,
                vertical="top",
            )

    wb.save(path)


# ============================================================
# HAUPTPROGRAMM
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Lokales GVBSID-EGID-Matching"
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "gebaeude_egid_matching.xlsx"
        ),
    )

    parser.add_argument(
        "--gwr-db",
        type=Path,
        default=DEFAULT_GWR_DB,
    )

    args = parser.parse_args()

    if (
        args.input.resolve()
        == args.output.resolve()
    ):
        parser.error(
            "Eingabe und Ausgabe dürfen nicht identisch sein."
        )

    (
        addr_egids,
        egid_addresses,
        egid_grids,
        grid_egids,
    ) = read_gwr(args.gwr_db)

    headers, records = read_excel(
        args.input
    )

    results = match(
        records,
        addr_egids,
        egid_addresses,
        egid_grids,
        grid_egids,
    )

    save_excel(
        args.output,
        headers,
        results,
    )

    print()
    print(
        f"Ergebnis: {args.output.resolve()}"
    )
    print()

    counts = Counter(
        result["Matching-Kategorie"]
        for result in results
    )

    for category, count in sorted(
        counts.items()
    ):
        print(
            f"  {category}: {count}"
        )

    assigned = sum(
        result["Automatische Zuordnung"] == "Ja"
        for result in results
    )

    print()
    print(
        f"Gesamt: {len(results)}"
    )
    print(
        f"Automatisch zugeordnet: {assigned}"
    )
    print(
        "Nicht automatisch zugeordnet: "
        f"{len(results) - assigned}"
    )


if __name__ == "__main__":
    main()
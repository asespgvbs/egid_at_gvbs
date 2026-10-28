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

GWR_DB = Path(
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
        "Genau eine EGID stimmt mit der GVBS-Adresse überein. "
        "Die EGID besitzt genau eine GWR-Adresse, eine EGRID "
        "und keine weitere bestehende EGID auf dieser EGRID. "
        "Keine andere GVBSID hat dieselbe EGID als eindeutigen "
        "Adresstreffer.",
        "Automatische Zuordnung.",
    ),
    (
        "good_match",
        "Eine EGID mit mehreren nachgewiesenen EGRIDs.",
        "Reserviert, da die verfügbaren GWR-Daten "
        "Mehrfach-Grundstücksbeziehungen nicht vollständig abbilden.",
    ),
    (
        "multiple_addresses_one_egid",
        "Eine EGID wurde über die GVBS-Adresse gefunden, "
        "besitzt aber mehrere unterschiedliche GWR-Adressen.",
        "Manuell prüfen.",
    ),
    (
        "multiple_egid",
        "Mehrere EGIDs besitzen eine GWR-Adresse, "
        "die mit der GVBS-Adresse übereinstimmt.",
        "Manuell prüfen.",
    ),
    (
        "multiple_gvbsid_multiple_egid",
        "Mehrere GVBSIDs besitzen dieselbe GVBS-Adresse, "
        "für die mehrere EGIDs im GWR gefunden wurden.",
        "Manuell prüfen.",
    ),
    (
        "multiple_gvbsid_one_egid",
        "Mehrere GVBSIDs haben dieselbe EGID "
        "als eindeutigen Adresstreffer.",
        "Mögliche n:1-Beziehung manuell prüfen.",
    ),
    (
        "review_parcel",
        "Ein eindeutiger Adresstreffer, aber mehrere "
        "bestehende EGIDs auf der zugehörigen EGRID.",
        "Manuell prüfen.",
    ),
    (
        "review_missing_egrid",
        "Ein eindeutiger Adresstreffer, "
        "aber keine EGRID vorhanden.",
        "Manuell prüfen.",
    ),
    (
        "no_match",
        "Die bei der GVBS hinterlegte Adresse stimmt "
        "mit keiner Adresse eines bestehenden GWR-Gebäudes überein.",
        "Keine automatische Zuordnung.",
    ),
    (
        "invalid_input",
        "Mindestens ein erforderliches Eingabefeld fehlt.",
        "Eingabedaten korrigieren.",
    ),
]


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def as_text(value):
    if value is None:
        return ""

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value).strip()


def normalize_address(street, number, postal):
    street = re.sub(
        r"\s+",
        " ",
        as_text(street).casefold().replace("ß", "ss"),
    ).strip()

    number = re.sub(
        r"\s+",
        "",
        as_text(number).casefold(),
    )

    return street, number, as_text(postal)


def gvbsid(record):
    return (
        as_text(record["Kontrollnummer"]),
        as_text(record["Gebäude (Nr.)"]),
    )


def gvbsid_text(record):
    kontrollnummer, gebaeudenummer = gvbsid(record)
    return f"{kontrollnummer}-{gebaeudenummer}"


def format_address(street, number, postal):
    return (
        f"{as_text(street)} {as_text(number)}, "
        f"{as_text(postal)}"
    ).strip()


def format_values(values):
    return ", ".join(
        str(value)
        for value in sorted(values)
    )


def format_gwr_addresses(egid, egid_addresses):
    """
    Gibt die tatsächlich im GWR gespeicherten Adressen
    einer EGID als lesbaren Text zurück.
    """

    addresses = egid_addresses.get(egid, set())

    if not addresses:
        return "Keine vollständige GWR-Adresse vorhanden"

    return "; ".join(sorted(addresses))


# ============================================================
# GWR EINLESEN
# ============================================================

def read_gwr(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"GWR-Datenbank nicht gefunden: {path}"
        )

    connection = sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro",
        uri=True,
    )

    try:
        buildings = connection.execute(
            """
            SELECT EGID, EGRID
            FROM building
            WHERE GSTAT = 1004
              AND EGID IS NOT NULL
            """
        ).fetchall()

        entrances = connection.execute(
            """
            SELECT
                e.EGID,
                e.STRNAME,
                e.DEINR,
                e.DPLZ4
            FROM entrance e
            JOIN building b
                ON b.EGID = e.EGID
            WHERE b.GSTAT = 1004
              AND b.EGID IS NOT NULL
            """
        ).fetchall()

    finally:
        connection.close()

    # Adresse -> EGIDs
    address_egids = defaultdict(set)

    # EGID -> normalisierte Adressen
    egid_address_keys = defaultdict(set)

    # EGID -> tatsächliche GWR-Adressen
    egid_addresses = defaultdict(set)

    # EGID -> EGRIDs
    egid_grids = defaultdict(set)

    # EGRID -> EGIDs
    grid_egids = defaultdict(set)

    for egid, egrid in buildings:
        if as_text(egrid):
            egrid = as_text(egrid)

            egid_grids[egid].add(egrid)
            grid_egids[egrid].add(egid)

    for egid, street, number, postal in entrances:
        key = normalize_address(
            street,
            number,
            postal,
        )

        if not all(key):
            continue

        address_egids[key].add(egid)
        egid_address_keys[egid].add(key)

        # Originale Schreibweise aus dem GWR verwenden.
        egid_addresses[egid].add(
            format_address(street, number, postal)
        )

    return (
        address_egids,
        egid_address_keys,
        egid_addresses,
        egid_grids,
        grid_egids,
    )


# ============================================================
# EXCEL EINLESEN
# ============================================================

def read_excel(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"Excel-Datei nicht gefunden: {path}"
        )

    workbook = load_workbook(
        path,
        read_only=True,
        data_only=True,
    )

    try:
        rows = workbook.active.iter_rows(
            values_only=True
        )

        first_row = next(rows, None)

        if first_row is None:
            raise ValueError(
                "Die Excel-Datei ist leer."
            )

        headers = [
            as_text(value)
            for value in first_row
        ]

        if len(headers) != len(set(headers)):
            raise ValueError(
                "Doppelte Spaltenüberschriften in Excel."
            )

        missing = [
            column
            for column in REQUIRED
            if column not in headers
        ]

        if missing:
            raise ValueError(
                f"Fehlende Pflichtspalten: {missing}"
            )

        records = [
            dict(zip(headers, row))
            for row in rows
            if any(value is not None for value in row)
        ]

        return headers, records

    finally:
        workbook.close()


# ============================================================
# FLIESSTEXT-ZUSAMMENFASSUNG
# ============================================================

def create_summary(
    record,
    category,
    address_candidates,
    egrids,
    parcel_egids,
    egid_address_keys,
    egid_addresses,
    n_gvbs,
    n_shared,
):
    """
    Erstellt eine verständliche Zusammenfassung.

    Wichtig:
    - GVBS-Adresse und GWR-Adresse werden getrennt.
    - GWR-Adressen stammen tatsächlich aus dem GWR.
    - Direkte Adresstreffer und zusätzliche EGIDs
      auf derselben EGRID werden unterschieden.
    """

    identity = gvbsid_text(record)

    gvbs_address = format_address(
        record["Strasse"],
        record["Nr."],
        record["PLZ"],
    )

    # --------------------------------------------------------
    # UNVOLLSTÄNDIGE EINGABE
    # --------------------------------------------------------

    if category == "invalid_input":
        return (
            f"Die GVBSID {identity} konnte nicht mit dem GWR "
            "abgeglichen werden, weil mindestens eine "
            "erforderliche Angabe in den GVBS-Daten fehlt. "
            "Die Eingabedaten müssen zuerst vervollständigt "
            "werden."
        )

    # --------------------------------------------------------
    # KEIN ADRESSTREFFER
    # --------------------------------------------------------

    if category == "no_match":
        return (
            f"Die bei der GVBS für die GVBSID {identity} "
            f"hinterlegte Adresse {gvbs_address} hat mit "
            "keiner Adresse eines bestehenden Gebäudes "
            "im GWR übereingestimmt (GSTAT=1004). "
            "Deshalb konnte keine EGID zugeordnet werden."
        )

    # --------------------------------------------------------
    # EINLEITUNG
    # --------------------------------------------------------

    text = (
        f"Für die GVBSID {identity} ist bei der GVBS "
        f"die Adresse {gvbs_address} hinterlegt. "
    )

    # --------------------------------------------------------
    # DIREKTES ADRESSMATCHING
    # --------------------------------------------------------

    if len(address_candidates) == 1:
        egid = address_candidates[0]

        gwr_addresses = format_gwr_addresses(
            egid,
            egid_addresses,
        )

        text += (
            "Beim Abgleich mit den Adressen bestehender "
            "Gebäude im GWR wurde genau eine passende "
            f"EGID gefunden: {egid}. "
            f"Für diese EGID sind im GWR folgende "
            f"Adressen hinterlegt: {gwr_addresses}. "
        )

    else:
        text += (
            "Beim Abgleich mit den Adressen bestehender "
            f"Gebäude im GWR wurden "
            f"{len(address_candidates)} passende "
            "EGIDs gefunden. "
        )

        for egid in address_candidates:
            gwr_addresses = format_gwr_addresses(
                egid,
                egid_addresses,
            )

            text += (
                f"EGID {egid}: "
                f"GWR-Adresse(n) {gwr_addresses}. "
            )

    # --------------------------------------------------------
    # EGRID-PRÜFUNG
    # --------------------------------------------------------

    if not egrids:
        text += (
            "Für die gefundenen EGIDs ist im verwendeten "
            "GWR-Datensatz keine EGRID hinterlegt. "
        )

    elif len(egrids) == 1:
        egrid = next(iter(egrids))

        text += (
            f"Die zugehörige EGRID lautet {egrid}. "
        )

        if len(parcel_egids) == 1:
            text += (
                "Auf dieser EGRID ist im verwendeten "
                "GWR-Datensatz genau eine bestehende "
                "EGID registriert. "
            )

        else:
            text += (
                f"Auf dieser EGRID sind insgesamt "
                f"{len(parcel_egids)} bestehende "
                "EGIDs registriert. "
            )

            additional_egids = (
                set(parcel_egids)
                - set(address_candidates)
            )

            if additional_egids:
                text += (
                    "Zusätzlich zum direkten Adressmatching "
                    "wurden über die gemeinsame EGRID "
                    "folgende EGIDs gefunden: "
                )

                for egid in sorted(additional_egids):
                    gwr_addresses = format_gwr_addresses(
                        egid,
                        egid_addresses,
                    )

                    text += (
                        f"EGID {egid} mit der GWR-Adresse "
                        f"bzw. den GWR-Adressen "
                        f"{gwr_addresses}. "
                    )

    else:
        text += (
            "Die gefundenen EGIDs sind mit "
            f"{len(egrids)} EGRIDs verknüpft: "
            f"{format_values(egrids)}. "
        )

        text += (
            f"Auf diesen EGRIDs sind insgesamt "
            f"{len(parcel_egids)} bestehende "
            "EGIDs registriert. "
        )

        additional_egids = (
            set(parcel_egids)
            - set(address_candidates)
        )

        if additional_egids:
            text += (
                "Folgende zusätzliche EGIDs wurden "
                "erst über die EGRIDs gefunden: "
            )

            for egid in sorted(additional_egids):
                gwr_addresses = format_gwr_addresses(
                    egid,
                    egid_addresses,
                )

                text += (
                    f"EGID {egid} "
                    f"({gwr_addresses}). "
                )

    # --------------------------------------------------------
    # MEHRERE GWR-ADRESSEN
    # --------------------------------------------------------

    if len(address_candidates) == 1:
        egid = address_candidates[0]

        n_addresses = len(
            egid_address_keys.get(egid, set())
        )

        if n_addresses == 1:
            text += (
                f"Die EGID {egid} besitzt im GWR "
                "genau eine unterschiedliche Adresse. "
            )

        elif n_addresses > 1:
            text += (
                f"Die EGID {egid} besitzt im GWR "
                f"insgesamt {n_addresses} unterschiedliche "
                "Adressen. "
            )

    # --------------------------------------------------------
    # MEHRERE GVBSIDs
    # --------------------------------------------------------

    if n_shared > 1:
        text += (
            f"Die EGID ist ausserdem für insgesamt "
            f"{n_shared} unterschiedliche GVBSIDs "
            "ein eindeutiger Adresstreffer. "
        )

    elif n_gvbs > 1:
        text += (
            f"Bei der GVBS sind unter derselben "
            f"Adresse {n_gvbs} unterschiedliche "
            "GVBSIDs erfasst. "
        )

    # --------------------------------------------------------
    # FACHLICHE BEURTEILUNG
    # --------------------------------------------------------

    explanations = {
        "perfect_match": (
            "Die Zuordnung erfüllt sämtliche definierten "
            "Kriterien für ein Perfect Match: "
            "ein eindeutiger Adresstreffer, nur eine "
            "GWR-Adresse für diese EGID, genau eine "
            "EGRID mit nur einer bestehenden EGID "
            "und keine weitere GVBSID mit derselben "
            "EGID als eindeutigen Adresstreffer. "
            "Die EGID wird automatisch zugeordnet."
        ),

        "good_match": (
            "Die Zuordnung muss hinsichtlich der "
            "Grundstücksbeziehungen zusätzlich geprüft "
            "werden. Eine automatische Zuordnung "
            "erfolgt nicht."
        ),

        "multiple_addresses_one_egid": (
            "Obwohl die bei der GVBS hinterlegte "
            "Adresse mit einer GWR-Adresse "
            "übereinstimmt, besitzt die gefundene "
            "EGID weitere GWR-Adressen. "
            "Nach den festgelegten Kriterien ist "
            "die Zuordnung deshalb nicht ausreichend "
            "eindeutig und muss überprüft werden."
        ),

        "multiple_egid": (
            "Die bei der GVBS hinterlegte Adresse "
            "stimmt mit den GWR-Adressen mehrerer "
            "EGIDs überein. Es kann deshalb nicht "
            "automatisch entschieden werden, "
            "welche EGID zur GVBSID gehört. "
            "Eine manuelle Prüfung ist erforderlich."
        ),

        "multiple_gvbsid_multiple_egid": (
            "An der bei der GVBS hinterlegten Adresse "
            "existieren mehrere GVBSIDs. Gleichzeitig "
            "wurden im GWR mehrere passende EGIDs "
            "gefunden. Die Beziehungen zwischen "
            "GVBSIDs und EGIDs müssen manuell "
            "geprüft werden."
        ),

        "multiple_gvbsid_one_egid": (
            "Mehrere GVBSIDs haben dieselbe EGID "
            "als eindeutigen Adresstreffer. "
            "Dies kann eine zulässige n:1-Beziehung "
            "darstellen, beispielsweise wenn mehrere "
            "GVBS-Versicherungsobjekte einem einzigen "
            "GWR-Gebäude entsprechen. "
            "Die Zuordnung muss überprüft werden."
        ),

        "review_parcel": (
            "Die bei der GVBS hinterlegte Adresse "
            "hat genau eine EGID im GWR getroffen. "
            "Auf der zugehörigen EGRID befindet sich "
            "jedoch mindestens eine weitere EGID, "
            "die nicht zwingend dieselbe Adresse "
            "besitzt. Der direkte Adresstreffer ist "
            "damit eindeutig, die gesamte "
            "Grundstückssituation jedoch nicht. "
            "Eine manuelle Prüfung ist erforderlich."
        ),

        "review_missing_egrid": (
            "Die bei der GVBS hinterlegte Adresse "
            "hat genau eine EGID im GWR getroffen. "
            "Da für diese EGID keine EGRID vorhanden "
            "ist, kann nicht überprüft werden, "
            "ob auf derselben Parzelle weitere "
            "EGIDs existieren. "
            "Eine manuelle Prüfung ist erforderlich."
        ),
    }

    text += explanations.get(
        category,
        "Die Zuordnung muss überprüft werden.",
    )

    return text.strip()


# ============================================================
# MATCHING
# ============================================================

def match(
    records,
    address_egids,
    egid_address_keys,
    egid_addresses,
    egid_grids,
    grid_egids,
):
    address_gvbsids = defaultdict(set)
    egid_gvbsids = defaultdict(set)

    # --------------------------------------------------------
    # GVBSIDs PRO ADRESSE UND EGID ERMITTELN
    # --------------------------------------------------------

    for record in records:
        key = normalize_address(
            record["Strasse"],
            record["Nr."],
            record["PLZ"],
        )

        identity = gvbsid(record)

        if not (all(key) and all(identity)):
            continue

        address_gvbsids[key].add(identity)

        candidates = address_egids.get(
            key,
            set(),
        )

        if len(candidates) == 1:
            egid = next(iter(candidates))

            egid_gvbsids[egid].add(identity)

    results = []

    # --------------------------------------------------------
    # EINZELNE GVBS-DATENSÄTZE PRÜFEN
    # --------------------------------------------------------

    for record in records:
        key = normalize_address(
            record["Strasse"],
            record["Nr."],
            record["PLZ"],
        )

        identity = gvbsid(record)

        valid = all(key) and all(identity)

        address_candidates = (
            sorted(address_egids.get(key, set()))
            if valid
            else []
        )

        # EGRIDs der Adresstreffer
        egrids = (
            set().union(
                *(
                    egid_grids.get(egid, set())
                    for egid in address_candidates
                )
            )
            if address_candidates
            else set()
        )

        # Alle EGIDs auf diesen EGRIDs
        parcel_egids = (
            set().union(
                *(
                    grid_egids.get(egrid, set())
                    for egrid in egrids
                )
            )
            if egrids
            else set()
        )

        n_gvbs = (
            len(address_gvbsids[key])
            if valid
            else 0
        )

        n_addresses = (
            len(
                egid_address_keys.get(
                    address_candidates[0],
                    set(),
                )
            )
            if len(address_candidates) == 1
            else None
        )

        n_shared = (
            len(
                egid_gvbsids[
                    address_candidates[0]
                ]
            )
            if len(address_candidates) == 1
            else 0
        )

        # ----------------------------------------------------
        # KATEGORIE
        # ----------------------------------------------------

        if not valid:
            category = "invalid_input"

        elif not address_candidates:
            category = "no_match"

        elif len(address_candidates) > 1:
            category = (
                "multiple_gvbsid_multiple_egid"
                if n_gvbs > 1
                else "multiple_egid"
            )

        elif n_gvbs > 1 or n_shared > 1:
            category = "multiple_gvbsid_one_egid"

        elif len(parcel_egids) > 1:
            category = "review_parcel"

        elif not egrids:
            category = "review_missing_egrid"

        elif n_addresses > 1:
            category = "multiple_addresses_one_egid"

        elif (
            len(egrids) == 1
            and len(parcel_egids) == 1
        ):
            category = "perfect_match"

        else:
            category = "good_match"

        # Nur Perfect Matches automatisch zuordnen
        assigned_egid = (
            address_candidates[0]
            if category == "perfect_match"
            else None
        )

        # ----------------------------------------------------
        # TECHNISCHER KOMMENTAR
        # ----------------------------------------------------

        comment = (
            f"{n_gvbs} GVBSID(s) an GVBS-Adresse; "
            f"{len(address_candidates)} bestehende "
            "EGID(s) an GWR-Adresse; "
            f"{len(egrids)} EGRID(s) der Adresskandidaten; "
            f"{len(parcel_egids)} bestehende "
            "EGID(s) auf diesen EGRID(s)."
        )

        if len(address_candidates) == 1:
            comment += (
                f" EGID {address_candidates[0]} besitzt "
                f"{n_addresses} unterschiedliche "
                "GWR-Adresse(n) und ist Adresskandidat "
                f"für {n_shared} unterschiedliche GVBSID(s)."
            )

        if category == "no_match":
            comment += (
                " Kein passender GWR-Adressdatensatz "
                "mit GSTAT=1004."
            )

        if category == "invalid_input":
            comment += (
                " Mindestens ein Pflichtfeld fehlt."
            )

        # ----------------------------------------------------
        # GWR-ADRESSEN DER DIREKTEN EGID-KANDIDATEN
        # ----------------------------------------------------

        direct_gwr_addresses = []

        for egid in address_candidates:
            direct_gwr_addresses.append(
                f"EGID {egid}: "
                f"{format_gwr_addresses(egid, egid_addresses)}"
            )

        # ----------------------------------------------------
        # GWR-ADRESSEN ALLER EGIDs AUF DER EGRID
        # ----------------------------------------------------

        parcel_gwr_addresses = []

        for egid in sorted(parcel_egids):
            source = (
                "Adresstreffer"
                if egid in address_candidates
                else "zusätzlich über EGRID"
            )

            parcel_gwr_addresses.append(
                f"EGID {egid} ({source}): "
                f"{format_gwr_addresses(egid, egid_addresses)}"
            )

        # ----------------------------------------------------
        # FLIESSTEXT
        # ----------------------------------------------------

        summary = create_summary(
            record=record,
            category=category,
            address_candidates=address_candidates,
            egrids=egrids,
            parcel_egids=parcel_egids,
            egid_address_keys=egid_address_keys,
            egid_addresses=egid_addresses,
            n_gvbs=n_gvbs,
            n_shared=n_shared,
        )

        # ----------------------------------------------------
        # ERGEBNIS
        # ----------------------------------------------------

        results.append({
            **record,

            "GVBSID": gvbsid_text(record),

            "EGID": assigned_egid,

            "Matching-Kategorie": category,

            "Match-Kommentar": comment,

            "GVBSIDs an GVBS-Adresse": n_gvbs,

            "EGIDs mit passender GWR-Adresse": (
                len(address_candidates)
            ),

            "EGRIDs der gefundenen EGIDs": (
                len(egrids)
            ),

            "EGIDs auf zugehöriger EGRID": (
                len(parcel_egids)
            ),

            "GWR-Adressen der gefundenen EGID": (
                n_addresses
            ),

            "GVBSIDs mit derselben EGID als Adresstreffer": (
                n_shared
                if len(address_candidates) == 1
                else None
            ),

            "EGIDs aus Adressmatching": (
                format_values(address_candidates)
            ),

            "GWR-Adressen der EGID-Kandidaten": (
                " | ".join(direct_gwr_addresses)
            ),

            "EGIDs auf zugehöriger EGRID (Liste)": (
                format_values(parcel_egids)
            ),

            "GWR-Adressen der EGIDs auf EGRID": (
                " | ".join(parcel_gwr_addresses)
            ),

            "EGRIDs aus Adressmatching": (
                format_values(egrids)
            ),

            "Matching-Zusammenfassung": summary,
        })

    return results


# ============================================================
# EXCEL EXPORT
# ============================================================

def save_excel(path, headers, results):
    workbook = Workbook()

    # --------------------------------------------------------
    # BLATT 1: MATCHING
    # --------------------------------------------------------

    sheet = workbook.active
    sheet.title = "Matching"

    extra_columns = [
        "GVBSID",
        "EGID",
        "Matching-Kategorie",
        "Match-Kommentar",

        "GVBSIDs an GVBS-Adresse",
        "EGIDs mit passender GWR-Adresse",
        "EGRIDs der gefundenen EGIDs",
        "EGIDs auf zugehöriger EGRID",

        "GWR-Adressen der gefundenen EGID",
        "GVBSIDs mit derselben EGID als Adresstreffer",

        "EGIDs aus Adressmatching",
        "GWR-Adressen der EGID-Kandidaten",

        "EGIDs auf zugehöriger EGRID (Liste)",
        "GWR-Adressen der EGIDs auf EGRID",

        "EGRIDs aus Adressmatching",

        "Matching-Zusammenfassung",
    ]

    # Originalspalten behalten.
    # Matching-Zusammenfassung immer ganz rechts.
    columns = [
        column
        for column in headers
        if column != "Matching-Zusammenfassung"
    ]

    columns += [
        column
        for column in extra_columns
        if column not in columns
    ]

    sheet.append(columns)

    for record in results:
        sheet.append([
            record.get(column)
            for column in columns
        ])

    # --------------------------------------------------------
    # BLATT 2: ZUSAMMENFASSUNG
    # --------------------------------------------------------

    summary = workbook.create_sheet(
        "Zusammenfassung"
    )

    summary.append([
        "Matching-Kategorie",
        "Anzahl",
    ])

    counts = Counter(
        record["Matching-Kategorie"]
        for record in results
    )

    for category, _, _ in CATEGORIES:
        summary.append([
            category,
            counts[category],
        ])

    summary.append([
        "Gesamt",
        len(results),
    ])

    # --------------------------------------------------------
    # BLATT 3: KATEGORIEN-HINWEISE
    # --------------------------------------------------------

    notes = workbook.create_sheet(
        "Kategorien-Hinweise"
    )

    notes.append([
        "Kategorie",
        "Definition",
        "Vorgehen",
    ])

    for category in CATEGORIES:
        notes.append(category)

    notes.append([
        "Hinweis",
        "Es werden ausschliesslich bestehende "
        "GWR-Gebäude mit GSTAT=1004 berücksichtigt.",
        "",
    ])

    notes.append([
        "Hinweis",
        "Die GVBS-Adresse stammt aus der "
        "eingelesenen GVBS-Excel-Datei.",
        "",
    ])

    notes.append([
        "Hinweis",
        "Die GWR-Adressen stammen aus der "
        "Tabelle entrance der GWR-Datenbank.",
        "",
    ])

    notes.append([
        "Hinweis",
        "EGIDs aus Adressmatching enthält nur "
        "EGIDs, deren GWR-Adresse mit der "
        "GVBS-Adresse übereinstimmt.",
        "",
    ])

    notes.append([
        "Hinweis",
        "EGIDs auf zugehöriger EGRID enthält "
        "auch EGIDs, die nicht über die "
        "GVBS-Adresse gefunden wurden.",
        "",
    ])

    notes.append([
        "Hinweis",
        "Mehrere identische GWR-Adressen "
        "werden pro EGID nur einmal gezählt.",
        "",
    ])

    notes.append([
        "Hinweis",
        "Die EGRID-Zuordnung basiert auf "
        "dem EGRID-Feld der GWR-Tabelle building. "
        "Weitere Grundstücksbeziehungen sind "
        "damit nicht vollständig nachgewiesen.",
        "",
    ])

    notes.append([
        "Hinweis",
        "Die Kategorie good_match bleibt "
        "bis zur Verfügbarkeit vollständiger "
        "Grundstücksbeziehungen reserviert.",
        "",
    ])

    notes.append([
        "Hinweis",
        "Nur perfect_match führt zu einer "
        "automatischen EGID-Zuordnung.",
        "",
    ])

    notes.append([
        "Hinweis",
        "Die Matching-Zusammenfassung unterscheidet "
        "ausdrücklich zwischen der bei der GVBS "
        "hinterlegten Adresse und den im GWR "
        "gespeicherten Adressen.",
        "",
    ])

    # --------------------------------------------------------
    # FORMATIERUNG
    # --------------------------------------------------------

    for ws in workbook.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        for cell in ws[1]:
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

        if ws.title == "Matching":
            for index, column in enumerate(
                columns,
                start=1,
            ):
                letter = get_column_letter(index)

                if column == "Matching-Zusammenfassung":
                    width = 110

                elif column == "Match-Kommentar":
                    width = 85

                elif column == "Matching-Kategorie":
                    width = 38

                elif "GWR-Adressen" in column:
                    width = 65

                elif column in (
                    "EGIDs aus Adressmatching",
                    "EGIDs auf zugehöriger EGRID (Liste)",
                    "EGRIDs aus Adressmatching",
                ):
                    width = 40

                else:
                    width = 22

                ws.column_dimensions[letter].width = width

            # Fliesstext mit Zeilenumbruch anzeigen
            summary_col = columns.index(
                "Matching-Zusammenfassung"
            ) + 1

            for row in ws.iter_rows(min_row=2):
                row[summary_col - 1].alignment = Alignment(
                    wrap_text=True,
                    vertical="top",
                )

        elif ws.title == "Kategorien-Hinweise":
            ws.column_dimensions["A"].width = 38
            ws.column_dimensions["B"].width = 100
            ws.column_dimensions["C"].width = 75

            for row in ws.iter_rows(min_row=2):
                for cell in row:
                    cell.alignment = Alignment(
                        wrap_text=True,
                        vertical="top",
                    )

        else:
            ws.column_dimensions["A"].width = 38
            ws.column_dimensions["B"].width = 18

    workbook.save(path)


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
        default=GWR_DB,
    )

    args = parser.parse_args()

    if args.input.resolve() == args.output.resolve():
        parser.error(
            "Eingabe- und Ausgabedatei dürfen "
            "nicht identisch sein."
        )

    gwr = read_gwr(args.gwr_db)

    headers, records = read_excel(
        args.input
    )

    results = match(
        records,
        *gwr,
    )

    save_excel(
        args.output,
        headers,
        results,
    )

    print(
        f"Ergebnis: {args.output.resolve()}"
    )

    counts = Counter(
        record["Matching-Kategorie"]
        for record in results
    )

    for category, count in sorted(counts.items()):
        print(
            f"  {category}: {count}"
        )


if __name__ == "__main__":
    main()
"""Gemeinsame Text-/ID-Helfer und Fehlerklassen ohne Datei- oder Datenzugriff."""

import re


class ReviewError(ValueError):
    pass


class ConflictError(ReviewError):
    pass


def txt(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def egid_text(value):
    value = txt(value)
    if not re.fullmatch(r"[1-9]\d*", value):
        raise ReviewError("EGID müssen positive ganze Zahlen sein.")
    return str(int(value))


def identifiers(value):
    return sorted({part.strip() for part in re.split(r"[,;\n]+", txt(value)) if part.strip()})

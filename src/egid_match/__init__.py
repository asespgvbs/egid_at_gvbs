"""GVBS-/EGID-Matching, Bestandsauswertung und manuelle Zuordnung."""


def main() -> None:
    """Bestehenden Konsolen-Einstieg auf das Matching weiterleiten."""
    from .matching import main as matching_main

    matching_main()

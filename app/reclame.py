"""Korte vermelding van de maker, getoond bij het opstarten (zelfde tekst als onderaan de web-app)."""
from __future__ import annotations

NAAM = "Schildermans AI"
EMAIL = "schildermansai@gmail.com"


def toon() -> None:
    lijn = "-" * 60  # gewone tekens: elke console kan ze tonen
    print(f"{lijn}\n  Gratis aangeboden door {NAAM}.\n"
          f"  Repetitieve taken sneller afhandelen met AI?\n  Mail naar {EMAIL}\n{lijn}", flush=True)

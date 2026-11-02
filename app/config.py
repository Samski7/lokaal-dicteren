"""Laadt config.yaml en zet relatieve paden om t.o.v. de projectmap."""
from pathlib import Path

import yaml

PROJECT_MAP = Path(__file__).resolve().parent.parent


def pad(relatief: str) -> Path:
    p = Path(relatief)
    return p if p.is_absolute() else PROJECT_MAP / p


def laad_config(bestand: str | Path | None = None) -> dict:
    bestand = Path(bestand) if bestand else PROJECT_MAP / "config.yaml"
    with open(bestand, encoding="utf-8") as f:
        return yaml.safe_load(f)

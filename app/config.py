"""Laadt config.yaml (+ eigen instellingen uit config.lokaal.yaml) en zet paden om."""
import sys
from pathlib import Path

import yaml

PROJECT_MAP = Path(__file__).resolve().parent.parent
# Eigen instellingen: staat niet in git, dus een update overschrijft ze nooit.
LOKAAL = PROJECT_MAP / "config.lokaal.yaml"


def utf8_console() -> None:
    """Console naar UTF-8: anders crasht een Windows-console op tekens als é, ë of ✓."""
    for stroom in (sys.stdout, sys.stderr):
        if hasattr(stroom, "reconfigure"):
            stroom.reconfigure(encoding="utf-8", errors="replace")


def pad(relatief: str) -> Path:
    p = Path(relatief)
    return p if p.is_absolute() else PROJECT_MAP / p


def _lees(bestand: Path) -> dict:
    # utf-8-sig: werkt ook als Kladblok het bestand met een BOM opslaat.
    with open(bestand, encoding="utf-8-sig") as f:
        return yaml.safe_load(f) or {}


def _samenvoegen(basis: dict, extra: dict) -> dict:
    for sleutel, waarde in extra.items():
        if isinstance(waarde, dict) and isinstance(basis.get(sleutel), dict):
            _samenvoegen(basis[sleutel], waarde)
        else:
            basis[sleutel] = waarde
    return basis


def laad_config(bestand: str | Path | None = None) -> dict:
    cfg = _lees(Path(bestand) if bestand else PROJECT_MAP / "config.yaml")
    if bestand is None and LOKAAL.exists():
        _samenvoegen(cfg, _lees(LOKAAL))
    return cfg


def bewaar_lokaal(sectie: str, sleutel: str, waarde) -> None:
    """Zet één instelling in config.lokaal.yaml (de rest van dat bestand blijft behouden)."""
    lokaal = _lees(LOKAAL) if LOKAAL.exists() else {}
    lokaal.setdefault(sectie, {})[sleutel] = waarde
    kop = "# Eigen instellingen; overschrijven config.yaml. Niet in git, dus veilig bij updates.\n"
    LOKAAL.write_text(kop + yaml.safe_dump(lokaal, allow_unicode=True, sort_keys=False),
                      encoding="utf-8")

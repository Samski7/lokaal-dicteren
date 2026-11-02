"""Controle vóór de installatie (enkel standaard-Python, draait nog zonder .venv).

Vangt problemen af die anders pas halverwege de installatie een onduidelijke fout geven.
"""
from __future__ import annotations

import os
import platform
import sys

MAX_MAP = 90  # langste pad in .venv/models is ~150 tekens; Windows-limiet is 260


def lange_paden_aan() -> bool:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\FileSystem") as k:
            return bool(winreg.QueryValueEx(k, "LongPathsEnabled")[0])
    except OSError:
        return False


def main() -> int:
    problemen = []
    if platform.machine().upper() == "ARM64":
        problemen.append(
            "Je gebruikt de ARM-versie van Python (bv. op een Snapdragon-laptop). De spraakmotor\n"
            "  bestaat niet voor ARM. Installeer de 64-bit (x64) versie van Python 3.13 via\n"
            "  https://www.python.org/downloads/windows/ ('Windows installer (64-bit)'); die\n"
            "  werkt ook op ARM-laptops.")
    map_ = os.getcwd()
    if len(map_) > MAX_MAP and not lange_paden_aan():
        problemen.append(
            f"De map is te diep ({len(map_)} tekens): Windows kan dan sommige bestanden niet\n"
            f"  aanmaken (limiet 260 tekens). Verplaats de map, bv. naar C:\\lokaal-dicteren,\n"
            f"  en start installeer.bat daar opnieuw.\n  Huidige map: {map_}")
    if not (3, 11) <= sys.version_info[:2] <= (3, 14):
        problemen.append(f"Python {platform.python_version()} wordt niet ondersteund; "
                         "installeer Python 3.13.")
    for p in problemen:
        print(f"PROBLEEM: {p}\n")
    return 1 if problemen else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Herstelt onderdelen die Windows (Smart App Control) blokkeert, zonder de beveiliging uit te zetten.

Smart App Control laat enkel bestanden toe die Microsoft "kent". Een pakketversie die pas
uitgebracht is, wordt daardoor soms geblokkeerd, terwijl de versie ervoor wel mag. Dit script:

1. zoekt in de Python-omgeving naar .pyd/.dll-bestanden die Windows weigert te laden;
2. installeert voor zo'n pakket de vorige versie(s), tot Windows de bestanden aanvaardt.

Windows blijft elk bestand controleren; we kiezen enkel een versie die het al vertrouwt.

Gebruik (doet installeer.bat automatisch):
    python -m app.windows_blokkade
"""
from __future__ import annotations

import ctypes
import importlib.metadata as md
import re
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

GEBLOKKEERD = 4551  # Windows: "An Application Control policy has blocked this file"
MAX_POGINGEN = 8    # zoveel oudere versies proberen we per pakket
# Getekend door NVIDIA en groot (1 GB+): niet nodig om te controleren.
OVERSLAAN = ("nvidia-",)

UITLEG = (
    "Windows (Smart App Control) blokkeert een onderdeel van de app.\n"
    "Oplossing zonder iets uit te zetten: dubbelklik installeer.bat opnieuw; dat kiest "
    "automatisch een versie die Windows wel vertrouwt."
)


@contextmanager
def leg_uit_bij_blokkade():
    """Rond imports van gecompileerde pakketten: een geblokkeerde DLL wordt een duidelijke
    uitleg in plaats van een traceback."""
    try:
        yield
    except ImportError as e:
        if "DLL load failed" in str(e):
            raise SystemExit(f"\n{UITLEG}\n(technisch: {e})") from e
        raise


def is_geblokkeerd(pad: Path) -> bool:
    """True als Windows weigert dit bestand als programmacode te laden."""
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LoadLibraryExW.restype = ctypes.c_void_p
    kernel32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
    kernel32.FreeLibrary.argtypes = [ctypes.c_void_p]
    # DONT_RESOLVE_DLL_REFERENCES: wordt wel gecontroleerd, maar er draait geen code.
    h = kernel32.LoadLibraryExW(str(pad), None, 0x1)
    if h:
        kernel32.FreeLibrary(h)
        return False
    return ctypes.get_last_error() == GEBLOKKEERD


def geblokkeerde_pakketten() -> dict[str, list[Path]]:
    """{pakketnaam: [geblokkeerde bestanden]} in de huidige Python-omgeving."""
    resultaat: dict[str, list[Path]] = {}
    for dist in md.distributions():
        naam = dist.metadata["Name"] or ""
        if naam.lower().startswith(OVERSLAAN):
            continue
        for f in dist.files or []:
            if f.suffix.lower() not in (".pyd", ".dll"):
                continue
            pad = Path(str(f.locate()))
            if pad.exists() and is_geblokkeerd(pad):
                resultaat.setdefault(naam, []).append(pad)
    return resultaat


def _pip(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "pip", *args], capture_output=True, text=True)


def oudere_versies(naam: str, huidig: str) -> list[str]:
    """Beschikbare versies ouder dan `huidig`, nieuwste eerst."""
    from packaging.version import InvalidVersion, Version

    uit = _pip("index", "versions", naam).stdout
    m = re.search(r"Available versions:\s*(.+)", uit)
    versies = [v.strip() for v in m.group(1).split(",")] if m else []
    try:
        grens = Version(huidig)
        ouder = [v for v in versies if Version(v) < grens and not Version(v).is_prerelease]
    except InvalidVersion:
        return []
    return ouder[:MAX_POGINGEN]


def herstel(naam: str) -> str | None:
    """Probeert oudere versies tot Windows ze aanvaardt. Geeft de gekozen versie of None."""
    huidig = md.version(naam)
    for versie in oudere_versies(naam, huidig):
        print(f"    probeer {naam} {versie}...", flush=True)
        r = _pip("install", "-q", "--no-deps", "--only-binary=:all:", f"{naam}=={versie}")
        if r.returncode != 0:
            continue  # bv. geen versie voor deze Python
        dist = md.distribution(naam)
        bestanden = [Path(str(f.locate())) for f in dist.files or []
                     if f.suffix.lower() in (".pyd", ".dll")]
        if not any(is_geblokkeerd(p) for p in bestanden if p.exists()):
            return versie
    # Niets gevonden: zet de oorspronkelijke versie terug, zodat de omgeving consistent blijft.
    _pip("install", "-q", "--no-deps", f"{naam}=={huidig}")
    return None


def main() -> int:
    if sys.platform != "win32":
        return 0
    print("Controleren of Windows onderdelen blokkeert (Smart App Control)...", flush=True)
    geblokkeerd = geblokkeerde_pakketten()
    if not geblokkeerd:
        print("    OK: niets geblokkeerd.")
        return 0
    mislukt = []
    for naam, bestanden in geblokkeerd.items():
        print(f"    {naam} {md.version(naam)} wordt geblokkeerd ({bestanden[0].name}).")
        versie = herstel(naam)
        if versie:
            print(f"    OK: {naam} {versie} wordt wel vertrouwd door Windows.")
        else:
            mislukt.append(naam)
            print(f"    Geen vertrouwde versie gevonden voor {naam}.")
    if mislukt:
        print("\nWindows blokkeert nog steeds: " + ", ".join(mislukt) + ".\n"
              "Probeer het over een paar dagen opnieuw (Windows leert nieuwe versies kennen),\n"
              "of zie README > Problemen oplossen.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

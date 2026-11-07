"""Nette zinnen (lokaal taalmodel via Ollama) aan- of uitzetten. Optioneel: dicteren werkt ook zonder.

Gebruik (of dubbelklik nette-zinnen-aan.bat / nette-zinnen-uit.bat):
    python -m app.nette_zinnen aan
    python -m app.nette_zinnen uit
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from .config import bewaar_lokaal, laad_config, utf8_console
from .opschonen import ollama_instellingen, ollama_modellen

DOWNLOAD = "https://ollama.com/download"


def zet_llm(aan: bool) -> None:
    """Bewaart de keuze in config.lokaal.yaml, zodat updates van config.yaml ze niet wissen."""
    bewaar_lokaal("opschonen", "llm", aan)


def ollama_bereikbaar(url: str) -> bool:
    try:
        ollama_modellen(url)
        return True
    except Exception:  # noqa: BLE001
        return False


def zoek_ollama() -> str | None:
    standaard = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return shutil.which("ollama") or (str(standaard) if standaard.exists() else None)


def start_ollama(url: str) -> bool:
    """Start de Ollama-server op de achtergrond als die geïnstalleerd is maar niet draait."""
    exe = zoek_ollama()
    if not exe:
        return False
    vlaggen = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=vlaggen)
    for _ in range(30):
        time.sleep(1)
        if ollama_bereikbaar(url):
            return True
    return False


def haal_model(url: str, model: str) -> None:
    """Downloadt het model via de Ollama-API, met voortgang."""
    req = urllib.request.Request(
        f"{url}/api/pull", data=json.dumps({"model": model, "stream": True}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        laatste = -1
        for lijn in r:
            stap = json.loads(lijn)
            if "error" in stap:
                raise RuntimeError(stap["error"])
            totaal, klaar = stap.get("total"), stap.get("completed")
            if totaal and klaar is not None:
                pct = int(klaar * 100 / totaal)
                if pct != laatste and pct % 5 == 0:
                    print(f"\r    downloaden: {pct:3d}% van {totaal / 1e9:.1f} GB", end="", flush=True)
                    laatste = pct
        print()


def aan() -> int:
    cfg = laad_config()
    url, model = ollama_instellingen(cfg)

    print("[1/4] Ollama zoeken...")
    if not ollama_bereikbaar(url):
        if zoek_ollama():
            print("    Ollama is geïnstalleerd maar draait niet: starten...")
            if not start_ollama(url):
                print("    Ollama start niet. Open de Ollama-app via het Startmenu en probeer opnieuw.")
                return 1
        else:
            print("    Ollama is niet geïnstalleerd. Ik open de downloadpagina:")
            print(f"    {DOWNLOAD}")
            print("    Installeer Ollama (gratis) en dubbelklik daarna opnieuw nette-zinnen-aan.bat.")
            webbrowser.open(DOWNLOAD)
            return 1
    print("    OK")

    print(f"[2/4] Taalmodel '{model}' ophalen (eenmalig ~3 GB, kan even duren)...")
    try:
        if model in ollama_modellen(url):
            print("    Al aanwezig.")
        else:
            haal_model(url, model)
    except Exception as e:  # noqa: BLE001
        print(f"    Downloaden mislukt: {e}")
        return 1

    print("[3/4] Testen...")
    cfg.setdefault("opschonen", {})["llm"] = True
    from .opschonen import Opschoner

    o = Opschoner(cfg)
    o.opwarmen()
    if not o.llm_aan:
        return 1
    zin = "Euh ik ga morgen, nee wacht, overmorgen naar de klant."
    start = time.perf_counter()
    uit, info = o.schoon(zin)
    print(f"    \"{zin}\"\n    -> \"{uit}\"  ({time.perf_counter() - start:.1f} s)")

    print("[4/4] Aanzetten (in config.lokaal.yaml)...")
    zet_llm(True)
    print("\nNette zinnen staan aan. Herstart dicteer.bat als dat nog openstaat.")
    print("Uitzetten kan met nette-zinnen-uit.bat.")
    return 0


def uit() -> int:
    zet_llm(False)
    print("Nette zinnen staan uit (opvulwoorden worden wel nog weggefilterd).")
    print("Herstart dicteer.bat als dat nog openstaat.")
    return 0


def main(argv: list[str] | None = None) -> int:
    utf8_console()
    args = argv if argv is not None else sys.argv[1:]
    if args[:1] == ["aan"]:
        return aan()
    if args[:1] == ["uit"]:
        return uit()
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

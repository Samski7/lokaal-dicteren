"""Handmatige test van live dicteren, zonder microfoon: FLEURS-zinnen worden in echte tijd
'ingesproken' en de tekst wordt echt geplakt in een testvenster.

Gebruik (raak muis en toetsenbord niet aan tijdens de test, ~45 s):
    .venv\\Scripts\\python.exe tests\\live_plaktest.py
    .venv\\Scripts\\python.exe tests\\live_plaktest.py --llm          # met nette zinnen
    .venv\\Scripts\\python.exe tests\\live_plaktest.py --wissel       # alsof je van venster wisselde
    .venv\\Scripts\\python.exe tests\\live_plaktest.py --pauze-midden # pauze midden in elke zin
    .venv\\Scripts\\python.exe tests\\live_plaktest.py --droog        # niets plakken: pc blijft vrij

Testdata: python tests/haal_testdata.py
"""
from __future__ import annotations

import argparse
import ctypes
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import dicteer, klembord  # noqa: E402
from app.asr import lees_audio  # noqa: E402
from app.config import laad_config  # noqa: E402

DATA = Path(__file__).parent / "data" / "fleurs_nl"
SR = 16000


def pauze_in_het_midden(audio: np.ndarray, sec: float) -> np.ndarray:
    """Voegt stilte in op het stilste moment tussen 35% en 65% van de zin (tussen twee woorden)."""
    venster = int(0.03 * SR)
    a, b = int(len(audio) * 0.35), int(len(audio) * 0.65)
    energie = np.convolve(audio[a:b] ** 2, np.ones(venster), "valid")
    knip = a + int(np.argmin(energie)) + venster // 2
    return np.concatenate([audio[:knip], np.zeros(int(sec * SR), np.float32), audio[knip:]])


class Wachtrij(queue.Queue):
    """Werkwachtrij die meldt wanneer het einde van de opname aan de beurt is: dan zijn alle
    stukken ervoor volledig omgezet en ingevoegd."""

    def __init__(self):
        super().__init__()
        self.einde = threading.Event()

    def get(self, *args, **kwargs):
        item = super().get(*args, **kwargs)
        if item is dicteer.EINDE:
            self.einde.set()
        return item


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model")
    p.add_argument("--llm", action="store_true", help="nette zinnen via Ollama")
    p.add_argument("--wissel", action="store_true", help="doen alsof je van venster wisselde")
    p.add_argument("--pauze-midden", action="store_true", help="pauze van 0,9 s midden in elke zin")
    p.add_argument("--zinnen", type=int, nargs="+", default=[2, 3, 4])
    p.add_argument("--droog", action="store_true",
                   help="niets plakken en geen testvenster: enkel tekst en timing tonen")
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    delen = []
    for i in args.zinnen:
        zin = lees_audio(DATA / f"fleurs_nl_{i:02d}.wav")
        if args.pauze_midden:
            zin = pauze_in_het_midden(zin, 0.9)
        delen += [zin, np.zeros(int(1.2 * SR), np.float32)]
        print("REF:", (DATA / f"fleurs_nl_{i:02d}.txt").read_text(encoding="utf-8").strip())
    audio = np.concatenate(delen)

    cfg = laad_config()
    cfg["opschonen"]["llm"] = args.llm
    d = dicteer.Dicteerder(cfg, args.model)
    d.sr = SR
    d.werk = Wachtrij()
    if args.llm:
        d.opschoner.opwarmen()
    origineel = None
    if not args.droog:  # droog: klembord nooit aanraken
        try:
            origineel = klembord.lees()
        except OSError:
            pass

    geplakt: list[tuple[float, str]] = []
    echte_typ = d.typ
    t_start = 0.0

    def typ(tekst: str) -> None:
        geplakt.append((round(time.monotonic() - t_start, 1), tekst))
        if not args.droog:
            echte_typ(tekst)

    d.typ = typ
    threading.Thread(target=d.verwerk_lus, daemon=True).start()

    root = tk.Tk()
    root.geometry("800x300+50+50")
    txt = tk.Text(root, wrap="word")
    txt.pack(fill="both", expand=True)
    res: dict = {}

    def stappen() -> None:
        nonlocal t_start
        eigen = 0
        if not args.droog:
            root.lift(); root.attributes("-topmost", True); root.focus_force(); txt.focus_set()
            time.sleep(1)
            # Enkel plakken in ons eigen testvenster, nooit in een venster van de gebruiker.
            eigen = ctypes.windll.user32.GetAncestor(root.winfo_id(), 2)  # GA_ROOT
            if dicteer.actief_hwnd() != eigen:
                res["fout"] = "Testvenster kreeg de focus niet (iemand gebruikt de pc?): gestopt."
                root.after(0, root.destroy)
                return
        # Zoals start_opname, maar met de testaudio in plaats van de microfoon.
        d.ruw, d.stop_evt = queue.Queue(), threading.Event()
        d.start_tijd = t_start = time.monotonic()
        d.doelvenster = 1 if args.wissel else eigen  # droog: 0 = geen venstercontrole
        d.gemist = []
        if hasattr(d, "nieuwe_opname"):
            d.nieuwe_opname()
        threading.Thread(target=d._verzamel, args=(d.ruw, d.stop_evt), daemon=True).start()
        for i in range(0, len(audio), 1600):  # blokken van 0,1 s in echte tijd
            d.ruw.put(audio[i:i + 1600]); time.sleep(0.1)
        res["spreekduur"] = time.monotonic() - t_start
        d.stop_evt.set()
        d.werk.einde.wait(120)  # alle stukken van deze opname verwerkt
        time.sleep(0.5)          # het slotpunt komt net na het laatste stuk
        res["tekst"] = txt.get("1.0", "end").strip()
        try:
            res["klembord"] = klembord.lees()
        except OSError:
            res["klembord"] = "(bezet)"
        root.after(0, root.destroy)

    def veilig() -> None:
        try:
            stappen()
        except Exception:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            root.after(0, root.destroy)

    threading.Thread(target=veilig, daemon=True).start()
    if args.droog:
        root.withdraw()
    root.mainloop()
    if "fout" in res:
        print(res["fout"])
        return 1
    if origineel is not None:
        klembord.schrijf(origineel)

    print(f"\nSpreekduur {res.get('spreekduur', 0):.1f} s. Geplakt (seconden na start):")
    for t, tekst in geplakt:
        print(f"  {t:5.1f} s  {tekst}")
    if geplakt:
        print(f"Laatste tekst {geplakt[-1][0] - res['spreekduur']:.1f} s na einde spreken")
    print("TEKSTVAK:", res.get("tekst"))
    if args.wissel:
        print("KLEMBORD:", res.get("klembord"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Dicteren op deze pc: sneltoets -> inspreken -> sneltoets -> tekst bij je cursor.

Starten:
    python -m app.dicteer            (of dubbelklik dicteer.bat)

Werkt in elk programma (Word, Outlook, browser, ...): de tekst wordt geplakt in het venster
dat de focus heeft. In live-modus verschijnt de tekst al per pauze terwijl je verder spreekt.
Audio komt nooit op schijf.
"""
from __future__ import annotations

import argparse
import logging
import queue
import sys
import threading
import time

import av
import numpy as np
import sounddevice as sd
from faster_whisper.vad import VadOptions, get_speech_timestamps
from pynput import keyboard

from .config import laad_config

log = logging.getLogger("dicteer")
SR = 16000  # wat de spraakmodellen verwachten


def piep(hoog: bool) -> None:
    """Kort geluidje als feedback (start = hoog, stop = laag)."""
    try:
        import winsound

        winsound.Beep(880 if hoog else 520, 120)
    except Exception:  # noqa: BLE001 - geen geluid is geen ramp
        pass


def actief_hwnd() -> int:
    """Handle van het venster dat nu de focus heeft."""
    try:
        import ctypes

        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:  # noqa: BLE001
        return 0


def actief_venster() -> str:
    """Titel van het venster dat nu de focus heeft (waar de tekst naartoe gaat)."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        return buf.value or "(naamloos venster)"
    except Exception:  # noqa: BLE001 - enkel informatief
        return "?"


_MUTEX = None  # blijft open zolang dit programma draait


def al_actief() -> bool:
    """True als er al een dicteervenster draait (anders plakt alles dubbel)."""
    global _MUTEX
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        _MUTEX = kernel32.CreateMutexW(None, False, "Local\\SpraakNaarTekst_Dicteren")
        return ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    except Exception:  # noqa: BLE001 - niet-Windows: geen controle
        return False


def naar_16khz(samples: np.ndarray, sr: int) -> np.ndarray:
    """Hersamplet mono float32 naar 16 kHz met de resampler van FFmpeg (via PyAV)."""
    if sr == SR or not len(samples):
        return samples
    frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="flt", layout="mono")
    frame.sample_rate = sr
    resampler = av.AudioResampler(format="flt", layout="mono", rate=SR)
    delen = [f.to_ndarray().reshape(-1) for f in resampler.resample(frame)]
    delen += [f.to_ndarray().reshape(-1) for f in resampler.resample(None)]
    return np.concatenate(delen).astype(np.float32)


class Dicteerder:
    def __init__(self, cfg: dict, model: str | None = None):
        d = cfg.get("dicteren", {})
        self.max_sec = d.get("max_seconden", 300)
        self.spatie_erna = d.get("spatie_erna", True)
        self.invoegen = d.get("invoegen", "plakken")  # plakken (betrouwbaar) of typen
        self.live = d.get("live", True)
        self.pauze_ms = d.get("pauze_ms", 700)
        self.max_stuk = d.get("max_stuk_seconden", 25)
        self.apparaat = d.get("microfoon")  # None = standaardmicrofoon
        info = sd.query_devices(self.apparaat, kind="input")
        self.micnaam = info["name"]
        self.sr = self._kies_samplerate(int(info["default_samplerate"]))

        from .asr import maak_transcriber
        from .opschonen import Opschoner

        self.transcriber = maak_transcriber(cfg, model)
        self.opschonen = cfg.get("opschonen", {}).get("aan", True)
        self.opschoner = Opschoner(cfg)
        self.toetsenbord = keyboard.Controller()
        self.vad = VadOptions(min_silence_duration_ms=self.pauze_ms, speech_pad_ms=150)
        self.stream: sd.InputStream | None = None
        self.stop_evt = threading.Event()
        self.ruw: queue.Queue[np.ndarray] = queue.Queue()
        self.werk: queue.Queue[np.ndarray] = queue.Queue()
        self.doelvenster = 0      # venster waarin je begon te dicteren
        self.gemist: list[str] = []  # tekst die niet geplakt werd omdat je van venster wisselde

    def _kies_samplerate(self, standaard: int) -> int:
        # Liefst meteen 16 kHz (Windows hersamplet dan zelf); anders de standaard van de mic.
        try:
            sd.check_input_settings(device=self.apparaat, samplerate=SR, channels=1)
            return SR
        except Exception:  # noqa: BLE001
            return standaard

    # --- opnemen -----------------------------------------------------------------------
    def wissel(self) -> None:
        """Sneltoets: start of stop de opname."""
        if self.stream is None:
            self.start_opname()
        else:
            self.stop_opname()

    def start_opname(self) -> None:
        self.ruw = queue.Queue()
        self.stop_evt = threading.Event()
        self.start_tijd = time.monotonic()
        self.doelvenster = actief_hwnd()
        self.gemist = []
        self.stream = sd.InputStream(
            samplerate=self.sr, channels=1, dtype="float32", device=self.apparaat,
            callback=lambda indata, *_: self.ruw.put(indata[:, 0].copy()),
        )
        self.stream.start()
        threading.Thread(target=self._verzamel, args=(self.ruw, self.stop_evt), daemon=True).start()
        piep(True)
        modus = "live: tekst verschijnt per pauze" if self.live else "tekst komt na het stoppen"
        print(f"● Opnemen ({modus}). Druk opnieuw op de sneltoets om te stoppen.")

    def stop_opname(self) -> None:
        stream, self.stream = self.stream, None
        if stream is None:
            return
        stream.stop()
        stream.close()
        self.stop_evt.set()
        piep(False)
        print(f"■ Gestopt na {time.monotonic() - self.start_tijd:.0f} s.")

    def _verzamel(self, ruw: queue.Queue, stop_evt: threading.Event) -> None:
        """Verzamelt de audio en knipt hem (in live-modus) op pauzes in stukken."""
        buf = np.zeros(0, dtype=np.float32)
        while True:
            gestopt = stop_evt.wait(0.25)
            blokken = []
            while not ruw.empty():
                blokken.append(ruw.get_nowait())
            if blokken:
                buf = np.concatenate([buf, naar_16khz(np.concatenate(blokken), self.sr)])
            if gestopt:
                break
            if self.live:
                buf = self._knip(buf)
            if time.monotonic() - self.start_tijd > self.max_sec:
                print("  Maximale opnameduur bereikt.")
                threading.Thread(target=self.stop_opname, daemon=True).start()
        # Restant na het stoppen: enkel doorsturen als er spraak in zit.
        if len(buf) > SR // 2 and get_speech_timestamps(buf, self.vad):
            self.werk.put(buf)
        elif not self.live:
            print("  Geen spraak gehoord.")

    def _knip(self, buf: np.ndarray) -> np.ndarray:
        """Stuurt afgeronde spraakstukken naar de verwerking; geeft de rest terug."""
        if len(buf) < SR:
            return buf
        stukken = get_speech_timestamps(buf, self.vad)
        if not stukken:
            # Enkel stilte: niet eindeloos bijhouden.
            return buf[-SR:] if len(buf) > 5 * SR else buf
        eind = stukken[-1]["end"]
        if len(buf) - eind >= self.pauze_ms * SR // 1000:
            knip = min(len(buf), eind + int(0.15 * SR))
        elif len(buf) > self.max_stuk * SR and len(stukken) > 1:
            knip = stukken[-1]["start"]  # vóór het lopende stuk spraak knippen
        else:
            return buf
        self.werk.put(buf[:knip])
        return buf[knip:]

    # --- omzetten en invoegen ----------------------------------------------------------
    def verwerk_lus(self) -> None:
        while True:
            stuk = self.werk.get()
            try:
                t = self.transcriber.transcribeer(stuk)
                if not t.tekst:
                    continue
                tekst, info = self.opschoner.schoon(t.tekst) if self.opschonen else (t.tekst, {})
                if not tekst:
                    continue
                llm = f" + opschonen {info['llm_sec']:.1f} s" if info.get("llm") else ""
                print(f"  ✓ ({t.duur_audio:.0f} s audio, {t.duur_verwerking:.1f} s{llm}) {tekst}")
                if self.doelvenster and actief_hwnd() != self.doelvenster:
                    # Niet in een ander programma plakken dan waar je begon: klembord.
                    from . import klembord

                    self.gemist.append(tekst)
                    klembord.schrijf(" ".join(self.gemist))
                    piep(False)
                    print(f"    ! Ander venster actief ({actief_venster()}): niet geplakt. "
                          "De tekst staat op het klembord (Ctrl+V).")
                    continue
                print(f"    → in: {actief_venster()}")
                self.typ(tekst)
            except Exception as e:  # noqa: BLE001 - blijf luisteren, ook na een fout
                log.exception("Fout bij omzetten: %s", e)

    def typ(self, tekst: str) -> None:
        tekst += " " if self.spatie_erna else ""
        if self.invoegen == "typen":
            self.toetsenbord.type(tekst)
        else:
            self.plak(tekst)

    def plak(self, tekst: str) -> None:
        """Zet de tekst op het klembord, plakt met Ctrl+V en zet het oude klembord terug.

        Letter per letter typen verliest in sommige programma's toetsen; plakken voegt alles
        in één keer in.
        """
        from . import klembord

        vorige = klembord.lees()
        klembord.schrijf(tekst)
        with self.toetsenbord.pressed(keyboard.Key.ctrl):
            self.toetsenbord.tap("v")
        # Het doelprogramma leest het klembord asynchroon: even wachten voor we terugzetten.
        time.sleep(0.5)
        if vorige is not None:
            klembord.schrijf(vorige)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Dicteren: tekst verschijnt bij je cursor")
    p.add_argument("--sneltoets", help="bv. '<ctrl>+<shift>+<space>' (overschrijft config.yaml)")
    p.add_argument("--model", help="spraakmodel (overschrijft config.yaml)")
    p.add_argument("--microfoons", action="store_true", help="toon beschikbare microfoons")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.microfoons:
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                print(f"{i:3d}  {dev['name']}")
        return 0

    if al_actief():
        print("Er draait al een dicteervenster. Sluit dat eerst (anders wordt alles twee keer")
        print("geplakt) en start dit daarna opnieuw.")
        return 1

    cfg = laad_config()
    d_cfg = cfg.get("dicteren", {})
    sneltoets = args.sneltoets or d_cfg.get("sneltoets", "<ctrl>+<shift>+<space>")
    model = args.model or d_cfg.get("model")

    print("Modellen laden...")
    d = Dicteerder(cfg, model)
    threading.Thread(target=d.verwerk_lus, daemon=True).start()
    threading.Thread(target=d.opschoner.opwarmen, daemon=True).start()

    llm = f" + {d.opschoner.model}" if d.opschonen and d.opschoner.llm_aan else ""
    device = getattr(d.transcriber, "device", "cpu").replace("cuda", "GPU").upper()
    print(f"\nKlaar. Spraakmodel: {d.transcriber.modelnaam} ({device}){llm} | microfoon: {d.micnaam}")
    print(f"Sneltoets: {sneltoets}  (1x = start, nog 1x = stop)"
          f"  | live: {'aan' if d.live else 'uit'}")
    print("Laat dit venster open (mag geminimaliseerd). Stoppen: Ctrl+C of venster sluiten.\n")

    with keyboard.GlobalHotKeys({sneltoets: d.wissel}) as luisteraar:
        try:
            luisteraar.join()
        except KeyboardInterrupt:
            print("Gestopt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

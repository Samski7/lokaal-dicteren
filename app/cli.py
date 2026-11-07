"""CLI: audiobestand(en) -> transcript met tijdsstempels.

Gebruik:
    python -m app.cli opname.m4a [meer.wav ...] [--model medium] [--niet-opslaan]
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from .config import laad_config, pad, utf8_console

AUDIO_EXTENSIES = {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".webm"}


def tijd(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"


def bewaar(transcript, audio: Path, uitvoermap: Path, tekst: str) -> tuple[Path, Path]:
    uitvoermap.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    basis = uitvoermap / f"{audio.stem}_{stempel}"
    txt, js = basis.with_suffix(".txt"), basis.with_suffix(".json")
    txt.write_text(tekst + "\n", encoding="utf-8")
    data = {"bron": audio.name, "aangemaakt": datetime.now().isoformat(timespec="seconds")}
    data.update(transcript.naar_dict())
    if tekst != transcript.tekst:
        data["tekst_ruw"], data["tekst"] = transcript.tekst, tekst
    js.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return txt, js


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Lokale spraak-naar-tekst met faster-whisper")
    p.add_argument("audio", nargs="+", type=Path, help="audiobestand(en): wav/mp3/m4a/ogg")
    p.add_argument("--model", help="Whisper-model (overschrijft config.yaml)")
    p.add_argument("--taal", help="taalcode, bv. nl/en, of 'auto' (overschrijft config.yaml)")
    p.add_argument("--config", help="ander configbestand")
    p.add_argument("--niet-opslaan", action="store_true", help="enkel tonen, geen bestanden")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )
    utf8_console()

    for a in args.audio:
        if not a.exists():
            p.error(f"bestand niet gevonden: {a}")
        if a.suffix.lower() not in AUDIO_EXTENSIES:
            print(f"Let op: onbekende extensie {a.suffix}, ik probeer het toch.", file=sys.stderr)

    cfg = laad_config(args.config)
    if args.taal:
        cfg["whisper"]["taal"] = None if args.taal == "auto" else args.taal
    from .asr import maak_transcriber  # pas hier: laden van de modellen duurt even
    from .opschonen import regels

    opschonen = cfg.get("opschonen", {}).get("aan", True)

    t0 = time.perf_counter()
    transcriber = maak_transcriber(cfg, model=args.model)
    laadtijd = time.perf_counter() - t0
    print(f"Model: {transcriber.modelnaam} (geladen in {laadtijd:.1f} s)")

    for audio in args.audio:
        t = transcriber.transcribeer(audio)
        print(f"\n=== {audio.name} | taal {t.taal} ({t.taal_kans:.0%}) | "
              f"{t.duur_audio:.1f} s audio in {t.duur_verwerking:.1f} s "
              f"(x{t.duur_audio / max(t.duur_verwerking, 0.01):.1f} realtime) ===")
        for s in t.segmenten:
            print(f"[{tijd(s.start)} -> {tijd(s.einde)}] {s.tekst}")
        # Zelfde opkuis als bij dicteren; de segmenten (tijdsstempels) blijven ongewijzigd.
        tekst = regels(t.tekst) if opschonen else t.tekst
        if tekst != t.tekst:
            print(f"\nOpgeschoond: {tekst}")
        if not args.niet_opslaan:
            txt, js = bewaar(t, audio, pad(cfg["paden"]["uitvoer"]), tekst)
            print(f"\nOpgeslagen: {txt}\n            {js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

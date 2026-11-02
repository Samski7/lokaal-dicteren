"""Vergelijkt spraakmodellen op eigen testopnames: foutpercentage (WER) en snelheid.

Testdata: een map met paren  naam.wav (of .m4a/.mp3/...) + naam.txt (wat er echt gezegd is).

Gebruik:
    python eval.py tests/data/fleurs_nl
    python eval.py tests/data --modellen large-v3-turbo onnx:nemo-parakeet-tdt-0.6b-v3

Resultaat in de terminal en in uitvoer/eval_<tijd>.md (+ .json met alle transcripten).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import jiwer

from app.asr import lees_audio, maak_transcriber
from app.config import laad_config, pad

AUDIO = {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".webm"}
STANDAARD_MODELLEN = [
    "large-v3-turbo",
    "onnx:nemo-parakeet-tdt-0.6b-v3",
    "onnx:nemo-canary-1b-v2",
]


def normaliseer(tekst: str) -> str:
    """Kleine letters, geen leestekens/accenten, zodat enkel echte woordfouten tellen."""
    tekst = unicodedata.normalize("NFKD", tekst.lower())
    tekst = "".join(c for c in tekst if not unicodedata.combining(c))
    tekst = re.sub(r"[^\w\s]", " ", tekst)
    return re.sub(r"\s+", " ", tekst).strip()


def zoek_paren(mappen: list[Path]) -> list[tuple[Path, str]]:
    paren = []
    for m in mappen:
        for audio in sorted(m.rglob("*")):
            ref = audio.with_suffix(".txt")
            if audio.suffix.lower() in AUDIO and ref.exists():
                paren.append((audio, ref.read_text(encoding="utf-8").strip()))
    return paren


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("mappen", nargs="*", type=Path, default=[Path("tests/data")])
    p.add_argument("--modellen", nargs="+", default=STANDAARD_MODELLEN)
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    paren = zoek_paren(args.mappen)
    if not paren:
        print("Geen testparen gevonden (naam.wav + naam.txt).")
        return 1
    # Audio één keer decoderen, zodat enkel de modeltijd gemeten wordt.
    audio = {a: lees_audio(a) for a, _ in paren}
    totaal_audio = sum(len(x) for x in audio.values()) / 16000
    print(f"{len(paren)} testopnames, {totaal_audio:.0f} s audio\n")

    cfg = laad_config()
    resultaten = []
    for model in args.modellen:
        print(f"== {model}")
        t0 = time.perf_counter()
        try:
            tr = maak_transcriber(cfg, model)
        except Exception as e:  # noqa: BLE001 - één kapot model mag de rest niet stoppen
            print(f"   overgeslagen: {e}\n")
            continue
        laadtijd = time.perf_counter() - t0
        tr.transcribeer(audio[paren[0][0]][:16000])  # opwarmen (eerste run is trager)

        refs, hyps, per_bestand, verwerking = [], [], [], 0.0
        for a, ref in paren:
            t = tr.transcribeer(audio[a])
            verwerking += t.duur_verwerking
            r, h = normaliseer(ref), normaliseer(t.tekst)
            refs.append(r)
            hyps.append(h)
            per_bestand.append({
                "bestand": str(a), "referentie": ref, "transcript": t.tekst,
                "wer": round(jiwer.wer(r, h) if h else 1.0, 4), "sec": t.duur_verwerking,
            })
        wer = jiwer.wer(refs, hyps)
        res = {
            "model": model, "wer": round(wer, 4), "laadtijd_s": round(laadtijd, 1),
            "verwerking_s": round(verwerking, 1),
            "x_realtime": round(totaal_audio / max(verwerking, 1e-6), 1),
            "per_bestand": per_bestand,
        }
        resultaten.append(res)
        print(f"   WER {wer:.1%} | {verwerking:.0f} s voor {totaal_audio:.0f} s audio "
              f"(x{res['x_realtime']} realtime) | laden {laadtijd:.0f} s\n")
        del tr

    resultaten.sort(key=lambda r: r["wer"])
    regels = [
        f"# Evaluatie {datetime.now():%Y-%m-%d %H:%M}",
        "", f"{len(paren)} opnames, {totaal_audio:.0f} s audio, mappen: "
        + ", ".join(str(m) for m in args.mappen), "",
        "| Model | WER (lager = beter) | Verwerking | Snelheid | Laden |",
        "| --- | --- | --- | --- | --- |",
    ]
    regels += [
        f"| {r['model']} | {r['wer']:.1%} | {r['verwerking_s']:.0f} s | x{r['x_realtime']} "
        f"realtime | {r['laadtijd_s']:.0f} s |" for r in resultaten
    ]
    tabel = "\n".join(regels)
    print(tabel)

    uit = pad(cfg["paden"]["uitvoer"])
    uit.mkdir(parents=True, exist_ok=True)
    stam = uit / f"eval_{datetime.now():%Y%m%d-%H%M%S}"
    stam.with_suffix(".md").write_text(tabel + "\n", encoding="utf-8")
    stam.with_suffix(".json").write_text(
        json.dumps(resultaten, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOpgeslagen: {stam}.md / .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

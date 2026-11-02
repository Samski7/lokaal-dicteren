"""Haalt Nederlandse testopnames + referentietekst op voor eval.py.

Bron: FLEURS (Google), Nederlandse testset, licentie CC BY 4.0
(https://huggingface.co/datasets/google/fleurs). Komt in tests/data/fleurs_nl/.

Gebruik:
    python tests/haal_testdata.py [aantal]   (standaard 15)
"""
import json
import sys
import urllib.request
from pathlib import Path

DOEL = Path(__file__).resolve().parent / "data" / "fleurs_nl"
URL = ("https://datasets-server.huggingface.co/rows?dataset=google/fleurs&config=nl_nl"
       "&split=test&offset=0&length=60")


def get(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def main() -> None:
    aantal = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    DOEL.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in json.loads(get(URL))["rows"]:
        row = r["row"]
        tekst = (row.get("raw_transcription") or "").strip()
        audio = row.get("audio") or []
        if not tekst or not audio or len(tekst.split()) < 8:
            continue  # te korte fragmenten zeggen weinig
        n += 1
        stam = DOEL / f"fleurs_nl_{n:02d}"
        stam.with_suffix(".wav").write_bytes(get(audio[0]["src"]))
        stam.with_suffix(".txt").write_text(tekst + "\n", encoding="utf-8")
        if n >= aantal:
            break
    print(f"{n} testopnames in {DOEL}")


if __name__ == "__main__":
    main()

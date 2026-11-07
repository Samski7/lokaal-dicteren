"""Controle na de installatie: spraakmodel downloaden en testen, microfoon en Ollama nakijken.

Gebruik (doet installeer.bat automatisch):
    python -m app.voorbereiden
"""
from __future__ import annotations

from .config import laad_config, utf8_console
from .opschonen import ollama_instellingen, ollama_modellen


def main() -> int:
    utf8_console()
    cfg = laad_config()
    ok = True

    print("\n[1/3] Spraakmodel laden (en de eerste keer downloaden)...")
    try:
        from .asr import maak_transcriber

        t = maak_transcriber(cfg)
        apparaat = "NVIDIA-GPU" if getattr(t, "device", "cpu") == "cuda" else "CPU"
        print(f"      OK: {t.modelnaam} op {apparaat} ({getattr(t, 'compute_type', '?')})")
        if apparaat == "CPU":
            print("      (Zonder NVIDIA-GPU duurt omzetten ongeveer even lang als de opname.)")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"      FOUT: {e}")

    print("[2/3] Microfoon zoeken...")
    try:
        import sounddevice as sd

        mic = cfg.get("dicteren", {}).get("microfoon")
        print(f"      OK: {sd.query_devices(mic, kind='input')['name']}")
    except Exception as e:  # noqa: BLE001
        ok = False
        print(f"      FOUT: geen microfoon gevonden ({e})")

    print("[3/3] Ollama (nette zinnen, optioneel)...")
    if not cfg.get("opschonen", {}).get("llm", False):
        print("      Staat uit (niet nodig om te dicteren). Aanzetten kan later met "
              "nette-zinnen-aan.bat.")
    else:
        url, model = ollama_instellingen(cfg)
        try:
            if model in ollama_modellen(url):
                print(f"      OK: {model}")
            else:
                print(f"      Ollama draait, maar '{model}' ontbreekt: ollama pull {model}")
        except Exception:  # noqa: BLE001
            print("      Niet gevonden: dicteren werkt, maar zonder nette zinnen. "
                  "Installeer Ollama via https://ollama.com voor die extra stap.")

    print("\nAlles klaar: start dicteer.bat." if ok else
          "\nEr ging iets mis (zie FOUT hierboven). Zie README > Problemen oplossen.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

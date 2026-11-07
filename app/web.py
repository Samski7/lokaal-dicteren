"""Web-UI: opnemen of uploaden in de browser, transcript terug. Volledig lokaal.

Starten:
    python -m app.web            # HTTPS op poort 8443 (microfoon werkt ook op gsm)
    python -m app.web --http     # enkel HTTP (microfoon dan alleen op localhost)
"""
from __future__ import annotations

import argparse
import logging
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from .config import PROJECT_MAP, laad_config, pad, utf8_console
from .opschonen import regels
from .reclame import toon as toon_maker

log = logging.getLogger("spraak")
STATIC = Path(__file__).parent / "static"
MAX_UPLOAD_MB = 100

cfg = laad_config()
staat: dict = {}
# Eén transcriptie tegelijk: de CPU is toch volledig bezet, en zo blijft het geheugen beperkt.
model_slot = threading.Lock()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from .asr import maak_transcriber

    staat["transcriber"] = await run_in_threadpool(maak_transcriber, cfg)
    log.info("Model klaar: %s", staat["transcriber"].modelnaam)
    yield


app = FastAPI(title="Spraak naar tekst", lifespan=lifespan, docs_url=None, redoc_url=None)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    t = staat.get("transcriber")
    return {
        "klaar": t is not None,
        "model": t.modelnaam if t else None,
        "taal": cfg["whisper"].get("taal"),
        "bezig": model_slot.locked(),
    }


def _transcribeer(bestand: Path):
    with model_slot:
        return staat["transcriber"].transcribeer(bestand)


@app.post("/api/transcribeer")
async def transcribeer(audio: UploadFile):
    if "transcriber" not in staat:
        raise HTTPException(503, "Model is nog aan het laden")

    uploadmap = pad(cfg["paden"].get("uploads", "uploads"))
    uploadmap.mkdir(parents=True, exist_ok=True)
    suffix = Path(audio.filename or "opname").suffix.lower()[:8] or ".audio"
    with tempfile.NamedTemporaryFile(dir=uploadmap, suffix=suffix, delete=False) as tmp:
        doel = Path(tmp.name)
        grootte = 0
        while blok := await audio.read(1024 * 1024):
            grootte += len(blok)
            if grootte > MAX_UPLOAD_MB * 1024 * 1024:
                tmp.close()
                doel.unlink(missing_ok=True)
                raise HTTPException(413, f"Bestand groter dan {MAX_UPLOAD_MB} MB")
            tmp.write(blok)

    try:
        t = await run_in_threadpool(_transcribeer, doel)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    finally:
        if not cfg.get("audio_bewaren", False):
            doel.unlink(missing_ok=True)

    data = t.naar_dict()
    if cfg.get("opschonen", {}).get("aan", True):  # zelfde opkuis als bij dicteren
        data["tekst_ruw"], data["tekst"] = t.tekst, regels(t.tekst)
    data["bron"] = audio.filename
    data["audio_bewaard"] = bool(cfg.get("audio_bewaren", False))
    return data


def main() -> None:
    import uvicorn

    from .certificaat import lan_ips, zorg_voor_certificaat

    p = argparse.ArgumentParser(description="Web-UI voor lokale spraak-naar-tekst")
    p.add_argument("--host", default=cfg.get("web", {}).get("host", "0.0.0.0"))
    p.add_argument("--poort", type=int, default=cfg.get("web", {}).get("poort", 8443))
    p.add_argument("--http", action="store_true", help="zonder HTTPS")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    utf8_console()
    ssl = {}
    schema = "http"
    if not args.http:
        cert, key = zorg_voor_certificaat(PROJECT_MAP / "certs")
        ssl = {"ssl_certfile": str(cert), "ssl_keyfile": str(key)}
        schema = "https"

    print()
    toon_maker()
    print("Spraak naar tekst - open in je browser:")
    print(f"  deze pc : {schema}://localhost:{args.poort}")
    if args.host == "0.0.0.0":
        for ip in lan_ips():
            print(f"  gsm/LAN : {schema}://{ip}:{args.poort}")
    if ssl:
        print("  (eerste keer: certificaatwaarschuwing aanvaarden, het is je eigen pc)")
    print("Het model laadt nu; dat duurt enkele seconden.\n")

    uvicorn.run(app, host=args.host, port=args.poort, log_level="warning", **ssl)


if __name__ == "__main__":
    main()

"""Spraakherkenning, volledig lokaal: faster-whisper of onnx-asr, op GPU (CUDA) of CPU."""
from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Windows zonder Developer Mode kent geen symlinks; de cache werkt toch, dus geen waarschuwing.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from .gpu import kies_compute_type, kies_device, registreer_cuda  # noqa: E402
from .windows_blokkade import leg_uit_bij_blokkade  # noqa: E402

registreer_cuda()  # vóór ctranslate2/onnxruntime laden

with leg_uit_bij_blokkade():  # meestal: Smart App Control blokkeert een onderdeel
    import av
    import numpy as np
    from faster_whisper import WhisperModel

from .config import pad  # noqa: E402

try:  # geen Engelstalige waarschuwingen (bv. over HF_TOKEN) tijdens de eenmalige download
    from huggingface_hub.utils import logging as _hf_logging

    _hf_logging.set_verbosity_error()
except Exception:  # noqa: BLE001
    pass

log = logging.getLogger(__name__)

# Whisper gebruikt maximaal de helft van zijn context (448) voor de prompt.
MAX_PROMPT_TOKENS = 223


@dataclass
class Segment:
    start: float
    einde: float
    tekst: str


@dataclass
class Transcript:
    tekst: str
    segmenten: list[Segment]
    taal: str
    taal_kans: float
    duur_audio: float
    duur_verwerking: float
    model: str
    initial_prompt: str = ""
    extra: dict = field(default_factory=dict)

    def naar_dict(self) -> dict:
        return asdict(self)


def lees_audio(bestand: str | Path, sampling_rate: int = 16000) -> np.ndarray:
    """Decodeert een audiobestand naar mono float32 op 16 kHz, zoals Whisper verwacht.

    We doen dit zelf (i.p.v. faster-whisper's decode_audio) zodat we niet vastzitten
    aan één PyAV-versie.
    """
    resampler = av.AudioResampler(format="s16", layout="mono", rate=sampling_rate)
    stukken: list[np.ndarray] = []
    try:
        with av.open(str(bestand), mode="r") as container:
            if not container.streams.audio:
                raise ValueError("bestand bevat geen audiospoor")
            for frame in container.decode(container.streams.audio[0]):
                stukken.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(frame))
            stukken.extend(f.to_ndarray().reshape(-1) for f in resampler.resample(None))
    except av.FFmpegError as e:
        reden = getattr(e, "strerror", None) or type(e).__name__
        raise ValueError(f"audio kan niet gelezen worden ({reden})") from e
    if not stukken:
        raise ValueError("bestand bevat geen audio")
    return np.concatenate(stukken).astype(np.float32) / 32768.0


def lees_vocabulaire(bestand: Path) -> str:
    """Leest vocabulaire.txt (één term per lijn of komma-gescheiden, # = commentaar)."""
    if not bestand.exists():
        return ""
    termen: list[str] = []
    for lijn in bestand.read_text(encoding="utf-8-sig").splitlines():  # -sig: Kladblok-BOM
        lijn = lijn.strip()
        if not lijn or lijn.startswith("#"):
            continue
        termen.extend(t.strip() for t in lijn.split(",") if t.strip())
    return ", ".join(termen)


def _model_ontbreekt(fout: Exception) -> bool:
    """True als de fout betekent dat het model nog niet gedownload is (huggingface_hub)."""
    tekst = f"{type(fout).__name__} {fout}".lower()
    return any(s in tekst for s in ("localentrynotfound", "snapshot", "local_files_only",
                                    "outgoing traffic has been disabled", "not found"))


class Transcriber:
    def __init__(self, cfg: dict, model: str | None = None):
        w = cfg["whisper"]
        self.cfg = w
        self.device = kies_device(w.get("device"))
        naam = model or w["model"]
        try:
            self.modelnaam, self.model = self._laad(naam, w.get("fallback_model"))
            if self.device == "cuda":
                self._test_gpu()
        except Exception as e:  # noqa: BLE001 - GPU-problemen mogen de app niet blokkeren
            if self.device == "cpu":
                raise
            print(f"GPU werkt niet ({e}); de app gebruikt de CPU (trager).")
            self.device = "cpu"
            self.modelnaam, self.model = self._laad(naam, w.get("fallback_model"))
        vocab = lees_vocabulaire(pad(cfg["paden"]["vocabulaire"]))
        # Whisper neemt de stijl van de prompt over: een zin met hoofdletters en leestekens
        # vooraan zorgt dat het transcript ook leestekens krijgt.
        inleiding = w.get("prompt_inleiding", "")
        prompt = f"{inleiding} {vocab}." if inleiding and vocab else (inleiding or vocab)
        self.initial_prompt = self._kort_in(prompt)

    def _laad(self, naam: str, fallback: str | None) -> tuple[str, WhisperModel]:
        kandidaten = [naam] + ([fallback] if fallback and fallback != naam else [])
        self.compute_type = kies_compute_type(self.device, self.cfg.get("compute_type", "auto"))
        laatste_fout = None
        for kandidaat in kandidaten:
            # Eerst enkel lokaal (geen netwerk); alleen downloaden als het model er nog niet is.
            try:
                return kandidaat, self._maak_model(kandidaat, lokaal=True)
            except Exception as e:  # noqa: BLE001
                if not _model_ontbreekt(e):
                    if self.device == "cuda":
                        raise  # GPU-fout: downloaden helpt niet, de aanroeper valt terug op CPU
                    log.warning("Model %s laadt niet: %s", kandidaat, e)  # bv. tikfout in naam
                    laatste_fout = e
                    continue
                log.info("Model %s nog niet lokaal aanwezig", kandidaat)
            print(f"Spraakmodel '{kandidaat}' wordt eenmalig gedownload "
                  "(large-v3-turbo: ~1,6 GB). Dit kan enkele minuten duren...", flush=True)
            try:
                return kandidaat, self._maak_model(kandidaat, lokaal=False)
            except Exception as e:  # noqa: BLE001 - probeer het reservemodel
                log.warning("Model %s laadt niet: %s", kandidaat, e)
                laatste_fout = e
        raise RuntimeError(f"Geen enkel Whisper-model kon laden: {laatste_fout}")

    def _maak_model(self, naam: str, lokaal: bool) -> WhisperModel:
        log.info("Whisper-model laden: %s (%s, %s, lokaal=%s)",
                 naam, self.device, self.compute_type, lokaal)
        return WhisperModel(
            naam,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cfg.get("cpu_threads", 0),
            download_root=str(pad(self.cfg.get("model_map", "models"))),
            local_files_only=lokaal,
        )

    def _test_gpu(self) -> None:
        """Eén seconde stilte omzetten: CUDA/cuDNN-problemen komen pas hier aan het licht."""
        segmenten, _ = self.model.transcribe(
            np.zeros(16000, dtype=np.float32), language="nl", beam_size=1, vad_filter=False)
        list(segmenten)

    def _kort_in(self, tekst: str) -> str:
        """Kort de prompt in tot de tokenlimiet; de eerste termen blijven behouden."""
        if not tekst:
            return ""
        tok = self.model.hf_tokenizer
        ids = tok.encode(" " + tekst, add_special_tokens=False).ids
        if len(ids) <= MAX_PROMPT_TOKENS:
            return tekst
        ingekort = tok.decode(ids[:MAX_PROMPT_TOKENS]).strip()
        # Niet midden in een term afbreken.
        ingekort = ingekort.rsplit(",", 1)[0] if "," in ingekort else ingekort
        log.warning("Vocabulaire ingekort van %d tot %d tokens", len(ids), MAX_PROMPT_TOKENS)
        return ingekort

    def transcribeer(self, audio: str | Path) -> Transcript:
        start = time.perf_counter()
        samples = lees_audio(audio) if isinstance(audio, (str, Path)) else audio
        segmenten_iter, info = self.model.transcribe(
            samples,
            language=self.cfg.get("taal") or None,
            beam_size=self.cfg.get("beam_size", 5),
            vad_filter=self.cfg.get("vad_filter", True),
            initial_prompt=self.initial_prompt or None,
        )
        # De segmenten worden pas hier (lui) berekend.
        segmenten = [
            Segment(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segmenten_iter
        ]
        return Transcript(
            tekst=" ".join(s.tekst for s in segmenten).strip(),
            segmenten=segmenten,
            taal=info.language,
            taal_kans=round(info.language_probability, 3),
            duur_audio=round(info.duration, 2),
            duur_verwerking=round(time.perf_counter() - start, 2),
            model=self.modelnaam,
            initial_prompt=self.initial_prompt,
        )


class OnnxTranscriber:
    """Andere spraakmodellen via onnx-asr (bv. NVIDIA Parakeet/Canary), ook lokaal op CPU.

    Modelnaam in config: "onnx:nemo-parakeet-tdt-0.6b-v3". Deze modellen kennen geen
    initial_prompt, dus vocabulaire.txt wordt hier niet gebruikt.
    """

    def __init__(self, cfg: dict, naam: str):
        try:
            import onnx_asr
        except ImportError as e:
            raise RuntimeError(
                "onnx-asr is niet geïnstalleerd: pip install -r requirements-extra.txt") from e

        self.device = "cpu"
        w = cfg["whisper"]
        self.cfg = w
        self.modelnaam = naam
        self.initial_prompt = ""
        onnx_naam = naam.removeprefix("onnx:")
        model = onnx_asr.load_model(onnx_naam, quantization=w.get("onnx_quantization", "int8"))
        # VAD knipt lange opnames in stukken; de modellen aanvaarden max. ~20-30 s per keer.
        self.model = model.with_vad(onnx_asr.load_vad("silero"))
        self.extra = {"language": w.get("taal") or "nl"} if "canary" in onnx_naam else {}

    def transcribeer(self, audio) -> Transcript:
        start = time.perf_counter()
        samples = lees_audio(audio) if isinstance(audio, (str, Path)) else audio
        resultaten = self.model.recognize(samples, sample_rate=16000, **self.extra)
        segmenten = [
            Segment(round(r.start, 2), round(r.end, 2), r.text.strip())
            for r in resultaten if r.text.strip()
        ]
        return Transcript(
            tekst=" ".join(s.tekst for s in segmenten).strip(),
            segmenten=segmenten,
            taal=self.cfg.get("taal") or "?",
            taal_kans=1.0,
            duur_audio=round(len(samples) / 16000, 2),
            duur_verwerking=round(time.perf_counter() - start, 2),
            model=self.modelnaam,
        )


def maak_transcriber(cfg: dict, model: str | None = None):
    """Kiest de juiste backend: "onnx:..." -> onnx-asr, anders faster-whisper."""
    naam = model or cfg["whisper"]["model"]
    if naam.startswith("onnx:"):
        return OnnxTranscriber(cfg, naam)
    return Transcriber(cfg, model=naam)

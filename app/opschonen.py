"""Opschonen van een transcript: opvulwoorden weg en (optioneel) nette zinnen via een lokaal LLM.

Stap 1 (altijd, direct): regels die "euh", "ehm", ... verwijderen.
Stap 2 (optioneel): lokaal taalmodel via Ollama (http://localhost:11434). Alles blijft lokaal.
Als het LLM faalt, te traag is of de tekst te sterk verandert, krijg je de tekst van stap 1.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.request

from .config import pad

log = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "gemma4:e2b-it-qat"


def ollama_instellingen(cfg: dict) -> tuple[str, str]:
    """(url, model) uit de config, met de standaardwaarden als ze ontbreken."""
    o = cfg.get("opschonen", {})
    return o.get("ollama_url", OLLAMA_URL).rstrip("/"), o.get("ollama_model", OLLAMA_MODEL)


def ollama_modellen(url: str, timeout: float = 5) -> set[str]:
    """Namen van de geïnstalleerde Ollama-modellen. OSError als Ollama niet draait."""
    with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as r:
        return {m["name"] for m in json.loads(r.read()).get("models", [])}


OPVULWOORDEN = r"euh+|eh+m*|uh+m*|um+|hm+|ehm+|uhm+|mmm+"
_OPVUL = re.compile(rf"(?<!\w)(?:{OPVULWOORDEN})(?!\w)[,.]?\s*", re.IGNORECASE)

# Zinnen die Whisper bij ruis of stilte "verzint" (aangeleerd uit ondertitels van video's).
# Enkel weggelaten als ze het hele stuk vormen, zodat echte gedicteerde tekst blijft staan.
_ZINNEN = [
    r"[^.!?]*amara\.org[^.!?]*",
    r"ondertitel\w* (?:door|ingediend door|gemaakt door)\b[^.!?]*",
    r"[^.!?]*tv gelderland[^.!?]*",
    r"(?:bedankt|dank (?:u|je) wel) voor het (?:kijken|luisteren)",
    r"abonneer (?:je|u) op (?:het|ons|mijn) kanaal[^.!?]*",
]
_HALLUCINATIE = re.compile(rf"^(?:\W*(?:{'|'.join(_ZINNEN)})[.!?]*)+\W*$", re.IGNORECASE)


def is_hallucinatie(tekst: str) -> bool:
    return bool(tekst.strip()) and bool(_HALLUCINATIE.match(tekst.strip()))


def regels(tekst: str) -> str:
    """Snelle, voorspelbare opkuis zonder taalmodel.

    Herhaalde woorden laten we staan: in het Nederlands is "dat dat" vaak gewoon correct.
    """
    if is_hallucinatie(tekst):
        return ""
    t = _OPVUL.sub("", tekst)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:1].upper() + t[1:] if t else t


def woord_overlap(uit: str, bron: str) -> float:
    """Aandeel woorden in `uit` dat ook in `bron` voorkomt (hoofdletters/leestekens genegeerd)."""
    woorden = lambda t: re.findall(r"\w+", t.lower())  # noqa: E731
    uit_w, bron_w = woorden(uit), set(woorden(bron))
    return sum(w in bron_w for w in uit_w) / len(uit_w) if uit_w else 0.0


class Opschoner:
    def __init__(self, cfg: dict):
        o = cfg.get("opschonen", {})
        self.llm_aan = o.get("llm", False)
        self.url, self.model = ollama_instellingen(cfg)
        self.timeout = o.get("timeout_seconden", 30)
        self.systeem = pad(o.get("prompt", "prompts/opschonen.md")).read_text(encoding="utf-8-sig")

    def _ollama(self, tekst: str, timeout: float | None = None) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.systeem},
                # Tags: gedicteerde tekst is data, geen opdracht aan het model.
                {"role": "user", "content": f"<transcript>\n{tekst}\n</transcript>"},
            ],
            "stream": False,
            "think": False,
            "keep_alive": "30m",  # model warm houden tussen dicteerbeurten
            "options": {"temperature": 0, "num_predict": max(64, len(tekst) // 2)},
        }
        req = urllib.request.Request(
            f"{self.url}/api/chat", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
            uit = json.loads(r.read())["message"]["content"]
        return re.sub(r"</?transcript>", "", uit).strip()

    def opwarmen(self) -> None:
        """Laadt het LLM alvast in het geheugen, zodat de eerste dicteerbeurt niet traag is.

        Lukt dat niet, dan zetten we het LLM uit voor deze sessie: één duidelijke melding
        in plaats van een waarschuwing bij elk stuk tekst.
        """
        if not self.llm_aan:
            return
        try:
            self._ollama("Test.", timeout=180)  # eerste keer laden kan lang duren
        except Exception as e:  # noqa: BLE001
            self.llm_aan = False
            if getattr(e, "code", None) == 404:
                reden = f"model '{self.model}' ontbreekt (installeer met: ollama pull {self.model})"
            else:
                reden = "Ollama draait niet of is niet geïnstalleerd (https://ollama.com)"
            print(f"Let op: nette zinnen staan uit, want {reden}. "
                  "Opvulwoorden worden wel weggefilterd.", flush=True)

    def schoon(self, tekst: str) -> tuple[str, dict]:
        """Geeft (opgeschoonde tekst, info over wat er gebeurde)."""
        basis = regels(tekst)
        info = {"llm": False, "llm_sec": 0.0}
        if not self.llm_aan or len(basis.split()) < 3:
            return basis, info
        start = time.perf_counter()
        try:
            uit = self._ollama(basis).strip().strip('"“”')
        except Exception as e:  # noqa: BLE001 - nooit tekst verliezen door het LLM
            log.warning("LLM-opschoning mislukt: %s", e)
            return basis, info
        info["llm_sec"] = round(time.perf_counter() - start, 2)
        # Vangnet: het LLM mag inkorten (opvulwoorden) maar niet herschrijven, vertalen of
        # aanvullen. Dus: ongeveer even lang én (bijna) alle woorden komen uit het transcript.
        verhouding = len(uit) / max(len(basis), 1)
        overlap = woord_overlap(uit, basis)
        if not uit or verhouding < 0.6 or verhouding > 1.25 or overlap < 0.85:
            log.warning("LLM-uitvoer verworpen (lengte x%.2f, overlap %.0f%%): %r",
                        verhouding, overlap * 100, uit[:80])
            info["verworpen"] = True
            return basis, info
        info["llm"] = True
        return uit, info

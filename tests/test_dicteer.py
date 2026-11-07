"""Dicteren zonder microfoon en zonder spraakmodel: knippen op pauzes en de verwerking."""
import queue
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from app import dicteer
from app.dicteer import SR, Dicteerder
from app.opschonen import Opschoner


def maak_dicteerder(**extra) -> Dicteerder:
    """Dicteerder met enkel wat _knip en de verwerking nodig hebben (geen mic, geen model)."""
    d = object.__new__(Dicteerder)
    d.sr, d.pauze_ms, d.max_stuk, d.live = SR, 700, 25, True
    d.vad = dicteer.VadOptions(min_silence_duration_ms=d.pauze_ms, speech_pad_ms=150)
    d.werk = queue.Queue()
    d.__dict__.update(extra)
    return d


def stilte(sec: float) -> np.ndarray:
    return np.zeros(int(sec * SR), np.float32)


def stukken(d: Dicteerder) -> list[np.ndarray]:
    uit = []
    while not d.werk.empty():
        uit.append(d.werk.get_nowait())
    return uit


def test_enkel_stilte_wordt_niet_eindeloos_bewaard():
    d = maak_dicteerder()
    rest = d._knip(stilte(6))
    assert not stukken(d) and len(rest) == SR


def test_spraak_met_pauze_wordt_geknipt(spraak):
    d = maak_dicteerder()
    rest = d._knip(np.concatenate([stilte(0.5), spraak, stilte(1.2)]))
    (stuk,) = stukken(d)
    assert len(stuk) >= len(spraak) * 0.8
    assert not dicteer.get_speech_timestamps(rest, d.vad)  # enkel stilte blijft over


def test_lopende_spraak_wacht_op_pauze(spraak):
    d = maak_dicteerder()
    buf = np.concatenate([stilte(0.5), spraak])  # nog geen pauze na de laatste spraak
    assert len(d._knip(buf)) == len(buf)
    assert not stukken(d)


def test_lang_zonder_pauze_toch_knippen(spraak):
    d = maak_dicteerder(max_stuk=5)
    korte_pauze = stilte(0.3)  # te kort om als einde van een stuk te tellen
    buf = np.concatenate([spraak, korte_pauze, spraak, korte_pauze, spraak])
    rest = d._knip(buf)
    (stuk,) = stukken(d)
    assert len(stuk) + len(rest) == len(buf) and len(rest) < len(buf)


# --- verwerking: omzetten, opschonen, plakken --------------------------------------------
class NepTranscriber:
    def __init__(self, teksten):
        self.teksten = list(teksten)

    def transcribeer(self, audio, **_):
        return SimpleNamespace(tekst=self.teksten.pop(0), duur_audio=1.0, duur_verwerking=0.1)


@pytest.fixture
def verwerker(monkeypatch):
    def maak(teksten, venster_wisselt=False):
        d = maak_dicteerder(
            transcriber=NepTranscriber(teksten), opschonen=True,
            opschoner=Opschoner({"opschonen": {"llm": False}}),
            doelvenster=1, gemist=[])
        d.geplakt, d.klembord = [], []
        d.typ = d.geplakt.append
        monkeypatch.setattr(dicteer, "actief_hwnd", lambda: 2 if venster_wisselt else 1)
        monkeypatch.setattr(dicteer, "piep", lambda hoog: None)
        from app import klembord
        monkeypatch.setattr(klembord, "schrijf", d.klembord.append)
        threading.Thread(target=d.verwerk_lus, daemon=True).start()
        for _ in teksten:
            d.werk.put(stilte(1))
        return d
    return maak


def wacht(conditie, sec=5.0):
    einde = time.monotonic() + sec
    while not conditie() and time.monotonic() < einde:
        time.sleep(0.02)
    assert conditie()


def test_verwerking_plakt_opgeschoond_en_in_volgorde(verwerker):
    d = verwerker(["euh Eerste zin.", "Ondertiteling door de Amara.org gemeenschap", "Tweede zin."])
    wacht(lambda: len(d.geplakt) == 2)
    assert d.geplakt == ["Eerste zin.", "Tweede zin."]


def test_ander_venster_naar_klembord(verwerker):
    d = verwerker(["Eerste zin.", "Tweede zin."], venster_wisselt=True)
    wacht(lambda: len(d.klembord) == 2)
    assert not d.geplakt
    assert d.klembord[-1] == "Eerste zin. Tweede zin."

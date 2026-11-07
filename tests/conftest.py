"""Gedeelde hulpmiddelen voor de tests: python -m pytest tests"""
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

FLEURS = PROJECT / "tests" / "data" / "fleurs_nl"


@pytest.fixture
def spraak():
    """Echte Nederlandse spraak (16 kHz) uit FLEURS; overslaan als de testdata ontbreekt."""
    wav = FLEURS / "fleurs_nl_02.wav"
    if not wav.exists():
        pytest.skip("testdata ontbreekt: python tests/haal_testdata.py")
    from app.asr import lees_audio

    return lees_audio(wav)

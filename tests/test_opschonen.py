import pytest

from app import opschonen
from app.opschonen import Opschoner, is_hallucinatie, regels, woord_overlap


@pytest.mark.parametrize("invoer, verwacht", [
    ("euh ik ga morgen, ehm, naar de winkel.", "Ik ga morgen, naar de winkel."),
    ("Uhm dat dat klopt.", "Dat dat klopt."),  # herhaling blijft staan: "dat dat" is correct
    ("Hmm.", ""),
    ("Een euro is geen euh.", "Een euro is geen"),
    ("Europa en humor blijven.", "Europa en humor blijven."),  # geen opvulwoord binnen een woord
])
def test_regels_haalt_opvulwoorden_weg(invoer, verwacht):
    assert regels(invoer) == verwacht


@pytest.mark.parametrize("tekst", [
    "Ondertiteling door de Amara.org gemeenschap",
    "Ondertiteld door TV Gelderland 2021.",
    "Bedankt voor het kijken!",
    "Abonneer je op het kanaal.",
])
def test_spookzinnen_herkend(tekst):
    assert is_hallucinatie(tekst)
    assert regels(tekst) == ""


@pytest.mark.parametrize("tekst", [
    "Abonneer je op de nieuwsbrief van de school.",
    "Bedankt voor het kijken naar mijn offerte, zie bijlage.",
    "Ik keek gisteren naar een video op Amara.org en toen ging ik slapen. Daarna at ik.",
    "",
])
def test_echte_tekst_geen_spookzin(tekst):
    assert not is_hallucinatie(tekst)


@pytest.mark.parametrize("tekst, klein", [
    ("en de interacties", True), ("euh, en dan", True), ("Euh Eerste zin", False),
    ("Ik ga", False), ("2005 was", False), ("", False),
])
def test_begint_klein(tekst, klein):
    assert opschonen.begint_klein(tekst) is klein


@pytest.mark.parametrize("tekst, door", [
    ("En de interacties", True), ("de bewegingen", True), ("Omdat het regent", True),
    ("Jan zei het", False), ("FBI agenten", False), ("Ik ga", False), ("", False),
])
def test_loopt_door(tekst, door):
    assert opschonen.loopt_door(tekst) is door


def test_woord_overlap():
    assert woord_overlap("Ik ga morgen.", "ik ga morgen") == 1.0
    assert woord_overlap("I am going tomorrow", "ik ga morgen") == 0.0
    assert woord_overlap("", "iets") == 0.0


@pytest.fixture
def opschoner(monkeypatch):
    cfg = {"opschonen": {"llm": True}}
    o = Opschoner(cfg)
    o.antwoord = None

    def nep_ollama(tekst, timeout=None):
        if isinstance(o.antwoord, Exception):
            raise o.antwoord
        return o.antwoord(tekst) if callable(o.antwoord) else o.antwoord

    monkeypatch.setattr(o, "_ollama", nep_ollama)
    return o


def test_llm_resultaat_aanvaard(opschoner):
    opschoner.antwoord = "Ik ga morgen naar de klant."
    tekst, info = opschoner.schoon("euh ik ga morgen naar de klant")
    assert tekst == "Ik ga morgen naar de klant." and info["llm"]


@pytest.mark.parametrize("antwoord", [
    "I am going to the customer tomorrow.",              # vertaald
    "Natuurlijk! Hier is je tekst: ik ga morgen naar de klant en daarna nog veel meer.",  # aangevuld
    "Ik ga.",                                             # te kort
    "",
])
def test_llm_resultaat_verworpen(opschoner, antwoord):
    opschoner.antwoord = antwoord
    tekst, info = opschoner.schoon("euh ik ga morgen naar de klant")
    assert tekst == "Ik ga morgen naar de klant" and not info["llm"]


def test_llm_fout_verliest_geen_tekst(opschoner):
    opschoner.antwoord = OSError("Ollama weg")
    assert opschoner.schoon("ik ga morgen naar de klant")[0] == "Ik ga morgen naar de klant"


def test_korte_tekst_zonder_llm(opschoner):
    opschoner.antwoord = AssertionError("mag niet aangeroepen worden")
    assert opschoner.schoon("Ja.")[0] == "Ja."


def test_llm_uit(monkeypatch):
    o = Opschoner({"opschonen": {"llm": False}})
    monkeypatch.setattr(o, "_ollama", lambda *_: pytest.fail("LLM staat uit"))
    assert o.schoon("euh hallo daar allemaal")[0] == "Hallo daar allemaal"


def test_opwarmen_zet_llm_uit_als_ollama_ontbreekt(monkeypatch, capsys):
    o = Opschoner({"opschonen": {"llm": True, "ollama_url": "http://127.0.0.1:9"}})
    o.opwarmen()
    assert not o.llm_aan
    assert "Ollama draait niet" in capsys.readouterr().out


def test_prompt_bestand_gelezen():
    assert "transcript" in Opschoner({}).systeem.lower()
    assert opschonen.OPVULWOORDEN

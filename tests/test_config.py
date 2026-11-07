import yaml

from app import config


def test_standaardconfig_laadt():
    cfg = config.laad_config(config.PROJECT_MAP / "config.yaml")
    assert cfg["whisper"]["model"]
    assert cfg["opschonen"]["llm"] is False  # werkt standaard zonder taalmodel


def test_samenvoegen_diep():
    basis = {"a": {"x": 1, "y": 2}, "b": 1}
    config._samenvoegen(basis, {"a": {"y": 3}, "c": 4})
    assert basis == {"a": {"x": 1, "y": 3}, "b": 1, "c": 4}


def test_lokaal_overschrijft_en_bewaart(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("opschonen:\n  llm: false\n  aan: true\n", encoding="utf-8")
    lokaal = tmp_path / "config.lokaal.yaml"
    # Kladblok bewaart soms met BOM.
    lokaal.write_text("﻿dicteren:\n  pauze_ms: 900\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_MAP", tmp_path)
    monkeypatch.setattr(config, "LOKAAL", lokaal)

    config.bewaar_lokaal("opschonen", "llm", True)
    cfg = config.laad_config()
    assert cfg["opschonen"] == {"llm": True, "aan": True}
    assert cfg["dicteren"]["pauze_ms"] == 900  # bestaande eigen instelling blijft
    assert yaml.safe_load(lokaal.read_text(encoding="utf-8"))["opschonen"]["llm"] is True


def test_pad():
    assert config.pad("models") == config.PROJECT_MAP / "models"
    assert config.pad(str(config.PROJECT_MAP)) == config.PROJECT_MAP

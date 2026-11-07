import sys
import types

import pytest

from app import gpu


@pytest.fixture
def nep_ct2(monkeypatch):
    def zet(ondersteund):
        mod = types.SimpleNamespace(get_supported_compute_types=lambda device: ondersteund)
        monkeypatch.setitem(sys.modules, "ctranslate2", mod)
    return zet


@pytest.mark.parametrize("device, ondersteund, verwacht", [
    ("cuda", {"int8", "int8_float16", "float16", "float32"}, "int8"),
    ("cuda", {"float16", "float32"}, "float16"),   # oudere kaart zonder int8
    ("cuda", {"float32"}, "float32"),
    ("cpu", {"int8", "int8_float32", "float32"}, "int8"),
    ("cpu", set(), "float32"),
])
def test_kies_compute_type(nep_ct2, device, ondersteund, verwacht):
    nep_ct2(ondersteund)
    assert gpu.kies_compute_type(device, "auto") == verwacht


def test_eigen_compute_type_blijft(nep_ct2):
    nep_ct2(set())
    assert gpu.kies_compute_type("cuda", "float16") == "float16"


def test_kies_device():
    assert gpu.kies_device("cpu") == "cpu"
    assert gpu.kies_device("auto") in {"cpu", "cuda"}

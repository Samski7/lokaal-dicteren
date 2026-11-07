import sys

import pytest

from app.windows_blokkade import UITLEG, is_geblokkeerd, leg_uit_bij_blokkade, onthoud_geweigerd


def test_geweigerde_versies_onthouden(tmp_path):
    f = tmp_path / "constraints.lokaal.txt"
    onthoud_geweigerd("ctranslate2", "4.8.4", f)
    onthoud_geweigerd("av", "19.0.2", f)
    onthoud_geweigerd("ctranslate2", "4.8.5", f)
    onthoud_geweigerd("ctranslate2", "4.8.4", f)  # dubbel: één keer bewaren
    regels = [r for r in f.read_text(encoding="utf-8").splitlines() if not r.startswith("#")]
    assert regels == ["av!=19.0.2", "ctranslate2!=4.8.4,!=4.8.5"]


def test_constraintsbestand_geldig_voor_pip(tmp_path):
    from packaging.requirements import Requirement

    f = tmp_path / "c.txt"
    onthoud_geweigerd("ctranslate2", "4.8.4", f)
    onthoud_geweigerd("ctranslate2", "4.8.5", f)
    req = Requirement(f.read_text(encoding="utf-8").splitlines()[1])
    assert "4.8.3" in req.specifier and "4.8.4" not in req.specifier


def test_geblokkeerde_dll_geeft_uitleg():
    with pytest.raises(SystemExit) as fout:
        with leg_uit_bij_blokkade():
            raise ImportError("DLL load failed while importing _ext: blocked")
    assert UITLEG in str(fout.value)


def test_andere_importfout_blijft():
    with pytest.raises(ModuleNotFoundError):
        with leg_uit_bij_blokkade():
            import bestaat_niet_xyz  # noqa: F401


@pytest.mark.skipif(sys.platform != "win32", reason="enkel Windows")
def test_python_dll_niet_geblokkeerd():
    import ctypes.util

    assert not is_geblokkeerd(ctypes.util.find_library("kernel32"))

import sys

import pytest

from app.windows_blokkade import UITLEG, is_geblokkeerd, leg_uit_bij_blokkade


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

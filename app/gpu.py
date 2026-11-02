"""NVIDIA-GPU (CUDA) gebruiken als die er is, anders gewoon de CPU.

De CUDA-bibliotheken komen uit pip-pakketten (nvidia-cublas-cu12, nvidia-cudnn-cu12, ...),
dus een aparte CUDA-installatie is niet nodig. Windows moet die DLL's wel kunnen vinden:
dat regelt registreer_cuda(), en dat moet gebeuren vóór ctranslate2/onnxruntime laden.
"""
from __future__ import annotations

import logging
import os
import sys
from functools import cache
from pathlib import Path

log = logging.getLogger(__name__)


@cache
def registreer_cuda() -> list[str]:
    """Maakt de CUDA-DLL's uit site-packages/nvidia/*/bin vindbaar. Geeft de mappen terug."""
    mappen = []
    for sp in map(Path, sys.path):
        nvidia = sp / "nvidia"
        if nvidia.is_dir():
            mappen += [str(b) for b in nvidia.glob("*/bin") if b.is_dir()]
    for m in mappen:
        os.add_dll_directory(m)
    if mappen:
        # Sommige bibliotheken laden hun afhankelijkheden via PATH, niet via add_dll_directory.
        os.environ["PATH"] = os.pathsep.join(mappen + [os.environ.get("PATH", "")])
    return mappen


@cache
def cuda_beschikbaar() -> bool:
    registreer_cuda()
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception as e:  # noqa: BLE001
        log.info("Geen CUDA: %s", e)
        return False


def kies_device(gewenst: str | None) -> str:
    """'auto' -> 'cuda' als er een NVIDIA-GPU is, anders 'cpu'."""
    gewenst = (gewenst or "auto").lower()
    if gewenst == "auto":
        return "cuda" if cuda_beschikbaar() else "cpu"
    if gewenst == "cuda":
        registreer_cuda()
    return gewenst

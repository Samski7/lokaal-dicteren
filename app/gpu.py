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
    if sys.platform != "win32":
        return []  # Linux vindt de pip-CUDA-bibliotheken zelf; os.add_dll_directory is Windows-only
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


# Voorkeur per apparaat, snelste eerst. int8 ook op de GPU: op een GTX 1650 Ti is float16
# ~3,5x trager dan int8 (gemeten). Oudere NVIDIA-kaarten (vóór Pascal) kennen geen int8.
VOORKEUR = {
    "cuda": ["int8", "int8_float16", "float16", "float32"],
    "cpu": ["int8", "int8_float32", "float32"],
}


def kies_compute_type(device: str, gewenst: str | None = "auto") -> str:
    """'auto' -> de snelste rekenprecisie die dit apparaat echt ondersteunt."""
    if gewenst and gewenst != "auto":
        return gewenst
    try:
        import ctranslate2

        ondersteund = set(ctranslate2.get_supported_compute_types(device))
    except Exception:  # noqa: BLE001
        ondersteund = set()
    for ct in VOORKEUR.get(device, ["float32"]):
        if ct in ondersteund:
            return ct
    return "float32"


def kies_device(gewenst: str | None) -> str:
    """'auto' -> 'cuda' als er een NVIDIA-GPU is, anders 'cpu'."""
    gewenst = (gewenst or "auto").lower()
    if gewenst == "auto":
        return "cuda" if cuda_beschikbaar() else "cpu"
    if gewenst == "cuda":
        registreer_cuda()
    return gewenst

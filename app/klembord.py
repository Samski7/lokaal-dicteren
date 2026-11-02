"""Windows-klembord (alleen tekst) via de Win32-API, zonder extra afhankelijkheden."""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.restype = wintypes.BOOL
user32.GetClipboardData.argtypes = [wintypes.UINT]
user32.GetClipboardData.restype = wintypes.HANDLE
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]


def _open(pogingen: int = 80) -> None:
    # Een ander programma (klembordbeheerder, Extern bureaublad, ...) kan het klembord even
    # vasthouden: tot ~2 s opnieuw proberen.
    for _ in range(pogingen):
        if user32.OpenClipboard(None):
            return
        time.sleep(0.025)
    raise OSError("klembord is bezet")


def lees() -> str | None:
    """Huidige klembordtekst, of None als er geen tekst op staat."""
    _open()
    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return None
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return None
        p = kernel32.GlobalLock(h)
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def schrijf(tekst: str) -> None:
    data = ctypes.create_unicode_buffer(tekst)
    grootte = ctypes.sizeof(data)
    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, grootte)
    if not h:
        raise MemoryError("GlobalAlloc mislukt")
    p = kernel32.GlobalLock(h)
    ctypes.memmove(p, data, grootte)
    kernel32.GlobalUnlock(h)
    _open()
    try:
        user32.EmptyClipboard()
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            raise OSError("SetClipboardData mislukt")
        # Na succes is Windows eigenaar van h: niet vrijgeven.
    finally:
        user32.CloseClipboard()

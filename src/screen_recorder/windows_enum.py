"""Enumerate top-level capturable windows via the Win32 API (ctypes).

We return ``(title, hwnd)`` pairs. Capturing by HWND (the OS window handle) is
far more reliable than matching a title substring: titles can be duplicated or
change at runtime (e.g. browser tabs), whereas the handle is unique and stable
for the lifetime of the window.

We filter to genuine application windows: visible, titled, not cloaked
(hidden virtual-desktop / UWP shell windows), and not tool windows.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

_user32 = ctypes.windll.user32
_dwmapi = ctypes.windll.dwmapi

_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_DWMWA_CLOAKED = 14

_EnumWindowsProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
)


@dataclass(frozen=True)
class WindowEntry:
    title: str
    hwnd: int


def _is_cloaked(hwnd: int) -> bool:
    cloaked = wintypes.DWORD()
    res = _dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd),
        _DWMWA_CLOAKED,
        ctypes.byref(cloaked),
        ctypes.sizeof(cloaked),
    )
    return res == 0 and cloaked.value != 0


def list_windows() -> list[WindowEntry]:
    entries: list[WindowEntry] = []
    seen: set[int] = set()

    def callback(hwnd: int, _lparam: int) -> bool:
        if not _user32.IsWindowVisible(hwnd):
            return True
        # Skip tool windows (palettes, tray helpers).
        ex_style = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        if ex_style & _WS_EX_TOOLWINDOW:
            return True
        # Skip cloaked windows (e.g. UWP apps on other virtual desktops).
        if _is_cloaked(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title and hwnd not in seen:
            seen.add(hwnd)
            entries.append(WindowEntry(title=title, hwnd=int(hwnd)))
        return True

    _user32.EnumWindows(_EnumWindowsProc(callback), 0)
    entries.sort(key=lambda e: e.title.lower())
    return entries

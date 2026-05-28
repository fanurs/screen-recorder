"""Enumerate monitors and reconcile Win32 / windows-capture ordering with Qt.

This is the crux of correct region/monitor capture. Three coordinate systems are
in play:

* **windows-capture** indexes monitors 1-based in EnumDisplayMonitors order and
  reports *physical* pixel sizes.
* **Qt** ``QGuiApplication.screens()`` has its *own* order (primary first) and
  reports *logical* sizes plus a device-pixel ratio.
* The user selects on a Qt screen but we must capture the matching
  windows-capture ``monitor_index``.

We enumerate the Win32 monitors (authoritative for capture indexing) and pair
each with the Qt screen that sits at the same virtual-desktop position, so a
monitor chosen in the UI is the monitor actually recorded.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass

from PySide6.QtGui import QGuiApplication


@dataclass(frozen=True)
class Monitor:
    capture_index: int       # windows-capture monitor_index (1-based)
    label: str
    phys_width: int          # physical pixels (what capture frames are)
    phys_height: int
    is_primary: bool
    qt_screen: object = None  # matching QScreen, or None if unmatched


def _enum_win32_monitors() -> list[tuple[int, int, int, int, bool]]:
    """Return (left, top, width, height, is_primary) in EnumDisplayMonitors order."""
    user32 = ctypes.windll.user32
    results: list[tuple[int, int, int, int, bool]] = []

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    MONITORINFOF_PRIMARY = 1

    cb_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def callback(hmonitor, hdc, lprect, lparam):  # noqa: ANN001
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
        rc = info.rcMonitor
        is_primary = bool(info.dwFlags & MONITORINFOF_PRIMARY)
        results.append((rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top, is_primary))
        return True

    user32.EnumDisplayMonitors(0, 0, cb_type(callback), 0)
    return results


def _match_qt_screen(left: int, top: int, screens=None):  # noqa: ANN001, ANN201
    """Find the QScreen whose physical top-left matches this Win32 monitor.

    ``screens`` defaults to the live Qt screens; it is injectable for testing the
    physical/logical reconciliation that decides which monitor we record.
    """
    if screens is None:
        screens = QGuiApplication.screens()
    for screen in screens:
        geo = screen.geometry()
        ratio = screen.devicePixelRatio()
        phys_left = round(geo.x() * ratio)
        phys_top = round(geo.y() * ratio)
        # Qt logical origin * ratio should match the physical origin; allow slack.
        if abs(phys_left - left) <= 2 and abs(phys_top - top) <= 2:
            return screen
        # Some setups: Qt geometry already in physical-ish coords.
        if geo.x() == left and geo.y() == top:
            return screen
    return None


def list_monitors() -> list[Monitor]:
    monitors: list[Monitor] = []
    win = _enum_win32_monitors()
    for i, (left, top, w, h, is_primary) in enumerate(win, start=1):
        screen = _match_qt_screen(left, top)
        primary_tag = " · primary" if is_primary else ""
        label = f"Monitor {i}: {w}×{h}{primary_tag}"
        monitors.append(
            Monitor(
                capture_index=i,
                label=label,
                phys_width=w,
                phys_height=h,
                is_primary=is_primary,
                qt_screen=screen,
            )
        )
    return monitors

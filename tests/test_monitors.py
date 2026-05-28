"""Tier 1: the Win32<->Qt monitor reconciliation.

This is the logic behind the original "recorded the wrong screen" bug: Win32
monitor order and Qt screen order can differ, and Qt reports logical coords while
Win32 reports physical ones. We must pair them by physical position.
"""

from __future__ import annotations

from screen_recorder.monitors import _match_qt_screen


class FakeScreen:
    def __init__(self, x, y, w, h, ratio):
        self._x, self._y, self._w, self._h, self._ratio = x, y, w, h, ratio

    def geometry(self):
        from PySide6.QtCore import QRect

        return QRect(self._x, self._y, self._w, self._h)

    def devicePixelRatio(self):
        return self._ratio


def test_matches_hidpi_screen_by_physical_origin():
    # Mirrors the user's real setup: a 2560x1600 panel at physical (1920,4),
    # which Qt reports as logical (1920,4) with ratio 1.5; and a primary at (0,0).
    primary = FakeScreen(0, 0, 1920, 1080, 1.0)
    hidpi = FakeScreen(1920, 4, 1707, 1067, 1.5)
    screens = [primary, hidpi]

    # Win32 says monitor 1 sits at physical (1920, 4) -> must match the hidpi one.
    matched = _match_qt_screen(1920, 4, screens=screens)
    assert matched is hidpi

    # Win32 monitor 2 at physical (0,0) -> primary.
    matched2 = _match_qt_screen(0, 0, screens=screens)
    assert matched2 is primary


def test_matches_scaled_origin():
    # A screen at logical (2560,0) with ratio 1.25 -> physical origin 3200.
    scaled = FakeScreen(2560, 0, 1536, 864, 1.25)
    screens = [FakeScreen(0, 0, 2560, 1440, 1.0), scaled]
    assert _match_qt_screen(3200, 0, screens=screens) is scaled


def test_no_match_returns_none():
    screens = [FakeScreen(0, 0, 1920, 1080, 1.0)]
    assert _match_qt_screen(9999, 9999, screens=screens) is None

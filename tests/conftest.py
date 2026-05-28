"""Shared test fixtures.

GUI tests run with Qt's ``offscreen`` platform so no real window appears and no
display is required. pytest-qt's ``qtbot`` fixture manages the QApplication.
"""

from __future__ import annotations

import os

import pytest

# Force headless Qt before any PySide6 import happens in the tests.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def fake_screen():
    """A stand-in QScreen-like object with a fixed geometry and DPR."""
    from PySide6.QtCore import QRect

    class _Screen:
        def __init__(self, x, y, w, h, ratio):
            self._geo = QRect(x, y, w, h)
            self._ratio = ratio

        def geometry(self):
            return self._geo

        def devicePixelRatio(self):
            return self._ratio

    return _Screen

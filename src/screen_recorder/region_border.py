"""Persistent, click-through border drawn around a selected capture region.

The border sits just *outside* the region rectangle. Because we capture by
monitor and then crop to the region, anything outside the region is cropped
away — so this border is visible on screen the whole time (including while
recording) yet never appears in the recorded video.

The region is stored in physical pixels on a specific monitor; we convert back
to that screen's logical Qt coordinates (dividing by its device-pixel ratio and
offsetting by the screen origin) to place the border window.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .processing import Rect

_BORDER = 3  # px thickness of the ring, drawn outside the region


class RegionBorder(QWidget):
    def __init__(self, screen, region_phys: Rect) -> None:  # noqa: ANN001 (QScreen)
        super().__init__()
        self._screen = screen
        self._region = region_phys

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def show_border(self) -> None:
        ratio = self._screen.devicePixelRatio()
        geo = self._screen.geometry()
        # Region (physical, monitor-local) -> logical, screen-global.
        rx = geo.x() + self._region.x / ratio
        ry = geo.y() + self._region.y / ratio
        rw = self._region.width / ratio
        rh = self._region.height / ratio

        b = _BORDER
        # Window encloses the region plus the outside ring.
        win = QRect(round(rx - b), round(ry - b), round(rw + 2 * b), round(rh + 2 * b))
        # Clamp so the ring stays on-screen even if the region hugs an edge.
        self.createWinId()
        handle = self.windowHandle()
        if handle is not None:
            handle.setScreen(self._screen)
        self.setGeometry(win)
        self.show()
        self.raise_()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        # The window is the region inset by _BORDER on every side. The region
        # itself occupies the inner hole [_BORDER, size-_BORDER); we must paint
        # ONLY the surrounding frame so nothing lands on a captured pixel.
        # Use filled rectangles for the four sides (a stroked rect would straddle
        # the boundary and bleed inward).
        c = QColor("#e5484d")
        w, h, b = self.width(), self.height(), _BORDER
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRect(0, 0, w, b)              # top
        p.drawRect(0, h - b, w, b)          # bottom
        p.drawRect(0, 0, b, h)              # left
        p.drawRect(w - b, 0, b, h)          # right

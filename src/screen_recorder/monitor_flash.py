"""Zoom-style monitor number badges.

Briefly shows a large number centered on each physical monitor so the user can
tell which "Monitor 1 / 2 / …" maps to which screen. The badge for the
currently-selected monitor is highlighted.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget


class _Badge(QWidget):
    def __init__(self, screen, number: int, highlighted: bool) -> None:  # noqa: ANN001
        super().__init__()
        self._number = number
        self._highlighted = highlighted
        self._screen = screen
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

    def show_centered(self) -> None:
        geo = self._screen.geometry()
        side = min(geo.width(), geo.height()) // 4
        side = max(120, min(side, 280))
        self.resize(side, side)
        self.createWinId()
        handle = self.windowHandle()
        if handle is not None:
            handle.setScreen(self._screen)
        self.move(
            geo.x() + (geo.width() - side) // 2,
            geo.y() + (geo.height() - side) // 2,
        )
        self.show()
        self.raise_()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)
        bg = QColor("#2f6bd6") if self._highlighted else QColor(20, 22, 28, 235)
        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(rect, 24, 24)

        p.setPen(QColor("#ffffff"))
        f = QFont("Segoe UI", 1, QFont.Weight.Bold)
        f.setPixelSize(int(rect.height() * 0.55))
        p.setFont(f)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(self._number))


class MonitorFlash:
    """Owns a set of badge windows and tears them down after a delay."""

    def __init__(self) -> None:
        self._badges: list[_Badge] = []
        self._timer: QTimer | None = None

    def show(self, monitors, selected_index: int | None = None, duration_ms: int = 1400) -> None:  # noqa: ANN001
        """Flash a number on each monitor. ``monitors`` is a list of objects with
        ``capture_index`` and ``qt_screen``; the monitor whose ``capture_index``
        equals ``selected_index`` is highlighted."""
        self.clear()
        for m in monitors:
            if m.qt_screen is None:
                continue
            badge = _Badge(m.qt_screen, m.capture_index, highlighted=(m.capture_index == selected_index))
            badge.show_centered()
            self._badges.append(badge)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.clear)
        self._timer.start(duration_ms)

    def clear(self) -> None:
        for b in self._badges:
            b.close()
        self._badges = []
        self._timer = None

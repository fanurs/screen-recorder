"""Full-screen overlay for drag-selecting a capture region.

The overlay covers exactly one monitor. The user drags a rectangle; on release we
emit it in that monitor's *physical pixel* coordinates (the space
windows-capture frames use), i.e. logical Qt coords multiplied by the screen's
device-pixel ratio.

Getting the overlay onto the right monitor is the subtle part: ``showFullScreen``
picks the primary screen by default, so we bind the native window handle to the
target screen and place it manually with frameless geometry instead.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QWidget

from .processing import Rect


def logical_rect_to_physical(x: int, y: int, w: int, h: int, ratio: float) -> Rect:
    """Convert a selection in a screen's logical (Qt) pixels to the monitor's
    physical pixels — the coordinate space windows-capture frames use."""
    return Rect(
        x=round(x * ratio),
        y=round(y * ratio),
        width=round(w * ratio),
        height=round(h * ratio),
    )


class RegionSelector(QWidget):
    """Translucent overlay; emits ``selected`` (Rect in physical px) or ``cancelled``."""

    selected = Signal(object)   # processing.Rect
    cancelled = Signal()

    def __init__(self, screen) -> None:  # noqa: ANN001 (QScreen)
        super().__init__()
        self._screen = screen
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._done = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.BypassWindowManagerHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def show_on_screen(self) -> None:
        """Bind to the target screen and cover it exactly, then show."""
        geo = self._screen.geometry()
        # Ensure the native window lives on the intended screen before placement.
        self.createWinId()
        handle = self.windowHandle()
        if handle is not None:
            handle.setScreen(self._screen)
        self.setGeometry(geo)
        self.show()
        self.setGeometry(geo)   # re-assert after the window manager may have moved it
        self.raise_()
        self.activateWindow()
        self.setFocus()

    # ----------------------------------------------------------------- drawing
    def _selection_rect(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        sel = self._selection_rect()

        # Dim everything, then clear the selection so it shows through crisply.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
        if not sel.isNull():
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(sel, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)

            painter.setPen(QPen(QColor(56, 160, 255), 2))
            painter.drawRect(sel)

            ratio = self._screen.devicePixelRatio()
            label = f"{round(sel.width() * ratio)} x {round(sel.height() * ratio)} px"
            painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
            tw = painter.fontMetrics().horizontalAdvance(label) + 14
            th = painter.fontMetrics().height() + 8
            bx = sel.x()
            by = sel.y() - th - 4 if sel.y() - th - 4 > 0 else sel.y() + 4
            painter.fillRect(bx, by, tw, th, QColor(56, 160, 255))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(
                QRect(bx, by, tw, th),
                Qt.AlignmentFlag.AlignCenter,
                label,
            )

        if self._origin is None:
            hint = "Drag to select a region    ·    Esc to cancel"
            painter.setFont(QFont("Segoe UI", 13))
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "\n\n" + hint,
            )

    # ------------------------------------------------------------------ events
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.position().toPoint()
            self._current = self._origin
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._origin is not None:
            self._current = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return
        sel = self._selection_rect()
        if sel.width() < 8 or sel.height() < 8:
            self._finish(None)
            return
        ratio = self._screen.devicePixelRatio()
        rect = logical_rect_to_physical(
            sel.x(), sel.y(), sel.width(), sel.height(), ratio
        )
        self._finish(rect)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)

    def _finish(self, rect: Rect | None) -> None:
        if self._done:
            return
        self._done = True
        self.close()
        if rect is None:
            self.cancelled.emit()
        else:
            self.selected.emit(rect)

"""Generate the app icon (.ico) from a painted Qt pixmap.

Run once with: uv run python tools/make_icon.py
Produces src/screen_recorder/assets/app.ico (multi-size).

The motif: a rounded dark "screen" with a red record dot and a subtle frame,
echoing the in-app record button.
"""

from __future__ import annotations

import os
import struct

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QApplication


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    s = size
    margin = s * 0.07
    rect = QRectF(margin, margin, s - 2 * margin, s - 2 * margin)
    radius = s * 0.22

    # Screen body: subtle vertical gradient.
    grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    grad.setColorAt(0.0, QColor("#2a2f3a"))
    grad.setColorAt(1.0, QColor("#1b1e26"))
    p.setBrush(QBrush(grad))
    p.setPen(QPen(QColor("#3a4150"), max(1.0, s * 0.012)))
    p.drawRoundedRect(rect, radius, radius)

    # Record dot.
    dot_r = s * 0.17
    cx, cy = s * 0.5, s * 0.5
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#e5484d"))
    p.drawEllipse(QRectF(cx - dot_r, cy - dot_r, dot_r * 2, dot_r * 2))
    # Glow ring.
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(229, 72, 77, 90), max(1.0, s * 0.03)))
    ring = dot_r * 1.55
    p.drawEllipse(QRectF(cx - ring, cy - ring, ring * 2, ring * 2))

    p.end()
    return img


def image_to_png_bytes(img: QImage) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba)


def write_ico(path: str, sizes: list[int]) -> None:
    pngs = [image_to_png_bytes(render(sz)) for sz in sizes]
    count = len(pngs)
    header = struct.pack("<HHH", 0, 1, count)  # reserved, type=1 (icon), count
    offset = 6 + count * 16
    entries = b""
    data = b""
    for sz, png in zip(sizes, pngs):
        w = 0 if sz >= 256 else sz
        h = 0 if sz >= 256 else sz
        entries += struct.pack(
            "<BBBBHHII", w, h, 0, 0, 1, 32, len(png), offset
        )
        data += png
        offset += len(png)
    with open(path, "wb") as f:
        f.write(header + entries + data)


def main() -> None:
    app = QApplication([])  # noqa: F841 (needed for QImage/QPainter)
    out_dir = os.path.join(os.path.dirname(__file__), "..", "src", "screen_recorder", "assets")
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    ico_path = os.path.join(out_dir, "app.ico")
    write_ico(ico_path, [16, 32, 48, 64, 128, 256])
    # Also a PNG for the in-app window icon at runtime if wanted.
    render(256).save(os.path.join(out_dir, "app.png"), "PNG")
    print("wrote", ico_path)


if __name__ == "__main__":
    main()

"""Frame processing: crop to region, downscale to a target height.

Input frames are BGRA ``(H, W, 4)`` numpy arrays from windows-capture. Output
is BGR ``(h, w, 3)`` with even dimensions (yuv420p, which libx264 uses for broad
compatibility, requires even width and height).
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class Rect:
    """A capture region in source-frame pixel coordinates."""

    x: int
    y: int
    width: int
    height: int

    def clamp_to(self, frame_w: int, frame_h: int) -> "Rect":
        x = max(0, min(self.x, frame_w - 1))
        y = max(0, min(self.y, frame_h - 1))
        w = max(1, min(self.width, frame_w - x))
        h = max(1, min(self.height, frame_h - y))
        return Rect(x, y, w, h)


def _even(n: int) -> int:
    return n if n % 2 == 0 else n - 1


def output_dimensions(src_w: int, src_h: int, target_h: int) -> tuple[int, int]:
    """Output (width, height) for a source size scaled to ``target_h``.

    Aspect ratio is preserved and both dimensions are forced even. If the source
    is already shorter than the target height we keep the source size (no upscale).
    """
    if src_h <= 0 or src_w <= 0:
        return (2, 2)
    out_h = min(target_h, src_h)
    scale = out_h / src_h
    out_w = round(src_w * scale)
    return (max(2, _even(out_w)), max(2, _even(out_h)))


def crop_and_resize(
    frame_bgra: np.ndarray, rect: Rect | None, target_h: int
) -> np.ndarray:
    """Crop ``frame_bgra`` to ``rect`` (if given) then resize to ``target_h``.

    Returns a contiguous BGR uint8 array suitable for piping to FFmpeg.
    """
    h, w = frame_bgra.shape[:2]
    if rect is not None:
        r = rect.clamp_to(w, h)
        frame_bgra = frame_bgra[r.y : r.y + r.height, r.x : r.x + r.width]
        src_w, src_h = r.width, r.height
    else:
        src_w, src_h = w, h

    out_w, out_h = output_dimensions(src_w, src_h, target_h)

    bgr = frame_bgra[:, :, :3]
    if (out_w, out_h) != (src_w, src_h):
        # INTER_AREA gives the best quality when shrinking.
        bgr = cv2.resize(bgr, (out_w, out_h), interpolation=cv2.INTER_AREA)
    else:
        # Still must hit even dims; crop a pixel if the region was odd-sized.
        bgr = bgr[:out_h, :out_w]

    return np.ascontiguousarray(bgr)

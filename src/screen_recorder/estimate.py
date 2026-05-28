"""Bitrate / file-size estimation for visually-lossless H.264 screen capture.

The estimate is a heuristic, not a guarantee: real bitrate depends heavily on
on-screen motion. We model the encoded size as bits-per-pixel-per-frame (bpp)
that falls off roughly geometrically as CRF rises. The constants below were
tuned against typical desktop content (mostly static UI with occasional motion)
and deliberately lean slightly high so the user is warned rather than surprised.
"""

from __future__ import annotations

from dataclasses import dataclass

# bpp at the reference CRF, and how bpp scales per CRF step.
# libx264 ~ -6 CRF doubles bitrate; +6 halves it. Reference: CRF 23 -> ~0.10 bpp
# for moderate-motion desktop content.
_REF_CRF = 23.0
_REF_BPP = 0.10
_CRF_STEP_FOR_DOUBLE = 6.0


def bits_per_pixel(crf: float) -> float:
    """Estimated encoded bits per pixel per frame at the given CRF."""
    return _REF_BPP * 2.0 ** ((_REF_CRF - crf) / _CRF_STEP_FOR_DOUBLE)


@dataclass(frozen=True)
class Estimate:
    mbps: float          # megabits per second
    mb_per_min: float    # megabytes per minute
    mb_per_hour: float    # megabytes per hour

    def summary(self) -> str:
        return f"~{self.mbps:.1f} Mbps  ·  ~{self.mb_per_min:.0f} MB/min  ·  ~{self.mb_per_hour / 1000:.1f} GB/hour"


def estimate(width: int, height: int, fps: int, crf: float) -> Estimate:
    """Estimate bitrate and file size for the given output settings."""
    if width <= 0 or height <= 0 or fps <= 0:
        return Estimate(0.0, 0.0, 0.0)
    bits_per_frame = width * height * bits_per_pixel(crf)
    bits_per_sec = bits_per_frame * fps
    mbps = bits_per_sec / 1_000_000
    bytes_per_sec = bits_per_sec / 8
    mb_per_min = bytes_per_sec * 60 / 1_000_000
    mb_per_hour = mb_per_min * 60
    return Estimate(mbps=mbps, mb_per_min=mb_per_min, mb_per_hour=mb_per_hour)

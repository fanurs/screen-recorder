"""Tier 1: crop/resize geometry rules."""

from __future__ import annotations

import numpy as np

from screen_recorder.processing import Rect, crop_and_resize, output_dimensions


def test_output_dimensions_preserve_aspect_and_even():
    # 1920x1080 (16:9) -> 720 high.
    assert output_dimensions(1920, 1080, 720) == (1280, 720)


def test_output_dimensions_force_even():
    # An odd target/source must round to even both ways (yuv420p requires it).
    w, h = output_dimensions(801, 601, 601)
    assert w % 2 == 0 and h % 2 == 0


def test_no_upscale_when_source_shorter():
    # Source 400 high, asking for 720 -> stays 400 (no upscaling).
    w, h = output_dimensions(600, 400, 720)
    assert h == 400


def test_rect_clamps_within_frame():
    r = Rect(1900, 1050, 500, 500).clamp_to(1920, 1080)
    assert r.x + r.width <= 1920
    assert r.y + r.height <= 1080
    assert r.width >= 1 and r.height >= 1


def test_crop_and_resize_returns_bgr_contiguous():
    frame = np.zeros((1080, 1920, 4), dtype=np.uint8)
    out = crop_and_resize(frame, Rect(100, 100, 640, 480), target_h=480)
    assert out.shape == (480, 640, 3)
    assert out.dtype == np.uint8
    assert out.flags["C_CONTIGUOUS"]


def test_crop_pixels_match_direct_slice():
    # A region crop with no resize must equal a plain numpy slice (BGR).
    rng = np.random.default_rng(0)
    frame = rng.integers(0, 255, (1080, 1920, 4), dtype=np.uint8)
    rect = Rect(200, 150, 800, 600)
    direct = frame[150:750, 200:1000, :3]
    out = crop_and_resize(frame, rect, target_h=600)  # 600 == region height -> no resize
    assert np.array_equal(direct, out)


def test_whole_frame_when_region_none():
    frame = np.zeros((1080, 1920, 4), dtype=np.uint8)
    out = crop_and_resize(frame, None, target_h=1080)
    assert out.shape == (1080, 1920, 3)

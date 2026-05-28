"""Tier 1: bitrate/size estimation is pure math."""

from __future__ import annotations

from screen_recorder import estimate


def test_zero_dimensions_yield_zero():
    e = estimate.estimate(0, 720, 30, 16)
    assert e.mbps == 0 and e.mb_per_min == 0


def test_lower_crf_is_larger():
    hi_q = estimate.estimate(1280, 720, 30, 12)   # better quality
    lo_q = estimate.estimate(1280, 720, 30, 24)   # smaller file
    assert hi_q.mbps > lo_q.mbps


def test_scales_with_pixels_and_fps():
    base = estimate.estimate(640, 480, 30, 18)
    double_fps = estimate.estimate(640, 480, 60, 18)
    assert double_fps.mbps == base.mbps * 2

    quad_pixels = estimate.estimate(1280, 960, 30, 18)
    assert abs(quad_pixels.mbps - base.mbps * 4) < 1e-6


def test_crf_step_of_6_doubles_bitrate():
    a = estimate.estimate(1280, 720, 30, 23)
    b = estimate.estimate(1280, 720, 30, 17)   # -6 CRF
    assert abs(b.mbps / a.mbps - 2.0) < 1e-6


def test_units_are_consistent():
    e = estimate.estimate(1280, 720, 30, 16)
    # MB/min should equal mbps/8 * 60.
    assert abs(e.mb_per_min - (e.mbps / 8 * 60)) < 1e-6
    assert abs(e.mb_per_hour - e.mb_per_min * 60) < 1e-6

"""Tier 1: region selection coordinate mapping (logical -> physical)."""

from __future__ import annotations

from screen_recorder.region import logical_rect_to_physical


def test_ratio_one_is_identity():
    r = logical_rect_to_physical(100, 50, 640, 480, 1.0)
    assert (r.x, r.y, r.width, r.height) == (100, 50, 640, 480)


def test_hidpi_scales_up():
    # On a 1.5x display, a 400x300 logical selection covers 600x450 physical px.
    r = logical_rect_to_physical(200, 100, 400, 300, 1.5)
    assert (r.x, r.y, r.width, r.height) == (300, 150, 600, 450)


def test_rounds_to_nearest_int():
    r = logical_rect_to_physical(10, 10, 101, 101, 1.25)
    assert r.width == round(101 * 1.25)
    assert isinstance(r.width, int)

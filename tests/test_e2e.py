"""Tier 3: real end-to-end recording smoke tests.

These actually capture the screen and run FFmpeg, so they are slow and require a
real display + the bundled FFmpeg. Marked ``e2e`` — run only these with
``pytest -m e2e`` or skip them with ``pytest -m "not e2e"``.
"""

from __future__ import annotations

import os
import subprocess
import time

import pytest

from screen_recorder.encoder import ffmpeg_exe
from screen_recorder.monitors import list_monitors
from screen_recorder.processing import Rect
from screen_recorder.recorder import Recorder, RecordSettings

pytestmark = pytest.mark.e2e


def _a_capturable_monitor_index() -> int:
    mons = list_monitors()
    if not mons:
        pytest.skip("no monitors detected")
    # Prefer the primary; fall back to the first.
    for m in mons:
        if m.is_primary:
            return m.capture_index
    return mons[0].capture_index


def _probe_dimensions(path: str) -> tuple[int, int]:
    """Return (width, height) of the first video stream via ffmpeg stderr."""
    out = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", path],
        capture_output=True, text=True,
    )
    # ffmpeg prints stream info to stderr; find "NNNxNNN".
    import re

    m = re.search(r"(\d{2,5})x(\d{2,5})", out.stderr)
    assert m, f"could not parse dimensions from:\n{out.stderr}"
    return int(m.group(1)), int(m.group(2))


def test_records_region_to_mp4(tmp_path):
    out = str(tmp_path / "clip.mp4")
    rec = Recorder(RecordSettings(
        monitor_index=_a_capturable_monitor_index(),
        region=Rect(100, 100, 640, 480),
        target_height=480, fps=30, crf=20, output_path=out,
    ))
    rec.start()
    time.sleep(1.5)
    stats = rec.stop()

    assert stats.error is None
    assert stats.encoded > 20            # ~30fps for 1.5s, allow slack
    assert os.path.exists(out) and os.path.getsize(out) > 0
    w, h = _probe_dimensions(out)
    assert (w, h) == (640, 480)          # 4:3 region at 480 high


def test_records_full_monitor_and_downscales(tmp_path):
    out = str(tmp_path / "mon.mp4")
    rec = Recorder(RecordSettings(
        monitor_index=_a_capturable_monitor_index(),
        target_height=480, fps=30, crf=22, output_path=out,
    ))
    rec.start()
    time.sleep(1.0)
    stats = rec.stop()

    assert stats.error is None
    assert os.path.exists(out) and os.path.getsize(out) > 0
    w, h = _probe_dimensions(out)
    assert h == 480                      # downscaled to target height
    assert w % 2 == 0 and h % 2 == 0     # yuv420p needs even dims


def test_region_border_does_not_bleed_into_recording(tmp_path):
    """The persistent border around a region is drawn OUTSIDE the crop so it
    is never captured. Show the border, record the same region, and assert the
    output's edge pixels don't contain the border's distinctive red."""
    import cv2
    import numpy as np
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from screen_recorder.region_border import RegionBorder

    app = QApplication.instance() or QApplication([])
    primary = QGuiApplication.primaryScreen()
    if primary is None:
        pytest.skip("no primary screen")

    rect = Rect(300, 300, 600, 400)
    border = RegionBorder(primary, rect)
    border.show_border()
    # Let the border actually paint before we start capturing.
    for _ in range(8):
        app.processEvents()
        time.sleep(0.03)

    out = str(tmp_path / "border.mkv")  # mkv to skip the remux step
    rec = Recorder(RecordSettings(
        monitor_index=_a_capturable_monitor_index(),
        region=rect, target_height=400, fps=30, crf=18, output_path=out,
    ))
    rec.start()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.04)
    rec.stop()
    border.close()
    app.processEvents()

    cap = cv2.VideoCapture(out)
    ok, frame = cap.read()
    cap.release()
    assert ok, "could not read a frame from the recording"

    # Scan a thin ring of edge pixels for the border's red (#e5484d -> BGR).
    # We measure the *fraction* of strongly-red pixels — should be ~0 if the
    # border is fully outside the captured area.
    t = 4
    ring = np.concatenate([
        frame[:t].reshape(-1, 3), frame[-t:].reshape(-1, 3),
        frame[:, :t].reshape(-1, 3), frame[:, -t:].reshape(-1, 3),
    ]).astype(int)
    b, g, r = ring[:, 0], ring[:, 1], ring[:, 2]
    red_fraction = float(((r > 180) & (g < 90) & (b < 90)).mean())
    # Real desktop content can include reddish accents; require it to be tiny.
    assert red_fraction < 0.05, f"edge ring is {red_fraction:.2%} border-red — border is bleeding in"

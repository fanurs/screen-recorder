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

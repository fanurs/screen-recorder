"""Recording orchestration.

Ties the capture source to the FFmpeg encoder. A fixed-rate sampler thread pulls
the latest captured frame every ``1/fps`` seconds, processes it (crop + resize),
and writes it to the encoder. Sampling on a clock (rather than encoding every
captured event) guarantees the output plays at the requested fps and stays in
sync regardless of how often the screen actually changes.

If the encoder/disk can't keep up, the bounded queue between the sampler and the
encoder thread fills and we count a dropped frame instead of blocking capture.
"""

from __future__ import annotations

import ctypes
import os
import queue
import tempfile
import threading
import time
from dataclasses import dataclass

import numpy as np

from .capture import ScreenCapture
from .encoder import EncoderConfig, FfmpegEncoder, nvenc_usable, remux_to_mp4
from .processing import Rect, crop_and_resize, output_dimensions


@dataclass
class RecordSettings:
    monitor_index: int | None = None
    window_hwnd: int | None = None
    region: Rect | None = None       # in source-frame pixel coords; None = whole frame
    target_height: int = 720
    fps: int = 30
    crf: int = 16
    use_nvenc: bool = False
    output_path: str = "recording.mp4"
    cursor_capture: bool = True


@dataclass
class Stats:
    captured: int = 0          # frames sampled from the source
    encoded: int = 0           # frames handed to ffmpeg
    dropped: int = 0           # frames dropped because the encode queue was full
    measured_fps: float = 0.0
    elapsed: float = 0.0
    error: str | None = None
    notice: str | None = None  # non-fatal info, e.g. "fell back to CPU encoder"


class _HighResTimer:
    """Raise the Windows system timer resolution to 1 ms for the duration.

    Without this, ``time.sleep`` and thread scheduling are quantised to the
    default ~15.6 ms tick, which makes it impossible to hold a steady 30/60 Hz.
    """

    def __enter__(self) -> "_HighResTimer":
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
            self._active = True
        except Exception:
            self._active = False
        return self

    def __exit__(self, *exc) -> None:
        if getattr(self, "_active", False):
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass


def _precise_sleep_until(deadline: float, stop: threading.Event) -> None:
    """Sleep until ``deadline`` (perf_counter seconds), spin for the last ~2 ms."""
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0 or stop.is_set():
            return
        if remaining > 0.002:
            # Leave a 1 ms margin; coarse sleep, then busy-wait the remainder.
            if stop.wait(remaining - 0.001):
                return
        # else: busy-spin the final sub-2ms for accuracy.


class Recorder:
    def __init__(self, settings: RecordSettings) -> None:
        self.settings = settings
        self._capture: ScreenCapture | None = None
        self._encoder: FfmpegEncoder | None = None
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=8)
        self._sampler: threading.Thread | None = None
        self._encoder_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._stats = Stats()
        # Always encode to a crash-safe MKV intermediate; remux to the final
        # (.mp4 or .mkv) container on stop.
        fd, self._temp_mkv = tempfile.mkstemp(suffix=".mkv", prefix="screenrec_")
        os.close(fd)

    @property
    def stats(self) -> Stats:
        with self._lock:
            return Stats(**vars(self._stats))

    def start(self) -> None:
        s = self.settings
        # Throttle OS frame delivery to ~the sample rate so the capture callback
        # isn't copying full frames far more often than we consume them.
        update_interval = max(1, int(1000 / s.fps / 2))

        # If NVENC was requested, verify it actually works before recording;
        # otherwise silently fall back to the CPU encoder with a notice.
        use_nvenc = s.use_nvenc
        if use_nvenc and not nvenc_usable():
            use_nvenc = False
            with self._lock:
                self._stats.notice = "GPU (NVENC) unavailable — used CPU encoder (libx264)."

        self._capture = ScreenCapture(
            monitor_index=s.monitor_index,
            window_hwnd=s.window_hwnd,
            cursor_capture=s.cursor_capture,
            minimum_update_interval=update_interval,
        )
        self._capture.start()
        if not self._capture.wait_for_first_frame(timeout=5.0):
            self._capture.stop()
            raise RuntimeError("No frame received from capture source within 5s")

        first = self._capture.latest.get()
        assert first is not None
        sample = crop_and_resize(first, s.region, s.target_height)
        out_h, out_w = sample.shape[0], sample.shape[1]

        self._encoder = FfmpegEncoder(
            EncoderConfig(
                width=out_w,
                height=out_h,
                fps=s.fps,
                crf=s.crf,
                output_path=self._temp_mkv,
                use_nvenc=use_nvenc,
            )
        )
        self._encoder.start()

        self._stop.clear()
        self._encoder_thread = threading.Thread(target=self._encode_loop, daemon=True)
        self._sampler = threading.Thread(target=self._sample_loop, daemon=True)
        self._encoder_thread.start()
        self._sampler.start()

    def _sample_loop(self) -> None:
        s = self.settings
        period = 1.0 / s.fps
        with _HighResTimer():
            self._run_sampler(period)

    def _run_sampler(self, period: float) -> None:
        s = self.settings
        start = time.perf_counter()
        next_tick = start + period
        last_frame: np.ndarray | None = None
        while not self._stop.is_set():
            now = time.perf_counter()
            if now < next_tick:
                _precise_sleep_until(next_tick, self._stop)
                if self._stop.is_set():
                    break
                now = time.perf_counter()
            next_tick += period
            # If we've fallen far behind (e.g. a stall), resync to avoid a burst.
            if now - next_tick > period:
                next_tick = now + period

            raw = self._capture.latest.get() if self._capture else None
            if raw is not None:
                try:
                    last_frame = crop_and_resize(raw, s.region, s.target_height)
                except Exception as exc:  # noqa: BLE001
                    self._record_error(f"processing error: {exc}")
                    break
            if last_frame is None:
                continue

            with self._lock:
                self._stats.captured += 1
                self._stats.elapsed = now - start
                if self._stats.elapsed > 0:
                    self._stats.measured_fps = self._stats.captured / self._stats.elapsed

            try:
                self._queue.put_nowait(last_frame)
            except queue.Full:
                with self._lock:
                    self._stats.dropped += 1

    def _encode_loop(self) -> None:
        while True:
            try:
                frame = self._queue.get(timeout=0.25)
            except queue.Empty:
                if self._stop.is_set() and self._queue.empty():
                    break
                continue
            try:
                self._encoder.write(frame.tobytes())  # type: ignore[union-attr]
                with self._lock:
                    self._stats.encoded += 1
            except Exception as exc:  # noqa: BLE001
                self._record_error(f"encoder write failed: {exc}")
                break

    def _record_error(self, msg: str) -> None:
        with self._lock:
            if self._stats.error is None:
                self._stats.error = msg
        self._stop.set()

    def stop(self) -> Stats:
        self._stop.set()
        if self._sampler:
            self._sampler.join(timeout=5)
        if self._encoder_thread:
            self._encoder_thread.join(timeout=10)
        if self._capture:
            self._capture.stop()
        if self._encoder:
            err = self._encoder.close()
            if err:
                self._record_error(err.strip().splitlines()[-1] if err.strip() else "ffmpeg error")
        self._finalize_output()
        return self.stats

    def _finalize_output(self) -> None:
        """Move/remux the temp MKV to the user's chosen output path."""
        dst = self.settings.output_path
        if not os.path.exists(self._temp_mkv) or os.path.getsize(self._temp_mkv) == 0:
            if self._stats.error is None:
                self._record_error("No video was recorded.")
            self._cleanup_temp()
            return

        if dst.lower().endswith(".mkv"):
            # Same container: just move the file into place.
            try:
                os.replace(self._temp_mkv, dst)
            except Exception as exc:  # noqa: BLE001
                self._record_error(f"could not save file: {exc}")
            return

        # MP4 (or anything else): lossless stream copy into the target container.
        err = remux_to_mp4(self._temp_mkv, dst)
        if err:
            # Remux failed; keep the MKV next to the intended path so work isn't lost.
            fallback = os.path.splitext(dst)[0] + ".mkv"
            try:
                os.replace(self._temp_mkv, fallback)
                with self._lock:
                    self._stats.notice = f"MP4 remux failed; saved as {os.path.basename(fallback)} instead."
                self.settings.output_path = fallback
            except Exception:
                self._record_error(f"remux failed: {err.strip().splitlines()[-1] if err.strip() else err}")
        else:
            self._cleanup_temp()

    def _cleanup_temp(self) -> None:
        try:
            if os.path.exists(self._temp_mkv):
                os.remove(self._temp_mkv)
        except Exception:
            pass


def planned_output_size(
    src_w: int, src_h: int, region: Rect | None, target_height: int
) -> tuple[int, int]:
    """Output (w, h) the recorder will produce, for the live size estimate."""
    if region is not None:
        r = region.clamp_to(src_w, src_h)
        src_w, src_h = r.width, r.height
    return output_dimensions(src_w, src_h, target_height)

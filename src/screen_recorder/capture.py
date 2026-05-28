"""Screen-capture source built on windows-capture.

windows-capture is event-driven: ``on_frame_arrived`` fires only when the screen
changes, and the numpy buffer it hands us is a view over native memory that is
only valid for the duration of the callback. So we copy each frame and store it
as "the latest frame". The recorder then samples this latest frame on a fixed
clock, which is what gives us a steady output frame rate even when the screen is
static.
"""

from __future__ import annotations

import threading

import numpy as np
from windows_capture import WindowsCapture


class LatestFrame:
    """Thread-safe holder for the most recent captured BGRA frame."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None

    def set(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frame = frame

    def get(self) -> np.ndarray | None:
        with self._lock:
            return self._frame


class ScreenCapture:
    """Captures a monitor or window; exposes the latest frame as a numpy array."""

    def __init__(
        self,
        monitor_index: int | None = None,
        window_hwnd: int | None = None,
        cursor_capture: bool = True,
        minimum_update_interval: int | None = None,
    ) -> None:
        self.latest = LatestFrame()
        self._control = None
        self._first_frame = threading.Event()

        self._capture = WindowsCapture(
            cursor_capture=cursor_capture,
            monitor_index=monitor_index,
            window_hwnd=window_hwnd,
            minimum_update_interval=minimum_update_interval,
        )

        @self._capture.event
        def on_frame_arrived(frame, capture_control):  # noqa: ANN001
            # frame.frame_buffer is a view over native memory -> copy it.
            self.latest.set(frame.frame_buffer.copy())
            self._first_frame.set()

        @self._capture.event
        def on_closed():
            pass

    def start(self) -> None:
        self._control = self._capture.start_free_threaded()

    def wait_for_first_frame(self, timeout: float = 5.0) -> bool:
        return self._first_frame.wait(timeout)

    def stop(self) -> None:
        if self._control is not None:
            try:
                self._control.stop()
                self._control.wait()
            except Exception:
                pass
            self._control = None

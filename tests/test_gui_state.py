"""Tier 2: GUI state transitions, driven by calling the handlers that user
actions trigger (not by simulating pixel-level clicks).

A fake recorder captures the RecordSettings the window builds, so we can assert
"pressing Start with these controls produces these settings" without launching
FFmpeg or touching a real screen.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QGuiApplication

from screen_recorder.gui import MainWindow
from screen_recorder.monitors import Monitor
from screen_recorder.processing import Rect


class FakeRecorder:
    """Stand-in for Recorder: records the settings, never spawns ffmpeg."""

    instances: list["FakeRecorder"] = []

    def __init__(self, settings):
        self.settings = settings
        self.started = False
        self.stopped = False
        FakeRecorder.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        from screen_recorder.recorder import Stats

        self.stopped = True
        return Stats(captured=30, encoded=30, dropped=0, measured_fps=30.0, elapsed=1.0)

    @property
    def stats(self):
        from screen_recorder.recorder import Stats

        return Stats(captured=10, encoded=10, dropped=0, measured_fps=30.0, elapsed=0.3)


@pytest.fixture
def fake_monitors():
    """Two monitors whose qt_screen is the offscreen primary screen (so overlay
    code paths can run). capture_index 1 = secondary, 2 = primary — deliberately
    'reversed' like the real machine, to guard the ordering bug."""
    screen = QGuiApplication.primaryScreen()
    return [
        Monitor(1, "Monitor 1: 2560×1600", 2560, 1600, is_primary=False, qt_screen=screen),
        Monitor(2, "Monitor 2: 1920×1080 · primary", 1920, 1080, is_primary=True, qt_screen=screen),
    ]


@pytest.fixture
def window(qtbot, fake_monitors, tmp_path, monkeypatch):
    from screen_recorder import config as cfgmod
    from screen_recorder.config import Config

    FakeRecorder.instances.clear()
    # Inject a throwaway config + redirect the save path, so closeEvent's
    # "remember last used" write doesn't touch the real %APPDATA% file.
    monkeypatch.setattr(cfgmod, "config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(cfgmod, "config_path", lambda: str(tmp_path / "config.json"))
    cfg = Config(output_dir=str(tmp_path))
    w = MainWindow(
        recorder_factory=FakeRecorder,
        monitors=fake_monitors,
        nvenc=False,
        config=cfg,
    )
    qtbot.addWidget(w)
    return w


# --------------------------------------------------------------------- modes

def test_default_mode_is_monitor(window):
    assert window._mode() == "monitor"


def test_switch_to_region_then_window(window):
    window._seg_buttons["region"].setChecked(True)
    assert window._mode() == "region"
    window._seg_buttons["window"].setChecked(True)
    assert window._mode() == "window"


# ------------------------------------------------------------- region border

def test_region_border_appears_on_selection(window):
    window._seg_buttons["region"].setChecked(True)
    window._on_region_selected(Rect(100, 100, 640, 480))
    assert window._region_border is not None


def test_region_border_clears_when_leaving_region_mode(window):
    """The exact bug the user reported: switching away from region must remove
    the persistent border."""
    window._seg_buttons["region"].setChecked(True)
    window._on_region_selected(Rect(100, 100, 640, 480))
    assert window._region_border is not None

    window._seg_buttons["monitor"].setChecked(True)
    assert window._region_border is None


def test_region_border_restored_on_return_to_region(window):
    window._seg_buttons["region"].setChecked(True)
    window._on_region_selected(Rect(100, 100, 640, 480))
    window._seg_buttons["window"].setChecked(True)
    assert window._region_border is None

    window._seg_buttons["region"].setChecked(True)
    # Region selection is preserved, so the border comes back.
    assert window._region is not None
    assert window._region_border is not None


def test_switching_monitor_invalidates_region(window):
    window._seg_buttons["region"].setChecked(True)
    window._on_region_selected(Rect(10, 10, 100, 100))
    # Move to the other monitor entry.
    other = 1 - window._monitor_combo.currentIndex()
    window._monitor_combo.setCurrentIndex(other)
    assert window._region is None
    assert window._region_border is None


# ------------------------------------------------------- start -> settings

def test_start_monitor_uses_correct_capture_index(window):
    """Selecting 'Monitor 1' must record capture_index 1 even though Qt lists the
    primary first — this guards the wrong-screen bug."""
    # Select the combo entry whose capture_index is 1.
    idx = next(i for i in range(window._monitor_combo.count())
               if window._monitor_combo.itemData(i).capture_index == 1)
    window._monitor_combo.setCurrentIndex(idx)
    window._seg_buttons["monitor"].setChecked(True)

    window._toggle_record()
    settings = FakeRecorder.instances[-1].settings
    assert settings.monitor_index == 1
    assert settings.region is None
    assert settings.window_hwnd is None


def test_start_region_passes_region_and_monitor(window):
    window._seg_buttons["region"].setChecked(True)
    window._on_region_selected(Rect(50, 60, 320, 240))
    window._toggle_record()
    s = FakeRecorder.instances[-1].settings
    assert s.region == Rect(50, 60, 320, 240)
    assert s.monitor_index is not None


def test_start_reflects_fps_and_quality_sliders(window):
    window._fps_slider.setValue(48)
    window._crf_slider.setValue(20)
    window._res_combo.setCurrentIndex(0)  # 480p
    window._seg_buttons["monitor"].setChecked(True)
    window._toggle_record()
    s = FakeRecorder.instances[-1].settings
    assert s.fps == 48
    assert s.crf == 20
    assert s.target_height == 480


def test_region_mode_without_region_does_not_start(window, monkeypatch):
    # Avoid a real modal dialog during the test.
    monkeypatch.setattr("screen_recorder.gui.QMessageBox.warning", lambda *a, **k: None)
    window._seg_buttons["region"].setChecked(True)
    window._region = None
    window._toggle_record()
    assert window._recorder is None  # never started


def test_start_then_stop_lifecycle(window):
    window._seg_buttons["monitor"].setChecked(True)
    window._toggle_record()
    rec = FakeRecorder.instances[-1]
    assert rec.started and window._recorder is rec
    window._toggle_record()
    assert rec.stopped and window._recorder is None


# --------------------------------------------------------------- estimate

def test_estimate_updates_with_controls(window):
    window._seg_buttons["monitor"].setChecked(True)
    window._fps_slider.setValue(30)
    text_30 = window._estimate_label.text()
    window._fps_slider.setValue(60)
    text_60 = window._estimate_label.text()
    assert text_30 != text_60
    assert "60 Hz" in text_60


def test_quality_label_shows_crf_number(window):
    window._crf_slider.setValue(14)
    assert "CRF 14" in window._crf_label.text()


# ----------------------------------------------------------------- config

def test_default_output_is_auto_timestamped_in_config_dir(window, tmp_path):
    window._seg_buttons["monitor"].setChecked(True)
    window._toggle_record()
    out = FakeRecorder.instances[-1].settings.output_path
    assert out.startswith(str(tmp_path))
    assert "recording-" in out and out.endswith(".mp4")


def test_explicit_save_path_overrides_auto(window, tmp_path):
    explicit = str(tmp_path / "demo.mkv")
    window._explicit_output = explicit
    window._seg_buttons["monitor"].setChecked(True)
    window._toggle_record()
    assert FakeRecorder.instances[-1].settings.output_path == explicit


def test_capture_config_reflects_controls(window):
    window._fps_slider.setValue(24)
    window._crf_slider.setValue(20)
    window._res_combo.setCurrentIndex(0)  # 480p
    cfg = window._capture_config()
    assert cfg.fps == 24 and cfg.crf == 20 and cfg.resolution == 480


def test_config_seeds_controls_on_launch(qtbot, fake_monitors, tmp_path):
    from screen_recorder.config import Config

    cfg = Config(output_dir=str(tmp_path), resolution=1080, fps=50, crf=22)
    w = MainWindow(recorder_factory=FakeRecorder, monitors=fake_monitors, nvenc=False, config=cfg)
    qtbot.addWidget(w)
    assert w._res_combo.currentData() == 1080
    assert w._fps_slider.value() == 50
    assert w._crf_slider.value() == 22

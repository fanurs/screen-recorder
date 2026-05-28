"""PySide6 main window: configure and drive a recording."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import estimate
from .assets import icon_path
from .config import Config
from .encoder import nvenc_usable
from .monitor_flash import MonitorFlash
from .monitors import Monitor, list_monitors
from .processing import Rect
from .recorder import RecordSettings, Recorder, planned_output_size
from .region import RegionSelector
from .region_border import RegionBorder
from .windows_enum import list_windows

_HEIGHTS = [480, 540, 720, 900, 1080]

_STYLESHEET = """
* { font-family: 'Segoe UI', sans-serif; font-size: 13px; color: #e6e8ec; }
QWidget#root { background: #15171c; }
QFrame#card {
    background: #1e2127;
    border: 1px solid #2b2f37;
    border-radius: 10px;
}
QLabel#cardTitle { color: #8b93a3; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#estimate { color: #6fb3ff; font-size: 14px; font-weight: 600; }
QLabel#stats { color: #9aa3b2; font-size: 12px; }
QLabel#statsRec { color: #ff5d5d; font-size: 13px; font-weight: 700; }
QLabel#filePath { color: #9aa3b2; font-size: 12px; }

QComboBox, QPushButton#secondary {
    background: #262a32; border: 1px solid #353b45; border-radius: 7px;
    padding: 7px 10px;
}
QComboBox:hover, QPushButton#secondary:hover { border-color: #4a91ff; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background: #262a32; border: 1px solid #353b45;
    selection-background-color: #2f6bd6; outline: none;
}

QPushButton#secondary { color: #cdd3dd; }
QPushButton#secondary:disabled { color: #5a606b; border-color: #2b2f37; }

QPushButton#segment {
    background: transparent; border: none; border-radius: 7px;
    padding: 8px 4px; color: #9aa3b2; font-weight: 600;
}
QPushButton#segment:checked { background: #2f6bd6; color: white; }
QPushButton#segment:hover:!checked { background: #262a32; }

QPushButton#record {
    background: #e5484d; border: none; border-radius: 9px;
    padding: 13px; color: white; font-size: 15px; font-weight: 700;
}
QPushButton#record:hover { background: #f25055; }
QPushButton#record[recording="true"] { background: #2b2f37; color: #ff8c8c; }
QPushButton#record[recording="true"]:hover { background: #353b45; }

QPushButton#open {
    background: transparent; border: 1px solid #4a91ff; border-radius: 8px;
    padding: 10px; color: #6fb3ff; font-weight: 600;
}
QPushButton#open:hover { background: rgba(79,143,255,0.12); }

QSlider::groove:horizontal { height: 5px; background: #353b45; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #4a91ff; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #ffffff; width: 16px; height: 16px;
    margin: -6px 0; border-radius: 8px;
}
QToolTip { background: #262a32; color: #e6e8ec; border: 1px solid #353b45; }
"""


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(16, 14, 16, 16)
    outer.setSpacing(10)
    lbl = QLabel(title.upper())
    lbl.setObjectName("cardTitle")
    outer.addWidget(lbl)
    return frame, outer


class MainWindow(QWidget):
    def __init__(
        self,
        recorder_factory: Callable[[RecordSettings], Recorder] = Recorder,
        monitors: list[Monitor] | None = None,
        nvenc: bool | None = None,
        config: Config | None = None,
    ) -> None:
        """``recorder_factory``, ``monitors``, ``nvenc`` and ``config`` are
        injectable so the window can be driven in tests without a real recorder,
        real screens, a real GPU probe, or touching the user's config file.
        Production code uses the defaults."""
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle("Screen Recorder")
        self.setMinimumWidth(460)
        self.setStyleSheet(_STYLESHEET)
        _ico = icon_path()
        if _ico:
            self.setWindowIcon(QIcon(_ico))

        self._config = config if config is not None else Config.load()
        self._recorder_factory = recorder_factory
        self._recorder: Recorder | None = None
        self._region: Rect | None = None
        self._region_selector: RegionSelector | None = None
        self._region_border: RegionBorder | None = None
        # An explicit "Save to…" override, or None to auto-generate a timestamped
        # path in the configured output directory at record time.
        self._explicit_output: str | None = None
        self._last_saved_path: str | None = None
        self._nvenc = nvenc_usable() if nvenc is None else nvenc
        self._monitors: list[Monitor] = monitors if monitors is not None else list_monitors()
        self._monitor_flash = MonitorFlash()

        self._build_ui()
        self._apply_config()
        self._refresh_estimate()

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(250)
        self._stats_timer.timeout.connect(self._update_stats)

    # ---------------------------------------------------------------- UI build
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        # ---- Source card ----
        src_card, src = _card("Source")

        seg_row = QHBoxLayout()
        seg_row.setSpacing(4)
        self._mode_group = QButtonGroup(self)
        self._seg_buttons: dict[str, QPushButton] = {}
        for key, text in (("monitor", "Monitor"), ("region", "Region"), ("window", "Window")):
            btn = QPushButton(text)
            btn.setObjectName("segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._mode_group.addButton(btn)
            self._seg_buttons[key] = btn
            seg_row.addWidget(btn)
            btn.toggled.connect(self._on_mode_changed)
        self._seg_buttons["monitor"].setChecked(True)
        src.addLayout(seg_row)

        self._monitor_combo = QComboBox()
        for m in self._monitors:
            self._monitor_combo.addItem(m.label, m)
        # Default to the primary monitor.
        for i, m in enumerate(self._monitors):
            if m.is_primary:
                self._monitor_combo.setCurrentIndex(i)
                break
        self._monitor_combo.currentIndexChanged.connect(self._on_monitor_changed)
        mon_row = QHBoxLayout()
        mon_row.addWidget(self._monitor_combo, 1)
        self._identify_btn = QPushButton("Identify")
        self._identify_btn.setObjectName("secondary")
        self._identify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._identify_btn.setToolTip("Flash a number on each screen to see which is which.")
        self._identify_btn.clicked.connect(lambda: self._flash_monitors())
        mon_row.addWidget(self._identify_btn)
        self._monitor_row_widget = QWidget()
        self._monitor_row_widget.setLayout(mon_row)
        src.addWidget(self._monitor_row_widget)

        region_row = QHBoxLayout()
        self._region_btn = QPushButton("Select region…")
        self._region_btn.setObjectName("secondary")
        self._region_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._region_btn.clicked.connect(self._select_region)
        self._region_label = QLabel("No region selected")
        self._region_label.setObjectName("filePath")
        region_row.addWidget(self._region_btn)
        region_row.addWidget(self._region_label, 1)
        self._region_widget = QWidget()
        self._region_widget.setLayout(region_row)
        src.addWidget(self._region_widget)

        win_row = QHBoxLayout()
        self._window_combo = QComboBox()
        self._refresh_windows_btn = QPushButton("↻")
        self._refresh_windows_btn.setObjectName("secondary")
        self._refresh_windows_btn.setFixedWidth(40)
        self._refresh_windows_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_windows_btn.setToolTip(
            "Refresh the window list — click after opening a new app so it appears here."
        )
        self._refresh_windows_btn.clicked.connect(self._populate_windows)
        win_row.addWidget(self._window_combo, 1)
        win_row.addWidget(self._refresh_windows_btn)
        self._window_widget = QWidget()
        self._window_widget.setLayout(win_row)
        src.addWidget(self._window_widget)
        self._populate_windows()

        root.addWidget(src_card)

        # ---- Output settings card ----
        out_card, out = _card("Output")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        grid.addWidget(QLabel("Resolution"), 0, 0)
        self._res_combo = QComboBox()
        for h in _HEIGHTS:
            self._res_combo.addItem(f"{h}p", h)
        self._res_combo.setCurrentIndex(_HEIGHTS.index(720))
        self._res_combo.currentIndexChanged.connect(self._refresh_estimate)
        grid.addWidget(self._res_combo, 0, 1, 1, 2)

        grid.addWidget(QLabel("Frame rate"), 1, 0)
        self._fps_slider = QSlider(Qt.Orientation.Horizontal)
        self._fps_slider.setRange(10, 60)
        self._fps_slider.setValue(30)
        self._fps_slider.valueChanged.connect(self._refresh_estimate)
        self._fps_label = QLabel("30 Hz")
        self._fps_label.setMinimumWidth(64)
        self._fps_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self._fps_slider, 1, 1)
        grid.addWidget(self._fps_label, 1, 2)

        grid.addWidget(QLabel("Quality"), 2, 0)
        self._crf_slider = QSlider(Qt.Orientation.Horizontal)
        self._crf_slider.setRange(10, 28)
        self._crf_slider.setValue(16)
        self._crf_slider.setInvertedAppearance(True)  # right = higher quality
        self._crf_slider.valueChanged.connect(self._refresh_estimate)
        self._crf_label = QLabel("CRF 16 · Visually lossless")
        self._crf_label.setMinimumWidth(180)
        self._crf_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self._crf_slider, 2, 1)
        grid.addWidget(self._crf_label, 2, 2)

        grid.addWidget(QLabel("Encoder"), 3, 0)
        self._enc_combo = QComboBox()
        self._enc_combo.addItem("libx264 (CPU)", False)
        if self._nvenc:
            self._enc_combo.addItem("NVENC (GPU)", True)
        grid.addWidget(self._enc_combo, 3, 1, 1, 2)
        grid.setColumnStretch(1, 1)
        out.addLayout(grid)

        file_row = QHBoxLayout()
        self._file_btn = QPushButton("Save to…")
        self._file_btn.setObjectName("secondary")
        self._file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._file_btn.clicked.connect(self._choose_file)
        self._file_label = QLabel()
        self._file_label.setObjectName("filePath")
        self._file_label.setWordWrap(True)
        file_row.addWidget(self._file_btn)
        file_row.addWidget(self._file_label, 1)
        out.addLayout(file_row)

        self._timestamp_cb = QCheckBox("Append timestamp to filename")
        self._timestamp_cb.setChecked(True)
        self._timestamp_cb.setToolTip(
            "When on, each recording is named with the current date/time so "
            "they never overwrite each other."
        )
        self._timestamp_cb.toggled.connect(self._on_timestamp_toggled)
        out.addWidget(self._timestamp_cb)

        self._estimate_label = QLabel()
        self._estimate_label.setObjectName("estimate")
        out.addWidget(self._estimate_label)

        root.addWidget(out_card)

        # ---- Controls ----
        self._record_btn = QPushButton("● Start recording")
        self._record_btn.setObjectName("record")
        self._record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._record_btn.setProperty("recording", False)
        self._record_btn.clicked.connect(self._toggle_record)
        root.addWidget(self._record_btn)

        self._stats_label = QLabel("Ready.")
        self._stats_label.setObjectName("stats")
        root.addWidget(self._stats_label)

        open_row = QHBoxLayout()
        self._open_file_btn = QPushButton("Open video")
        self._open_file_btn.setObjectName("open")
        self._open_file_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_file_btn.clicked.connect(self._open_last_file)
        self._open_folder_btn = QPushButton("Show in folder")
        self._open_folder_btn.setObjectName("open")
        self._open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_folder_btn.clicked.connect(self._open_last_folder)
        open_row.addWidget(self._open_file_btn)
        open_row.addWidget(self._open_folder_btn)
        self._open_row_widget = QWidget()
        self._open_row_widget.setLayout(open_row)
        self._open_row_widget.setVisible(False)
        root.addWidget(self._open_row_widget)

        self._on_mode_changed()

    # ------------------------------------------------------------------ config
    def _apply_config(self) -> None:
        """Seed the controls from the remembered config."""
        c = self._config
        i = self._res_combo.findData(c.resolution)
        if i >= 0:
            self._res_combo.setCurrentIndex(i)
        self._fps_slider.setValue(c.fps)
        self._crf_slider.setValue(c.crf)
        if c.use_nvenc and self._nvenc:
            i = self._enc_combo.findData(True)
            if i >= 0:
                self._enc_combo.setCurrentIndex(i)
        self._timestamp_cb.setChecked(c.append_timestamp)
        self._update_file_label()

    def _capture_config(self) -> Config:
        """Snapshot the current control values into a Config for persistence."""
        self._config.resolution = self._res_combo.currentData()
        self._config.fps = self._fps_slider.value()
        self._config.crf = self._crf_slider.value()
        self._config.use_nvenc = bool(self._enc_combo.currentData())
        self._config.append_timestamp = self._timestamp_cb.isChecked()
        return self._config

    def _on_timestamp_toggled(self, checked: bool) -> None:
        self._config.append_timestamp = checked
        # Toggling the auto-naming mode invalidates any prior explicit path
        # the user picked — the new mode should be honoured for the next run.
        self._explicit_output = None
        self._update_file_label()

    def _update_file_label(self) -> None:
        if self._explicit_output:
            self._file_label.setText(self._explicit_output)
        elif self._config.append_timestamp:
            self._file_label.setText(
                f"{self._config.output_dir}\\  (auto-named, timestamped)"
            )
        else:
            self._file_label.setText(
                f"{self._config.output_dir}\\recording.{self._config.container}"
            )

    def _resolve_output_path(self) -> str:
        """The path this recording will be written to."""
        return self._explicit_output or self._config.next_output_path()

    def _needs_overwrite_prompt(self, path: str) -> bool:
        """True when an existing file at ``path`` could be silently clobbered.

        Auto-timestamped paths are already collision-free, so we only need to
        guard the fixed-name and explicit ``Save to…`` cases.
        """
        if self._explicit_output:
            return True
        return not self._config.append_timestamp

    # ------------------------------------------------------------- population
    def _populate_windows(self) -> None:
        current = self._window_combo.currentData()
        self._window_combo.clear()
        for entry in list_windows():
            self._window_combo.addItem(entry.title, entry.hwnd)
        if current is not None:
            idx = self._window_combo.findData(current)
            if idx >= 0:
                self._window_combo.setCurrentIndex(idx)

    # ---------------------------------------------------------------- helpers
    def _mode(self) -> str:
        for key, btn in self._seg_buttons.items():
            if btn.isChecked():
                return key
        return "monitor"

    def _selected_monitor(self) -> Monitor | None:
        return self._monitor_combo.currentData()

    def _source_size(self) -> tuple[int, int]:
        m = self._selected_monitor()
        if m is None:
            return 1920, 1080
        return m.phys_width, m.phys_height

    def _on_monitor_changed(self) -> None:
        # A region is tied to the monitor it was drawn on; invalidate on switch.
        if self._region is not None:
            self._region = None
            self._region_label.setText("No region selected")
            self._clear_region_border()
        self._refresh_estimate()
        if len(self._monitors) > 1:
            self._flash_monitors()

    def _flash_monitors(self) -> None:
        m = self._selected_monitor()
        self._monitor_flash.show(
            self._monitors,
            selected_index=m.capture_index if m else None,
        )

    def _on_mode_changed(self) -> None:
        if not hasattr(self, "_window_widget"):
            return  # still building the UI
        mode = self._mode()
        self._monitor_row_widget.setVisible(mode in ("monitor", "region"))
        self._region_widget.setVisible(mode == "region")
        self._window_widget.setVisible(mode == "window")
        # The border only makes sense in region mode; show it there (if a region
        # is set), hide it otherwise. The region selection itself is preserved.
        if mode == "region" and self._region is not None:
            self._show_region_border()
        else:
            self._clear_region_border()
        self._refresh_estimate()

    def _refresh_estimate(self) -> None:
        self._fps_label.setText(f"{self._fps_slider.value()} Hz")
        crf = self._crf_slider.value()
        if crf <= 18:
            quality = "Visually lossless"
        elif crf <= 23:
            quality = "High quality"
        else:
            quality = "Smaller file"
        self._crf_label.setText(f"CRF {crf} · {quality}")

        fps = self._fps_slider.value()
        target_h = self._res_combo.currentData()
        src_w, src_h = self._source_size()
        region = self._region if self._mode() == "region" else None
        out_w, out_h = planned_output_size(src_w, src_h, region, target_h)
        est = estimate.estimate(out_w, out_h, fps, crf)
        self._estimate_label.setText(f"{out_w}×{out_h} @ {fps} Hz   →   {est.summary()}")

    # ----------------------------------------------------------------- region
    def _select_region(self) -> None:
        m = self._selected_monitor()
        screen = m.qt_screen if (m and m.qt_screen) else QGuiApplication.primaryScreen()
        if screen is None:
            QMessageBox.warning(self, "No screen", "Could not resolve the monitor to select on.")
            return
        self.hide()
        self._region_selector = RegionSelector(screen)
        self._region_selector.selected.connect(self._on_region_selected)
        self._region_selector.cancelled.connect(self._on_region_cancelled)
        self._region_selector.show_on_screen()

    def _on_region_selected(self, rect: Rect) -> None:
        self._region = rect
        self._region_label.setText(f"{rect.width}×{rect.height} at ({rect.x}, {rect.y})")
        self.show()
        self.raise_()
        self.activateWindow()
        self._refresh_estimate()
        self._show_region_border()

    def _show_region_border(self) -> None:
        self._clear_region_border()
        if self._region is None:
            return
        m = self._selected_monitor()
        screen = m.qt_screen if (m and m.qt_screen) else QGuiApplication.primaryScreen()
        if screen is None:
            return
        self._region_border = RegionBorder(screen, self._region)
        self._region_border.show_border()

    def _clear_region_border(self) -> None:
        if self._region_border is not None:
            self._region_border.close()
            self._region_border = None

    def _on_region_cancelled(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------------- file
    def _choose_file(self) -> None:
        suggested = self._resolve_output_path()
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Save recording",
            suggested,
            "MP4 Video (*.mp4);;Matroska Video (*.mkv)",
        )
        if path:
            if not path.lower().endswith((".mp4", ".mkv")):
                path += ".mkv" if "mkv" in selected.lower() else ".mp4"
            self._explicit_output = path
            # Remember the chosen folder + container as the new defaults.
            self._config.output_dir = os.path.dirname(path)
            self._config.container = "mkv" if path.lower().endswith(".mkv") else "mp4"
            self._update_file_label()

    def _open_last_file(self) -> None:
        if self._last_saved_path and os.path.exists(self._last_saved_path):
            os.startfile(self._last_saved_path)  # noqa: S606 (Windows file open)

    def _open_last_folder(self) -> None:
        if self._last_saved_path and os.path.exists(self._last_saved_path):
            # Open Explorer with the file selected.
            subprocess.run(["explorer", "/select,", os.path.normpath(self._last_saved_path)])

    # --------------------------------------------------------------- recording
    def _toggle_record(self) -> None:
        if self._recorder is None:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self) -> None:
        mode = self._mode()
        if mode == "region" and self._region is None:
            QMessageBox.warning(self, "No region", "Please select a region first.")
            return
        if mode == "window" and not self._window_combo.currentData():
            QMessageBox.warning(self, "No window", "No window selected.")
            return

        output_path = self._resolve_output_path()
        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        except OSError as exc:
            QMessageBox.critical(self, "Cannot save there", f"Could not create the output folder:\n{exc}")
            return

        # When timestamping is on, next_output_path() already returned a
        # collision-free path. Otherwise (fixed name or explicit Save to…),
        # confirm before silently clobbering an existing recording.
        if self._needs_overwrite_prompt(output_path) and os.path.exists(output_path):
            reply = QMessageBox.question(
                self,
                "Overwrite existing file?",
                f"{output_path}\nalready exists. Overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        m = self._selected_monitor()
        capture_index = m.capture_index if m else 1
        settings = RecordSettings(
            monitor_index=capture_index if mode in ("monitor", "region") else None,
            window_hwnd=self._window_combo.currentData() if mode == "window" else None,
            region=self._region if mode == "region" else None,
            target_height=self._res_combo.currentData(),
            fps=self._fps_slider.value(),
            crf=self._crf_slider.value(),
            use_nvenc=bool(self._enc_combo.currentData()),
            output_path=output_path,
        )
        self._recorder = self._recorder_factory(settings)
        try:
            self._recorder.start()
        except Exception as exc:  # noqa: BLE001
            self._recorder = None
            QMessageBox.critical(self, "Failed to start", str(exc))
            return

        # Keep the region border visible during recording (it's outside the
        # crop, so it isn't captured); ensure it's shown.
        if mode == "region":
            self._show_region_border()

        self._open_row_widget.setVisible(False)
        self._record_btn.setText("■ Stop recording")
        self._set_record_style(True)
        self._set_controls_enabled(False)
        self._stats_timer.start()

    def _stop_recording(self) -> None:
        self._stats_timer.stop()
        if self._recorder is None:
            return
        stats = self._recorder.stop()
        path = self._recorder.settings.output_path  # may be updated by remux fallback
        self._recorder = None
        self._record_btn.setText("● Start recording")
        self._set_record_style(False)
        self._set_controls_enabled(True)
        self._clear_region_border()   # border goes away when recording stops

        if stats.error:
            QMessageBox.critical(self, "Recording error", stats.error)
            self._stats_label.setText("Error during recording.")
            return

        self._last_saved_path = path
        size_mb = os.path.getsize(path) / 1_000_000 if os.path.exists(path) else 0
        self._stats_label.setText(
            f"Saved · {stats.encoded} frames · {stats.dropped} dropped · "
            f"{stats.measured_fps:.1f} Hz avg · {size_mb:.1f} MB"
        )
        self._open_row_widget.setVisible(True)
        if stats.notice:
            QMessageBox.information(self, "Note", stats.notice)

    def _update_stats(self) -> None:
        if self._recorder is None:
            return
        stats = self._recorder.stats
        if stats.error:
            self._stop_recording()
            return
        self._stats_label.setText(
            f"● REC   {stats.elapsed:5.1f}s    {stats.measured_fps:4.1f} Hz    "
            f"encoded {stats.encoded}    dropped {stats.dropped}"
        )

    def _set_record_style(self, recording: bool) -> None:
        self._record_btn.setProperty("recording", recording)
        self._record_btn.style().unpolish(self._record_btn)
        self._record_btn.style().polish(self._record_btn)
        # Recolor the stats line red while recording, normal otherwise.
        self._stats_label.setObjectName("statsRec" if recording else "stats")
        self._stats_label.style().unpolish(self._stats_label)
        self._stats_label.style().polish(self._stats_label)

    def _set_controls_enabled(self, enabled: bool) -> None:
        widgets = [
            self._monitor_combo, self._identify_btn, self._region_btn,
            self._window_combo, self._refresh_windows_btn, self._res_combo,
            self._fps_slider, self._crf_slider, self._enc_combo, self._file_btn,
        ]
        widgets += list(self._seg_buttons.values())
        for w in widgets:
            w.setEnabled(enabled)

    def closeEvent(self, event) -> None:  # noqa: ANN001
        if self._recorder is not None:
            self._recorder.stop()
            self._recorder = None
        self._clear_region_border()
        self._monitor_flash.clear()
        self._capture_config().save()   # remember settings for next launch
        event.accept()

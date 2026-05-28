"""Entry point: launch the screen recorder GUI."""

from __future__ import annotations

import ctypes
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .assets import icon_path
from .gui import MainWindow


def _set_app_user_model_id() -> None:
    """Give Windows a stable AppUserModelID so the taskbar uses our own icon
    and grouping instead of bundling under generic 'python.exe'."""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "screen-recorder.app.1"
        )
    except Exception:
        pass


def main() -> int:
    _set_app_user_model_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Screen Recorder")

    path = icon_path()
    if path:
        app.setWindowIcon(QIcon(path))

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

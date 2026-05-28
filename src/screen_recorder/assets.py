"""Locate bundled asset files (icon, etc.)."""

from __future__ import annotations

import os

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")


def icon_path() -> str | None:
    path = os.path.join(_ASSETS_DIR, "app.ico")
    return path if os.path.exists(path) else None

"""Persistent user settings and standard Windows paths.

Settings live in ``%APPDATA%\\ScreenRecorder\\config.json`` — the conventional
per-user location for app config on Windows (writable even when the app itself
is installed under a read-only directory). Recordings default to the user's
Videos folder. The app remembers the last-used settings by writing them back on
exit.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime

_APP_DIR_NAME = "ScreenRecorder"


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, _APP_DIR_NAME)


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def default_output_dir() -> str:
    """``%USERPROFILE%\\Videos\\ScreenRecorder`` (Videos is a Windows known folder)."""
    videos = os.path.join(os.path.expanduser("~"), "Videos")
    return os.path.join(videos, _APP_DIR_NAME)


_DEFAULT_BASE = "recording"
_INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def sanitize_base(name: str) -> str:
    """Clean a user-typed filename stem: strip whitespace, invalid Windows
    filename chars, and any ``.mp4``/``.mkv`` extension the user typed in.
    Falls back to ``"recording"`` if nothing useful is left."""
    s = (name or "").strip()
    if s.lower().endswith((".mp4", ".mkv")):
        s = s[:-4]
    s = "".join(c for c in s if c not in _INVALID_FILENAME_CHARS).strip()
    return s or _DEFAULT_BASE


def _timestamp() -> str:
    return f"{datetime.now():%Y-%m-%d_%H-%M-%S}"


@dataclass
class Config:
    """Remembered user preferences. Values are the *defaults* until overridden."""

    output_dir: str = ""           # filled from default_output_dir() if blank
    base_name: str = "recording"   # filename stem (before any timestamp + extension)
    resolution: int = 720          # target height in px
    fps: int = 30
    crf: int = 16
    use_nvenc: bool = False
    container: str = "mp4"         # "mp4" or "mkv" — power users edit JSON to switch
    append_timestamp: bool = True  # if True, suffix the base name with the current timestamp

    def __post_init__(self) -> None:
        if not self.output_dir:
            self.output_dir = default_output_dir()

    # ------------------------------------------------------------- persistence
    @classmethod
    def load(cls) -> "Config":
        """Read config.json; fall back to defaults for any missing/invalid file."""
        try:
            with open(config_path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        # Keep only known fields so an old/garbage file can't crash construction.
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        """Write config.json, creating the directory if needed. Best-effort."""
        try:
            os.makedirs(config_dir(), exist_ok=True)
            tmp = config_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
            os.replace(tmp, config_path())   # atomic on Windows
        except OSError:
            pass

    # --------------------------------------------------------------- helpers
    def next_output_path(self, exists: Callable[[str], bool] = os.path.exists) -> str:
        """Path the next recording should write to, given the current settings.

        Rule: ``<output_dir>/<base>[-<timestamp>].<container>``, with a
        ``-1``/``-2``/… suffix appended to make it collision-free. The
        ``append_timestamp`` flag is purely additive — it never replaces or
        removes any other part of the name.
        """
        base = sanitize_base(self.base_name)
        if self.append_timestamp:
            base = f"{base}-{_timestamp()}"
        path = os.path.join(self.output_dir, f"{base}.{self.container}")
        # Auto-suffix only when timestamping is on (two timestamped recordings
        # within the same second would otherwise collide). With timestamping
        # off, the user picked an exact name — preserve it and let the caller
        # decide whether to overwrite.
        if self.append_timestamp:
            path = _collision_free(path, exists)
        return path


def _collision_free(path: str, exists: Callable[[str], bool] = os.path.exists) -> str:
    """Return ``path`` if free, else ``path-1``, ``path-2``, … until one is."""
    if not exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 1
    while True:
        candidate = f"{stem}-{n}{ext}"
        if not exists(candidate):
            return candidate
        n += 1

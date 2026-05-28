"""Tier 1: config load/save and path helpers."""

from __future__ import annotations

import json
import os

from screen_recorder import config as cfgmod
from screen_recorder.config import Config


def test_defaults_fill_output_dir():
    c = Config()
    assert c.output_dir  # not blank
    assert c.output_dir.endswith("ScreenRecorder")
    assert c.resolution == 720 and c.fps == 30 and c.crf == 16


def test_roundtrip_save_load(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(cfgmod, "config_path", lambda: str(tmp_path / "config.json"))

    c = Config(output_dir=str(tmp_path / "vids"), resolution=1080, fps=60, crf=14, use_nvenc=True, container="mkv")
    c.save()
    loaded = Config.load()
    assert loaded.resolution == 1080
    assert loaded.fps == 60
    assert loaded.crf == 14
    assert loaded.use_nvenc is True
    assert loaded.container == "mkv"
    assert loaded.output_dir == str(tmp_path / "vids")


def test_load_missing_file_returns_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "config_path", lambda: str(tmp_path / "nope.json"))
    assert Config.load().fps == 30


def test_load_corrupt_file_returns_defaults(tmp_path, monkeypatch):
    bad = tmp_path / "config.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(cfgmod, "config_path", lambda: str(bad))
    assert Config.load().fps == 30


def test_load_ignores_unknown_keys(tmp_path, monkeypatch):
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"fps": 24, "bogus_field": 999}), encoding="utf-8")
    monkeypatch.setattr(cfgmod, "config_path", lambda: str(f))
    c = Config.load()
    assert c.fps == 24
    assert not hasattr(c, "bogus_field")


def test_next_output_path_is_timestamped_and_in_dir():
    c = Config(output_dir="C:\\vids", container="mp4")
    p = c.next_output_path()
    assert p.startswith("C:\\vids")
    assert p.endswith(".mp4")
    assert "recording-" in os.path.basename(p)


def test_container_drives_extension():
    assert Config(container="mkv").next_output_path().endswith(".mkv")
    assert Config(container="mp4").next_output_path().endswith(".mp4")


# ----------------------------------------------------- filename collisions

def test_timestamped_path_avoids_collision_within_same_second(tmp_path):
    """Two rapid recordings in the same second must NOT overwrite each other."""
    c = Config(output_dir=str(tmp_path), append_timestamp=True)
    first = c.next_output_path()
    # Simulate the first recording being on disk before the second request.
    open(first, "a").close()
    second = c.next_output_path()  # called within the same second
    assert second != first
    assert not os.path.exists(second)  # i.e. it's a free path, ready to use


def test_timestamped_path_keeps_incrementing_under_many_collisions(tmp_path):
    """If even the -1, -2, … candidates exist, we keep going until free."""
    c = Config(output_dir=str(tmp_path), append_timestamp=True)
    taken = {c.next_output_path() for _ in range(5)}
    # The Config doesn't know about taken paths by itself; simulate them on
    # disk and confirm the next call avoids every one.
    for p in taken:
        open(p, "a").close()
    fresh = c.next_output_path()
    assert fresh not in taken


def test_fixed_name_mode_returns_stable_path(tmp_path):
    """With timestamping off, the path is stable — caller must handle overwrite."""
    c = Config(output_dir=str(tmp_path), append_timestamp=False, container="mp4")
    p1 = c.next_output_path()
    p2 = c.next_output_path()
    assert p1 == p2
    assert p1.endswith("recording.mp4")


def test_append_timestamp_persists_through_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cfgmod, "config_dir", lambda: str(tmp_path))
    monkeypatch.setattr(cfgmod, "config_path", lambda: str(tmp_path / "config.json"))
    Config(append_timestamp=False).save()
    assert Config.load().append_timestamp is False

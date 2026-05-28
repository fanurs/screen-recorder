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

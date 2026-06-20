"""Tests for settings file persistence."""

import json
from pathlib import Path

import pytest

from lcstats_relay.core.config import (
    CONFIG_FILENAME,
    DEFAULT_TRACKER_URL,
    RelaySettings,
    SettingsStore,
    default_config_path,
)


def test_settings_store_returns_defaults_when_file_is_missing(tmp_path: Path) -> None:
    """Start with usable defaults before the user saves settings."""
    store = SettingsStore(tmp_path / "settings.json")

    assert store.load() == RelaySettings()


def test_settings_store_saves_and_loads_json(tmp_path: Path) -> None:
    """Persist safe settings without converting paths to plain strings in memory."""
    store = SettingsStore(tmp_path / "settings.json")
    settings = RelaySettings(
        tracker_url="http://localhost:2145/",
        gas_url="https://script.google.com/macros/s/id/exec",
        data_dir=tmp_path / "relay-data",
    )

    store.save(settings)

    assert store.load() == settings
    content = json.loads(store.path.read_text(encoding="utf-8"))
    assert content["tracker_url"] != DEFAULT_TRACKER_URL
    assert content["data_dir"] == str(tmp_path / "relay-data")


@pytest.mark.parametrize("content", ["[]", '{"tracker_url": 42}', "{"])
def test_settings_store_rejects_invalid_settings(tmp_path: Path, content: str) -> None:
    """Surface corrupt settings instead of silently discarding user input."""
    store = SettingsStore(tmp_path / "settings.json")
    store.path.write_text(content, encoding="utf-8")

    with pytest.raises((TypeError, ValueError), match="設定ファイル"):
        store.load()


def test_default_config_path_prefers_platform_locations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Choose a per-user config path without requiring callers to pass one."""
    app_data = tmp_path / "app-data"
    config_home = tmp_path / "xdg"
    monkeypatch.setenv("APPDATA", str(app_data))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    assert default_config_path() == app_data / "lcstats-relay" / CONFIG_FILENAME

    monkeypatch.delenv("APPDATA")
    assert default_config_path() == config_home / "lcstats-relay" / CONFIG_FILENAME

    monkeypatch.delenv("XDG_CONFIG_HOME")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert default_config_path() == tmp_path / ".config" / "lcstats-relay" / CONFIG_FILENAME

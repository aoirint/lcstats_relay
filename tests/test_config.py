"""Tests for settings file persistence."""

import json
from pathlib import Path

import pytest

from lcstats_relay.application.settings import (
    DEFAULT_TRACKER_URL,
    RelaySettings,
)
from lcstats_relay.infrastructure.config import (
    CONFIG_FILENAME,
    SettingsStore,
    default_config_path,
    default_data_dir,
)


def test_settings_store_returns_defaults_when_file_is_missing(*, tmp_path: Path) -> None:
    """Start with usable defaults before the user saves settings."""
    store = SettingsStore(path=tmp_path / "settings.json")

    assert store.load() == RelaySettings(data_dir=default_data_dir())


def test_settings_store_saves_and_loads_json(*, tmp_path: Path) -> None:
    """Persist safe settings without converting paths to plain strings in memory."""
    store = SettingsStore(path=tmp_path / "settings.json")
    settings = RelaySettings(
        tracker_url="http://localhost:2145/",
        gas_url="https://script.google.com/macros/s/id/exec",
        data_dir=tmp_path / "relay-data",
    )

    store.save(settings=settings)

    assert store.load() == settings
    content = json.loads(store.path.read_text(encoding="utf-8"))
    assert content["tracker_url"] != DEFAULT_TRACKER_URL
    assert content["data_dir"] == str(tmp_path / "relay-data")


@pytest.mark.parametrize("content", ["[]", '{"tracker_url": 42}', "{"])
def test_settings_store_rejects_invalid_settings(*, tmp_path: Path, content: str) -> None:
    """Surface corrupt settings instead of silently discarding user input."""
    store = SettingsStore(path=tmp_path / "settings.json")
    store.path.write_text(content, encoding="utf-8")

    with pytest.raises((TypeError, ValueError), match="設定ファイル"):
        store.load()


def test_default_config_path_prefers_platform_locations(
    *,
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


def test_default_data_dir_prefers_platform_locations(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Choose stable per-user data storage for new installations."""
    local_app_data = tmp_path / "local-app-data"
    data_home = tmp_path / "xdg-data"
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    assert default_data_dir() == local_app_data / "lcstats-relay" / "data"

    monkeypatch.delenv("LOCALAPPDATA")
    assert default_data_dir() == data_home / "lcstats-relay"

    monkeypatch.delenv("XDG_DATA_HOME")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert default_data_dir() == tmp_path / ".local" / "share" / "lcstats-relay"


def test_settings_store_uses_platform_data_default_for_legacy_file(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fill a missing legacy data directory without reverting to process-relative storage."""
    data_home = tmp_path / "xdg-data"
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    store = SettingsStore(path=tmp_path / "settings.json")
    store.path.write_text('{"tracker_url": "http://localhost:2145/"}', encoding="utf-8")

    assert store.load().data_dir == data_home / "lcstats-relay"

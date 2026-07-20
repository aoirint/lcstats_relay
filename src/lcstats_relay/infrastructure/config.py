"""Application settings persistence."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lcstats_relay.application.settings import (
    DEFAULT_TRACKER_URL,
    RelaySettings,
)
from lcstats_relay.infrastructure.filesystem import write_text_atomic

CONFIG_FILENAME = "settings.json"
_APP_DIRECTORY = "lcstats-relay"


def default_config_path() -> Path:
    """Return the per-user settings file path for the current platform."""
    app_data = os.environ.get("APPDATA")
    if app_data:
        return Path(app_data) / _APP_DIRECTORY / CONFIG_FILENAME

    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / _APP_DIRECTORY / CONFIG_FILENAME

    return Path.home() / ".config" / _APP_DIRECTORY / CONFIG_FILENAME


def default_data_dir() -> Path:
    """Return a stable per-user data root for new settings."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / _APP_DIRECTORY / "data"

    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / _APP_DIRECTORY

    return Path.home() / ".local" / "share" / _APP_DIRECTORY


class SettingsStore:
    """Load and save the relay settings JSON file."""

    def __init__(self, *, path: Path | None = None) -> None:
        """Use the supplied path or the platform default."""
        self.path = path or default_config_path()

    def load(self) -> RelaySettings:
        """Load settings, returning defaults when no file exists yet."""
        if not self.path.exists():
            return RelaySettings(data_dir=default_data_dir())

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = "設定ファイルを読み込めません"
            raise ValueError(msg) from exc

        if not isinstance(raw, dict):
            msg = "設定ファイルの形式が不正です"
            raise TypeError(msg)

        return RelaySettings(
            tracker_url=_string_value(raw=raw, key="tracker_url", default=DEFAULT_TRACKER_URL),
            gas_url=_string_value(raw=raw, key="gas_url", default=""),
            data_dir=Path(_string_value(raw=raw, key="data_dir", default=str(default_data_dir()))),
        )

    def save(self, *, settings: RelaySettings) -> None:
        """Persist settings atomically as readable JSON."""
        payload = asdict(settings)
        payload["data_dir"] = str(settings.data_dir)
        write_text_atomic(
            path=self.path,
            content=f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
        )


def _string_value(*, raw: dict[str, Any], key: str, default: str) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        msg = f"設定ファイルの{key}は文字列である必要があります"
        raise TypeError(msg)
    return value

"""Application settings persistence."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_TRACKER_URL = "http://127.0.0.1:2145/"
DEFAULT_DATA_DIR = Path("data")
CONFIG_FILENAME = "settings.json"


@dataclass(frozen=True, kw_only=True, slots=True)
class RelaySettings:
    """User-configurable relay settings safe to persist on disk."""

    tracker_url: str = DEFAULT_TRACKER_URL
    gas_url: str = ""
    data_dir: Path = DEFAULT_DATA_DIR


def default_config_path() -> Path:
    """Return the per-user settings file path for the current platform."""
    app_data = os.environ.get("APPDATA")
    if app_data:
        return Path(app_data) / "lcstats-relay" / CONFIG_FILENAME

    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "lcstats-relay" / CONFIG_FILENAME

    return Path.home() / ".config" / "lcstats-relay" / CONFIG_FILENAME


class SettingsStore:
    """Load and save the relay settings JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        """Use the supplied path or the platform default."""
        self.path = path or default_config_path()

    def load(self) -> RelaySettings:
        """Load settings, returning defaults when no file exists yet."""
        if not self.path.exists():
            return RelaySettings()

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"設定ファイルを読み込めません: {self.path}"
            raise ValueError(msg) from exc

        if not isinstance(raw, dict):
            msg = f"設定ファイルの形式が不正です: {self.path}"
            raise TypeError(msg)

        return RelaySettings(
            tracker_url=_string_value(raw, key="tracker_url", default=DEFAULT_TRACKER_URL),
            gas_url=_string_value(raw, key="gas_url", default=""),
            data_dir=Path(_string_value(raw, key="data_dir", default=str(DEFAULT_DATA_DIR))),
        )

    def save(self, settings: RelaySettings) -> None:
        """Persist settings atomically as readable JSON."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(settings)
        payload["data_dir"] = str(settings.data_dir)
        temporary = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary.write_text(
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)


def _string_value(raw: dict[str, Any], *, key: str, default: str) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        msg = f"設定ファイルの{key}は文字列である必要があります"
        raise TypeError(msg)
    return value

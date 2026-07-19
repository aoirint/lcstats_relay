"""Framework-free relay settings values."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_TRACKER_URL = "http://127.0.0.1:2145/"
DEFAULT_DATA_DIR = Path("data")


@dataclass(frozen=True, kw_only=True, slots=True)
class RelaySettings:
    """User-configurable relay settings safe to persist on disk."""

    tracker_url: str = DEFAULT_TRACKER_URL
    gas_url: str = ""
    data_dir: Path = DEFAULT_DATA_DIR

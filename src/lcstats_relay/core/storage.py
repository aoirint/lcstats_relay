"""Durable local archive and retry queue storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

type JSONValue = None | bool | int | float | str | list[JSONValue] | dict[str, JSONValue]


def parse_json(raw_json: str) -> JSONValue:
    """Parse a JSON value without leaking an untyped result."""
    return cast("JSONValue", json.loads(raw_json))


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


class ArchiveWriter:
    """Persist each received JSON payload before downstream processing."""

    def __init__(self, data_dir: Path) -> None:
        """Use the archive directory beneath the supplied application data root."""
        self._root = data_dir / "archive"

    def write(self, raw_json: str, *, received_at: datetime) -> Path:
        """Write the exact received JSON and return its archive path."""
        date_dir = self._root / received_at.strftime("%Y-%m-%d")
        filename = f"{received_at:%Y-%m-%dT%H-%M-%S-%f}-{uuid4().hex[:8]}.json"
        archive_path = date_dir / filename
        _write_atomic(archive_path, f"{raw_json}\n")
        return archive_path


@dataclass(frozen=True, slots=True)
class RetryItem:
    """One failed Sheets delivery stored for a later retry."""

    path: Path
    payload: JSONValue
    archive_file: str


class RetryQueue:
    """Store failed payloads as individual JSON files."""

    def __init__(self, data_dir: Path) -> None:
        """Use the queue directory beneath the supplied application data root."""
        self._root = data_dir / "queue"

    def enqueue(
        self,
        payload: JSONValue,
        *,
        archive_file: Path,
        queued_at: datetime,
    ) -> Path:
        """Persist a failed delivery and return the queue file path."""
        filename = f"{queued_at:%Y-%m-%dT%H-%M-%S-%f}-{uuid4().hex[:8]}.json"
        queue_path = self._root / filename
        record: dict[str, JSONValue] = {
            "queued_at": queued_at.isoformat(),
            "archive_file": str(archive_file),
            "payload": payload,
        }
        _write_atomic(queue_path, f"{json.dumps(record, ensure_ascii=False, indent=2)}\n")
        return queue_path

    def pending(self) -> list[RetryItem]:
        """Load pending deliveries in stable creation order."""
        if not self._root.exists():
            return []

        items: list[RetryItem] = []
        for path in sorted(self._root.glob("*.json")):
            record = parse_json(path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                msg = f"Retry queue record must be an object: {path.name}"
                raise TypeError(msg)
            archive_file = record.get("archive_file")
            if not isinstance(archive_file, str) or "payload" not in record:
                msg = f"Retry queue record is missing required fields: {path.name}"
                raise ValueError(msg)
            items.append(
                RetryItem(path=path, payload=record["payload"], archive_file=archive_file),
            )
        return items

    def remove(self, item: RetryItem) -> None:
        """Remove a successfully delivered queue item."""
        item.path.unlink(missing_ok=True)

    def count(self) -> int:
        """Return the number of queued deliveries without parsing them."""
        if not self._root.exists():
            return 0
        return sum(1 for _path in self._root.glob("*.json"))

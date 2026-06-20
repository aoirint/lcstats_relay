"""Durable local archive and retry queue storage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from lcstats_relay.core.payload import JSONValue, RelayPayload, parse_json


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
    """One failed output delivery stored for a later retry."""

    path: Path
    output_key: str
    payload: RelayPayload


class RetryQueue:
    """Store failed payloads as individual JSON files."""

    def __init__(self, data_dir: Path) -> None:
        """Use the queue directory beneath the supplied application data root."""
        self._root = data_dir / "queue"

    def enqueue(
        self,
        output_key: str,
        payload: RelayPayload,
        *,
        queued_at: datetime,
    ) -> Path:
        """Persist a failed delivery and return the queue file path."""
        filename = f"{queued_at:%Y-%m-%dT%H-%M-%S-%f}-{uuid4().hex[:8]}.json"
        queue_path = self._root / filename
        record: dict[str, JSONValue] = {
            "queued_at": queued_at.isoformat(),
            "output_key": output_key,
            "received_at": payload.received_at.isoformat(),
            "raw_json": payload.raw_json,
            "payload": payload.payload,
            "parse_error": payload.parse_error,
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
            if "payload" not in record:
                msg = f"Retry queue record is missing required fields: {path.name}"
                raise ValueError(msg)
            items.append(self._load_item(path, record))
        return items

    def remove(self, item: RetryItem) -> None:
        """Remove a successfully delivered queue item."""
        item.path.unlink(missing_ok=True)

    def count(self, output_key: str | None = None) -> int:
        """Return all queued deliveries or those belonging to one output."""
        if not self._root.exists():
            return 0
        if output_key is None:
            return sum(1 for _path in self._root.glob("*.json"))
        return sum(item.output_key == output_key for item in self.pending())

    @staticmethod
    def _load_item(path: Path, record: dict[str, JSONValue]) -> RetryItem:
        output_key = record.get("output_key", "gas")
        if not isinstance(output_key, str):
            msg = f"Retry queue output key must be a string: {path.name}"
            raise TypeError(msg)

        queued_at = record.get("queued_at")
        received_at = record.get("received_at", queued_at)
        if not isinstance(received_at, str):
            msg = f"Retry queue timestamp must be a string: {path.name}"
            raise TypeError(msg)
        try:
            received_datetime = datetime.fromisoformat(received_at)
        except ValueError as exc:
            msg = f"Retry queue timestamp is invalid: {path.name}"
            raise ValueError(msg) from exc

        payload = record["payload"]
        raw_json = record.get("raw_json")
        if not isinstance(raw_json, str):
            raw_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        parse_error = record.get("parse_error")
        if parse_error is not None and not isinstance(parse_error, str):
            msg = f"Retry queue parse error must be a string or null: {path.name}"
            raise TypeError(msg)
        return RetryItem(
            path=path,
            output_key=output_key,
            payload=RelayPayload(
                raw_json=raw_json,
                payload=payload,
                received_at=received_datetime,
                parse_error=parse_error,
            ),
        )

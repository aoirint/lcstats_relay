"""Durable local archive and retry queue storage."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from lcstats_relay.application.ports import RetryItem
from lcstats_relay.domain.payload import JSONValue, RelayPayload, parse_json
from lcstats_relay.infrastructure.filesystem import write_text_atomic


class ArchiveWriter:
    """Persist each received JSON payload before downstream processing."""

    def __init__(self, *, data_dir: Path) -> None:
        """Use the archive directory beneath the supplied application data root."""
        self._root = data_dir / "archive"

    def write(
        self, *, raw_json: str, received_at: datetime, correlation_id: str | None = None
    ) -> Path:
        """Write the exact received JSON and return its archive path."""
        date_dir = self._root / received_at.strftime("%Y-%m-%d")
        suffix = UUID(hex=correlation_id).hex if correlation_id else uuid4().hex[:8]
        filename = f"{received_at:%Y-%m-%dT%H-%M-%S-%f}-{suffix}.json"
        archive_path = date_dir / filename
        write_text_atomic(path=archive_path, content=f"{raw_json}\n")
        return archive_path


class RetryQueue:
    """Store failed payloads as individual JSON files."""

    def __init__(self, *, data_dir: Path) -> None:
        """Use the queue directory beneath the supplied application data root."""
        self._root = data_dir / "queue"

    def enqueue(
        self,
        *,
        output_key: str,
        payload: RelayPayload,
        queued_at: datetime,
    ) -> Path:
        """Persist a failed delivery and return the queue file path."""
        filename = f"{queued_at:%Y-%m-%dT%H-%M-%S-%f}-{uuid4().hex[:8]}.json"
        queue_path = self._root / filename
        record: dict[str, JSONValue] = {
            "correlation_id": payload.correlation_id,
            "queued_at": queued_at.isoformat(),
            "output_key": output_key,
            "received_at": payload.received_at.isoformat(),
            "raw_json": payload.raw_json,
            "payload": payload.payload,
            "parse_error": payload.parse_error,
        }
        write_text_atomic(
            path=queue_path,
            content=f"{json.dumps(record, ensure_ascii=False, indent=2)}\n",
        )
        return queue_path

    def pending(self) -> list[RetryItem]:
        """Load pending deliveries in stable creation order."""
        if not self._root.exists():
            return []

        items: list[RetryItem] = []
        for path in sorted(self._root.glob("*.json")):
            record = parse_json(raw_json=path.read_text(encoding="utf-8"))
            if not isinstance(record, dict):
                msg = f"Retry queue record must be an object: {path.name}"
                raise TypeError(msg)
            if (
                not {
                    "output_key",
                    "received_at",
                    "raw_json",
                    "payload",
                    "parse_error",
                    "correlation_id",
                }
                <= record.keys()
            ):
                msg = f"Retry queue record is missing required fields: {path.name}"
                raise ValueError(msg)
            items.append(self._load_item(path=path, record=record))
        return items

    def remove(self, *, item: RetryItem) -> None:
        """Remove a successfully delivered queue item."""
        Path(item.storage_key).unlink(missing_ok=True)

    def count(self, *, output_key: str | None = None) -> int:
        """Return all queued deliveries or those belonging to one output."""
        if not self._root.exists():
            return 0
        if output_key is None:
            return sum(1 for _path in self._root.glob("*.json"))
        return sum(item.output_key == output_key for item in self.pending())

    @staticmethod
    def _load_item(*, path: Path, record: dict[str, JSONValue]) -> RetryItem:
        output_key = record["output_key"]
        if not isinstance(output_key, str):
            msg = f"Retry queue output key must be a string: {path.name}"
            raise TypeError(msg)

        received_at = record["received_at"]
        if not isinstance(received_at, str):
            msg = f"Retry queue timestamp must be a string: {path.name}"
            raise TypeError(msg)
        try:
            received_datetime = datetime.fromisoformat(received_at)
        except ValueError as exc:
            msg = f"Retry queue timestamp is invalid: {path.name}"
            raise ValueError(msg) from exc

        raw_json = record["raw_json"]
        if not isinstance(raw_json, str):
            msg = f"Retry queue raw JSON must be a string: {path.name}"
            raise TypeError(msg)
        parse_error = record["parse_error"]
        if parse_error is not None and not isinstance(parse_error, str):
            msg = f"Retry queue parse error must be a string or null: {path.name}"
            raise TypeError(msg)
        correlation_id = record["correlation_id"]
        if not isinstance(correlation_id, str):
            msg = f"Retry queue correlation ID must be a string: {path.name}"
            raise TypeError(msg)
        try:
            correlation_id = UUID(hex=correlation_id).hex
        except ValueError as exc:
            msg = f"Retry queue correlation ID is invalid: {path.name}"
            raise ValueError(msg) from exc
        return RetryItem(
            storage_key=str(path),
            output_key=output_key,
            payload=RelayPayload(
                raw_json=raw_json,
                payload=record["payload"],
                received_at=received_datetime,
                parse_error=parse_error,
                correlation_id=correlation_id,
            ),
        )

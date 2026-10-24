"""Tests for archive and retry queue persistence."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lcstats_relay.domain.payload import JSONValue, RelayPayload, parse_json
from lcstats_relay.infrastructure import filesystem as filesystem_module
from lcstats_relay.infrastructure.storage import ArchiveWriter, RetryQueue


def test_archive_writer_preserves_raw_json(*, tmp_path: Path) -> None:
    """Store the exact received object in a date-partitioned archive."""
    received_at = datetime(2026, 6, 20, 9, 15, 33, tzinfo=UTC)
    path = ArchiveWriter(data_dir=tmp_path).write(raw_json='{"Seed":42}', received_at=received_at)

    assert path.parent == tmp_path / "archive" / "2026-06-20"
    assert path.read_text(encoding="utf-8") == '{"Seed":42}\n'


def test_retry_queue_round_trip(*, tmp_path: Path) -> None:
    """Load and remove a queued payload without changing its JSON value."""
    queue = RetryQueue(data_dir=tmp_path)
    received_at = datetime(2026, 6, 20, 10, 8, 12, tzinfo=UTC)
    payload = RelayPayload(
        raw_json='{"Seed":42,"Players":["player-1"]}',
        payload={"Seed": 42, "Players": ["player-1"]},
        received_at=received_at,
    )

    path = queue.enqueue(output_key="gas", payload=payload, queued_at=received_at)

    assert queue.count() == 1
    assert queue.count(output_key="gas") == 1
    assert queue.count(output_key="archive") == 0
    [item] = queue.pending()
    assert item.storage_key == str(path)
    assert item.output_key == "gas"
    assert item.payload == payload
    assert item.payload.correlation_id == payload.correlation_id
    assert (
        RetryQueue(data_dir=tmp_path).pending()[0].payload.correlation_id == payload.correlation_id
    )

    queue.remove(item=item)
    queue.remove(item=item)
    assert queue.pending() == []
    assert queue.count() == 0


_QUEUE_RECORD: dict[str, JSONValue] = {
    "output_key": "gas",
    "received_at": "2026-10-24T00:00:00+00:00",
    "raw_json": "{}",
    "payload": {},
    "parse_error": None,
    "correlation_id": "a" * 32,
}


@pytest.mark.parametrize(
    "record",
    [
        [],
        {},
        _QUEUE_RECORD | {"output_key": 123},
        _QUEUE_RECORD | {"received_at": 123},
        _QUEUE_RECORD | {"received_at": "not-a-date"},
        _QUEUE_RECORD | {"raw_json": 123},
        _QUEUE_RECORD | {"parse_error": 123},
        _QUEUE_RECORD | {"correlation_id": 123},
        _QUEUE_RECORD | {"correlation_id": "invalid"},
    ],
)
def test_retry_queue_rejects_invalid_record(*, tmp_path: Path, record: object) -> None:
    """Report incompatible or corrupt queue records without rewriting or deleting them."""
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    path = queue_dir / "invalid.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    original = path.read_bytes()
    with pytest.raises((TypeError, ValueError), match="Retry queue"):
        RetryQueue(data_dir=tmp_path).pending()
    assert path.read_bytes() == original


def test_parse_json_supports_scalar_values() -> None:
    """Keep valid JSON values rather than requiring a top-level object."""
    assert parse_json(raw_json="null") is None


def test_empty_retry_queue_does_not_create_directory(*, tmp_path: Path) -> None:
    """Read an empty queue without producing filesystem side effects."""
    queue = RetryQueue(data_dir=tmp_path)
    assert queue.pending() == []
    assert queue.count() == 0
    assert queue.count(output_key="gas") == 0


def test_atomic_write_cleans_unique_temporary_file_after_replace_failure(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Leave the previous final file intact and remove failed temporary output."""
    target = tmp_path / "settings.json"
    target.write_text("previous\n", encoding="utf-8")

    def fail_replace(  # noqa: PLR0917 -- keyword-only-exception: pathlib Path.replace method ABI
        source: Path, destination: str | Path
    ) -> None:
        del source, destination
        msg = "replace failed"
        raise OSError(msg)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        filesystem_module.write_text_atomic(path=target, content="next\n")

    assert target.read_text(encoding="utf-8") == "previous\n"
    assert list(tmp_path.glob(".*.tmp")) == []

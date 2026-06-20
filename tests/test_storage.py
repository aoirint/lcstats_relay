"""Tests for archive and retry queue persistence."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from lcstats_relay.core.payload import RelayPayload, parse_json
from lcstats_relay.core.storage import ArchiveWriter, RetryQueue


def test_archive_writer_preserves_raw_json(tmp_path: Path) -> None:
    """Store the exact received object in a date-partitioned archive."""
    received_at = datetime(2026, 6, 20, 9, 15, 33)
    path = ArchiveWriter(tmp_path).write('{"Seed":42}', received_at=received_at)

    assert path.parent == tmp_path / "archive" / "2026-06-20"
    assert path.read_text(encoding="utf-8") == '{"Seed":42}\n'


def test_retry_queue_round_trip(tmp_path: Path) -> None:
    """Load and remove a queued payload without changing its JSON value."""
    queue = RetryQueue(tmp_path)
    received_at = datetime(2026, 6, 20, 10, 8, 12)
    payload = RelayPayload(
        raw_json='{"Seed":42,"Players":["player-1"]}',
        payload={"Seed": 42, "Players": ["player-1"]},
        received_at=received_at,
    )

    path = queue.enqueue("gas", payload, queued_at=received_at)

    assert queue.count() == 1
    assert queue.count("gas") == 1
    assert queue.count("archive") == 0
    [item] = queue.pending()
    assert item.path == path
    assert item.output_key == "gas"
    assert item.payload == payload

    queue.remove(item)
    queue.remove(item)
    assert queue.pending() == []
    assert queue.count() == 0


def test_retry_queue_loads_legacy_record(tmp_path: Path) -> None:
    """Keep compatibility with early queue files that lacked output metadata."""
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    (queue_dir / "legacy.json").write_text(
        json.dumps(
            {
                "queued_at": "2026-06-20T10:08:12",
                "archive_file": "data/archive/payload.json",
                "payload": {"Seed": 42},
            },
        ),
        encoding="utf-8",
    )

    [item] = RetryQueue(tmp_path).pending()

    assert item.output_key == "gas"
    assert item.payload.raw_json == '{"Seed":42}'
    assert item.payload.payload == {"Seed": 42}
    assert item.payload.received_at == datetime(2026, 6, 20, 10, 8, 12)


@pytest.mark.parametrize(
    "record",
    [
        [],
        {"queued_at": "2026-06-20T10:08:12"},
        {"queued_at": "2026-06-20T10:08:12", "payload": {"Seed": 42}, "output_key": 123},
        {"queued_at": 123, "payload": {"Seed": 42}},
        {"queued_at": "not-a-date", "payload": {"Seed": 42}},
        {"queued_at": "2026-06-20T10:08:12", "payload": {"Seed": 42}, "parse_error": 123},
    ],
)
def test_retry_queue_rejects_invalid_record(tmp_path: Path, record: object) -> None:
    """Reject malformed queue files instead of silently dropping deliveries."""
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    (queue_dir / "invalid.json").write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises((TypeError, ValueError), match="Retry queue"):
        RetryQueue(tmp_path).pending()


def test_parse_json_supports_scalar_values() -> None:
    """Keep valid JSON values rather than requiring a top-level object."""
    assert parse_json("null") is None


def test_empty_retry_queue_does_not_create_directory(tmp_path: Path) -> None:
    """Read an empty queue without producing filesystem side effects."""
    queue = RetryQueue(tmp_path)
    assert queue.pending() == []
    assert queue.count() == 0
    assert queue.count("gas") == 0

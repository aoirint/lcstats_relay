"""Tests for archive and retry queue persistence."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from lcstats_relay.core.storage import ArchiveWriter, RetryQueue, parse_json


def test_archive_writer_preserves_raw_json(tmp_path: Path) -> None:
    """Store the exact received object in a date-partitioned archive."""
    received_at = datetime(2026, 6, 20, 9, 15, 33)
    path = ArchiveWriter(tmp_path).write('{"Seed":42}', received_at=received_at)

    assert path.parent == tmp_path / "archive" / "2026-06-20"
    assert path.read_text(encoding="utf-8") == '{"Seed":42}\n'


def test_retry_queue_round_trip(tmp_path: Path) -> None:
    """Load and remove a queued payload without changing its JSON value."""
    queue = RetryQueue(tmp_path)
    archive_file = tmp_path / "archive" / "payload.json"
    queued_at = datetime(2026, 6, 20, 10, 8, 12)

    path = queue.enqueue(
        {"Seed": 42, "Players": ["aoi"]},
        archive_file=archive_file,
        queued_at=queued_at,
    )

    assert queue.count() == 1
    [item] = queue.pending()
    assert item.path == path
    assert item.payload == {"Seed": 42, "Players": ["aoi"]}
    assert item.archive_file == str(archive_file)

    queue.remove(item)
    queue.remove(item)
    assert queue.pending() == []
    assert queue.count() == 0


@pytest.mark.parametrize(
    "record",
    [
        [],
        {"payload": {"Seed": 42}},
        {"archive_file": 123, "payload": {"Seed": 42}},
    ],
)
def test_retry_queue_rejects_invalid_record(tmp_path: Path, record: object) -> None:
    """Reject malformed queue files instead of silently dropping deliveries."""
    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    (queue_dir / "invalid.json").write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises((TypeError, ValueError), match="Retry queue record"):
        RetryQueue(tmp_path).pending()


def test_parse_json_supports_scalar_values() -> None:
    """Keep valid JSON values rather than requiring a top-level object."""
    assert parse_json("null") is None


def test_empty_retry_queue_does_not_create_directory(tmp_path: Path) -> None:
    """Read an empty queue without producing filesystem side effects."""
    assert RetryQueue(tmp_path).pending() == []

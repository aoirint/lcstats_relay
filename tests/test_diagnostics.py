"""Behavioral checks for private, bounded operational diagnostics."""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

import flet as ft
import httpx
import pytest

from lcstats_relay.application.diagnostics import LOGGER, emit
from lcstats_relay.application.dispatcher import OutputDispatcher
from lcstats_relay.application.ports import (
    BoundOutput,
    OutputPolicy,
    RetrySemantics,
)
from lcstats_relay.application.settings import RelaySettings
from lcstats_relay.application.state import ConnectionState, RelayStateStore
from lcstats_relay.composition.application import create_connection_manager
from lcstats_relay.domain.payload import JSONValue, RelayPayload
from lcstats_relay.entrypoints import flet_app
from lcstats_relay.infrastructure import diagnostics
from lcstats_relay.infrastructure.auth import NoAuthentication
from lcstats_relay.infrastructure.config import SettingsStore
from lcstats_relay.infrastructure.diagnostics import DiagnosticLog, default_log_dir
from lcstats_relay.infrastructure.outputs import ArchiveOutput, GasOutput
from lcstats_relay.infrastructure.storage import ArchiveWriter, RetryQueue


def _payload() -> RelayPayload:
    return RelayPayload(
        raw_json='{"Players":{"76561198000000000":"private-player"}}',
        payload={"Players": {"76561198000000000": "private-player"}},
        received_at=datetime(2026, 10, 24, tzinfo=UTC),
    )


def test_file_log_rejects_unstructured_and_third_party_secrets(*, tmp_path: Path) -> None:
    """Persist only the schema even if an exception or arbitrary field is supplied."""
    log = DiagnosticLog(directory=tmp_path)
    log.start()
    log.start()
    payload = _payload()
    try:
        emit(event="payload_received", correlation_id=payload.correlation_id)
        LOGGER.warning(
            "https://example.com/private?token=secret",
            "private-player",
            extra={
                "output": "private-player",
                "category": "secret",
                "correlation_id": payload.raw_json,
                "status_code": 900,
                "payload": payload.raw_json,
            },
            exc_info=True,
        )
        logging.getLogger("httpx").info("https://example.com/private?token=secret")
    finally:
        log.close()
        log.close()
    content = log.path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in content.splitlines()]
    assert [r["event"] for r in records] == [
        "application_started",
        "payload_received",
        "application_failed",
        "application_stopped",
    ]
    assert records[1]["correlation_id"] == payload.correlation_id
    assert all(r["timestamp"].endswith("+00:00") for r in records)
    assert len({r["session_id"] for r in records}) == 1
    for secret in ("secret", "private-player", "76561198000000000", "example.com", "Traceback"):
        assert secret not in content


def test_rotation_bounds_files_and_retains_newest_events(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Limit disk consumption while retaining complete newest JSONL records."""
    limit = 600
    monkeypatch.setattr(diagnostics, "MAX_LOG_BYTES", limit)
    log = DiagnosticLog(directory=tmp_path)
    log.start()
    try:
        for _ in range(40):
            emit(event="receive_waiting")
    finally:
        log.close()
    files = list(tmp_path.glob("relay.jsonl*"))
    assert len(files) == diagnostics.LOG_BACKUPS + 1
    assert all(p.stat().st_size <= limit for p in files)
    for p in files:
        assert all(
            json.loads(line)["event"] in ("receive_waiting", "application_stopped")
            for line in p.read_text(encoding="utf-8").splitlines()
        )
    assert (
        json.loads(log.path.read_text(encoding="utf-8").splitlines()[-1])["event"]
        == "application_stopped"
    )


def test_log_creation_failure_keeps_diagnostics_available(*, tmp_path: Path) -> None:
    """Report an unavailable log destination without preventing Relay operation."""
    blocked = tmp_path / "file"
    blocked.write_text("occupied", encoding="utf-8")
    log = DiagnosticLog(directory=blocked)
    log.start()
    assert log.failed
    assert "書き込み失敗" in log.describe(data_dir=Path("data"))
    assert str((Path("data") / "archive").resolve()) in log.describe(data_dir=Path("data"))
    log.close()


def test_rollover_failure_is_visible_without_exception_text(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Suppress logging's traceback fallback when disk operations fail."""
    monkeypatch.setattr(diagnostics, "MAX_LOG_BYTES", 1)

    def fail_rename(  # keyword-only-exception: os.rename ABI
        *_args: object, **_kwargs: object
    ) -> None:
        msg = "secret URL https://example.com/private"
        raise OSError(msg)

    monkeypatch.setattr(os, "rename", fail_rename)
    log = DiagnosticLog(directory=tmp_path)
    log.start()
    try:
        emit(event="payload_received")
        assert log.failed
    finally:
        log.close()
    assert capsys.readouterr().err == ""


def test_log_location_uses_stable_user_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Place logs independently from the editable archive destination."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_log_dir() == tmp_path / "lcstats-relay" / "logs"
    monkeypatch.delenv("LOCALAPPDATA")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_log_dir() == tmp_path / "lcstats-relay" / "logs"


@pytest.mark.parametrize(
    ("content_type", "body", "category", "status"),
    [
        (
            "text/html",
            "<html>Error: Invalid token (line 10) private-player</html>",
            "authentication",
            200,
        ),
        ("text/html", "<html>private-player</html>", "response_format", 200),
        ("application/json", "{broken private-player", "json_parse", 200),
        ("application/json", '{"ok":false,"error":"private-player"}', "application", 200),
        ("application/json", '{"ok":1}', "application", 200),
        ("application/json", "[]", "application", 200),
        ("text/plain", "private-player", "authentication", 401),
        ("text/plain", "private-player", "authentication", 403),
        ("text/plain", "private-player", "http", 503),
    ],
)
def test_gas_application_errors_remain_queued_and_private(
    *, tmp_path: Path, content_type: str, body: str, category: str, status: int
) -> None:
    """HTTP 200 does not remove a queue entry until GAS acknowledges success."""

    async def scenario() -> None:
        responses = [
            httpx.Response(status, text=body, headers={"content-type": content_type}),
            httpx.Response(200, json={"ok": True}),
        ]

        def handle(  # keyword-only-exception: httpx.MockTransport handler ABI
            _request: httpx.Request,
        ) -> httpx.Response:
            return responses.pop(0)

        log = DiagnosticLog(directory=tmp_path / "logs")
        log.start()
        try:
            queue = RetryQueue(data_dir=tmp_path)
            payload = _payload()
            queue.enqueue(output_key="gas", payload=payload, queued_at=payload.received_at)
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                dispatcher = OutputDispatcher(
                    outputs=[
                        BoundOutput(
                            policy=OutputPolicy(
                                key="gas", label="GAS", retry_semantics=RetrySemantics.AT_LEAST_ONCE
                            ),
                            sink=GasOutput(
                                url="https://example.com/private?token=secret",
                                client=client,
                                authenticator=NoAuthentication(),
                            ),
                        )
                    ],
                    queue=queue,
                    state=RelayStateStore(outputs=[("gas", "GAS")], on_change=_ignore_state),
                )
                await dispatcher.retry_pending()
                assert queue.count() == 1
                await dispatcher.retry_pending()
                assert queue.count() == 0
        finally:
            log.close()
        content = log.path.read_text(encoding="utf-8")
        records = [json.loads(line) for line in content.splitlines()]
        failures = [r for r in records if r["event"] == "output_failed"]
        assert failures[0]["category"] == category
        if status != HTTPStatus.OK:
            assert failures[0]["status_code"] == status
        assert failures[0]["correlation_id"] == payload.correlation_id
        assert sum(r["event"] == "output_succeeded" for r in records) == 1
        assert records[-2]["event"] == "retry_removed"
        for secret in ("private-player", "76561198000000000", "example.com", "token", body):
            assert secret not in content

    asyncio.run(scenario())


def test_runtime_failure_propagates_and_closes_log(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Preserve runtime failure propagation while flushing the diagnostic sink."""
    log = DiagnosticLog(directory=tmp_path)
    monkeypatch.setattr(flet_app, "_diagnostics", log)

    def fail(_target: object) -> None:  # keyword-only-exception: flet.run target ABI
        msg = "private-player"
        raise RuntimeError(msg)

    monkeypatch.setattr(ft, "run", fail)
    with pytest.raises(RuntimeError, match="private-player"):
        flet_app.run()
    content = log.path.read_text(encoding="utf-8")
    assert "application_stopped" in content
    assert "private-player" not in content


def _ignore_state(*, state: ConnectionState) -> None:
    del state


def test_delivered_item_stays_queued_when_removal_fails(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Distinguish remote success from failure to persist queue removal."""

    async def scenario() -> None:
        queue = RetryQueue(data_dir=tmp_path)
        payload = _payload()
        queue.enqueue(output_key="archive", payload=payload, queued_at=payload.received_at)

        def fail_remove(*, item: object) -> None:
            del item
            msg = "secret disk path"
            raise OSError(msg)

        monkeypatch.setattr(queue, "remove", fail_remove)
        log = DiagnosticLog(directory=tmp_path / "logs")
        log.start()
        try:
            dispatcher = OutputDispatcher(
                outputs=[
                    BoundOutput(
                        policy=OutputPolicy(key="archive", label="Archive"),
                        sink=ArchiveOutput(writer=ArchiveWriter(data_dir=tmp_path)),
                    )
                ],
                queue=queue,
                state=RelayStateStore(outputs=[("archive", "Archive")], on_change=_ignore_state),
            )
            with pytest.raises(OSError, match="secret"):
                await dispatcher.retry_pending()
            assert queue.count() == 1
        finally:
            log.close()
        content = log.path.read_text(encoding="utf-8")
        assert "output_succeeded" in content
        assert "retry_remove_failed" in content
        assert "secret" not in content

    asyncio.run(scenario())


def test_settings_write_failure_is_classified(*, tmp_path: Path) -> None:
    """Persist safe failure metadata when settings cannot be replaced."""
    log = DiagnosticLog(directory=tmp_path / "logs")
    log.start()
    try:
        with pytest.raises(OSError, match=tmp_path.name):
            SettingsStore(path=tmp_path).save(settings=RelaySettings())
    finally:
        log.close()
    content = log.path.read_text(encoding="utf-8")
    assert "settings_failed" in content
    assert "settings_saved" not in content


def _ignore_payload(*, payload: JSONValue) -> None:
    del payload


def test_close_failure_does_not_interrupt_shutdown(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep application cleanup safe if the final flush fails."""
    log = DiagnosticLog(directory=tmp_path)
    log.start()
    [handler] = [h for h in LOGGER.handlers if isinstance(h, logging.FileHandler)]

    def fail_flush() -> None:
        msg = "private disk path"
        raise OSError(msg)

    with monkeypatch.context() as patch:
        patch.setattr(handler, "flush", fail_flush)
        log.close()
    assert log.failed
    assert handler not in LOGGER.handlers


def test_production_receive_archive_queue_events_share_identity(*, tmp_path: Path) -> None:
    """Trace the real receiver and output adapters without retaining sensitive data."""

    async def scenario() -> None:
        received = False
        blocked = asyncio.Event()
        queued = asyncio.Event()
        raw = _payload().raw_json

        async def handle(  # noqa: PLR0917 -- keyword-only-exception: httpx MockTransport ABI
            request: httpx.Request,
        ) -> httpx.Response:
            nonlocal received
            if request.method == "POST":
                return httpx.Response(
                    200,
                    text="Error: Invalid token private-player",
                    headers={"content-type": "text/html"},
                )
            if not received:
                received = True
                return httpx.Response(200, text=f"data: {raw}\n\n")
            await blocked.wait()
            return httpx.Response(200)

        def client_factory(*, timeout: httpx.Timeout) -> httpx.AsyncClient:
            return httpx.AsyncClient(timeout=timeout, transport=httpx.MockTransport(handle))

        def state_changed(*, state: ConnectionState) -> None:
            if state.outputs["gas"].pending_count:
                queued.set()

        log = DiagnosticLog(directory=tmp_path / "logs")
        log.start()
        manager = create_connection_manager(
            sse_url="http://localhost:2145/?private=secret",
            gas_url="https://example.com/private-deployment/exec",
            gas_token="secret",  # noqa: S106 - inert fixture, never sent to a live service.
            data_dir=tmp_path,
            on_state=state_changed,
            on_payload=_ignore_payload,
            client_factory=client_factory,
        )
        try:
            manager.start()
            await asyncio.wait_for(queued.wait(), timeout=2)
        finally:
            await manager.stop()
            log.close()
        content = log.path.read_text(encoding="utf-8")
        records = [json.loads(line) for line in content.splitlines()]
        events = [r["event"] for r in records]
        assert events.index("connection_started") < events.index("receive_connected")
        assert events.index("payload_received") < events.index("output_succeeded")
        assert events.index("output_failed") < events.index("queue_saved")
        assert events[-2:] == ["connection_stopped", "application_stopped"]
        [item] = RetryQueue(data_dir=tmp_path).pending()
        ids = {r["correlation_id"] for r in records if "correlation_id" in r}
        assert ids == {item.payload.correlation_id}
        [archive] = (tmp_path / "archive").rglob("*.json")
        assert archive.stem.endswith(item.payload.correlation_id)
        assert archive.read_text(encoding="utf-8") == raw + "\n"
        for private in ("secret", "private", "76561198000000000", "example.com", "localhost", raw):
            assert private not in content

    asyncio.run(scenario())

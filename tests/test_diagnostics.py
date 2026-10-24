"""Operational checks for retained logs, delivery tracing and private metadata."""

import asyncio
import logging
import re
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path

import flet as ft
import httpx
import pytest

from lcstats_relay.application.diagnostics import emit
from lcstats_relay.application.dispatcher import OutputDispatcher
from lcstats_relay.application.ports import BoundOutput, OutputPolicy, RetrySemantics
from lcstats_relay.application.settings import RelaySettings
from lcstats_relay.application.state import ConnectionState, RelayStateStore
from lcstats_relay.composition.application import create_connection_manager
from lcstats_relay.domain.payload import JSONValue, RelayPayload
from lcstats_relay.entrypoints import flet_app
from lcstats_relay.infrastructure.auth import NoAuthentication
from lcstats_relay.infrastructure.config import SettingsStore
from lcstats_relay.infrastructure.diagnostics import default_log_dir, logging_session
from lcstats_relay.infrastructure.outputs import ArchiveOutput, GasOutput
from lcstats_relay.infrastructure.storage import ArchiveWriter, RetryQueue


def _payload() -> RelayPayload:
    return RelayPayload(
        raw_json='{"Players":{"76561198000000000":"private-player"}}',
        payload={"Players": {"76561198000000000": "private-player"}},
        received_at=datetime(2026, 10, 24, tzinfo=UTC),
    )


def test_logs_survive_reopening_without_duplicate_handlers(*, tmp_path: Path) -> None:
    """Retain earlier runs and emit each operational event only once."""
    events = ("receive_waiting", "receive_connected")
    for event in events:
        with logging_session(directory=tmp_path):
            emit(event=event)
    content = (tmp_path / "relay.log").read_text(encoding="utf-8")
    assert content.count("event=application_started") == len(events)
    assert content.count("event=application_stopped") == len(events)
    assert content.count("event=receive_waiting") == 1
    assert content.count("event=receive_connected") == 1
    assert content.split()[0].endswith("Z")


def test_unavailable_file_falls_back_to_console(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Keep Relay running and leave an explanation when its file cannot open."""
    blocked = tmp_path / "blocked"
    blocked.write_text("occupied", encoding="utf-8")
    with logging_session(directory=blocked):
        emit(event="receive_waiting")
    content = capsys.readouterr().err
    assert "event=log_file_unavailable" in content
    assert "event=receive_waiting" in content
    assert "event=application_stopped" in content
    assert str(tmp_path) not in content


def test_default_log_location(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep operational logs stable when the archive setting changes."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_log_dir() == tmp_path / "lcstats-relay" / "logs"
    monkeypatch.delenv("LOCALAPPDATA")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert default_log_dir() == tmp_path / "lcstats-relay" / "logs"


def test_runtime_failure_propagates_and_closes_log(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep unexpected runtime errors observable and flush the final event."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    def fail(_target: object) -> None:  # keyword-only-exception: Flet target ABI
        msg = "private-player"
        raise RuntimeError(msg)

    monkeypatch.setattr(ft, "run", fail)
    with pytest.raises(RuntimeError, match="private-player"):
        flet_app.run()
    content = (default_log_dir() / "relay.log").read_text(encoding="utf-8")
    assert "application_stopped" in content
    assert "private-player" not in content


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

        with logging_session(directory=tmp_path / "logs"):
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
        content = (tmp_path / "logs" / "relay.log").read_text(encoding="utf-8")
        records = content.splitlines()
        failures = [line for line in records if "event=output_failed " in line]
        assert f"category={category}" in failures[0]
        if status != HTTPStatus.OK:
            assert f"http={status}" in failures[0]
        assert f"id={payload.correlation_id}" in failures[0]
        assert content.count("event=output_succeeded ") == 1
        assert "event=retry_removed " in records[-2]
        for secret in ("private-player", "76561198000000000", "example.com", "token", body):
            assert secret not in content

    asyncio.run(scenario())


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
        with logging_session(directory=tmp_path / "logs"):
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
        content = (tmp_path / "logs" / "relay.log").read_text(encoding="utf-8")
        assert "output_succeeded" in content
        assert "retry_remove_failed" in content
        assert "secret" not in content

    asyncio.run(scenario())


def test_settings_write_failure_is_classified(*, tmp_path: Path) -> None:
    """Persist safe failure metadata when settings cannot be replaced."""
    with (
        logging_session(directory=tmp_path / "logs"),
        pytest.raises(OSError, match=tmp_path.name),
    ):
        SettingsStore(path=tmp_path).save(settings=RelaySettings())
    content = (tmp_path / "logs" / "relay.log").read_text(encoding="utf-8")
    assert "settings_failed" in content
    assert "settings_saved" not in content


def _ignore_state(*, state: ConnectionState) -> None:
    del state


def _ignore_payload(*, payload: JSONValue) -> None:
    del payload


def test_production_receive_archive_queue_events_share_identity(
    *, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Trace the real receiver and output adapters without retaining sensitive data."""
    caplog.set_level(logging.INFO)

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

        with logging_session(directory=tmp_path / "logs"):
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
        content = (tmp_path / "logs" / "relay.log").read_text(encoding="utf-8")
        records = content.splitlines()
        events = [line.split("event=", 1)[1].split()[0] for line in records]
        assert events.index("connection_started") < events.index("receive_connected")
        assert events.index("payload_received") < events.index("output_succeeded")
        assert events.index("output_failed") < events.index("queue_saved")
        assert events[-2:] == ["connection_stopped", "application_stopped"]
        [item] = RetryQueue(data_dir=tmp_path).pending()
        ids = set(re.findall(r"\bid=([0-9a-f]{32})\b", content))
        assert ids == {item.payload.correlation_id}
        [archive] = (tmp_path / "archive").rglob("*.json")
        assert archive.stem.endswith(item.payload.correlation_id)
        assert archive.read_text(encoding="utf-8") == raw + "\n"
        for private in ("secret", "private", "76561198000000000", "example.com", "localhost", raw):
            assert private not in content

    asyncio.run(scenario())

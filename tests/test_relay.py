"""Tests for receive, archive, send, and retry coordination."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from lcstats_relay.core.relay import (
    ConnectionManager,
    ConnectionState,
    RelayStatus,
    SheetSender,
    _make_client,
)
from lcstats_relay.core.storage import JSONValue, RetryQueue

_EXPECTED_RETRY_REQUESTS = 2


async def _wait_for(predicate: Callable[[], bool]) -> None:
    for _attempt in range(200):
        if predicate():
            return
        await asyncio.sleep(0.005)
    msg = "Timed out waiting for relay state"
    raise AssertionError(msg)


class _TransportHandler:
    def __init__(self, *, first_post_status: int = 200, payload: str = '{"Seed":42}') -> None:
        self.first_post_status = first_post_status
        self.payload = payload
        self.get_count = 0
        self.post_count = 0
        self.blocked = asyncio.Event()

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            self.post_count += 1
            status = self.first_post_status if self.post_count == 1 else 200
            return httpx.Response(status, request=request)

        self.get_count += 1
        if self.get_count == 1:
            return httpx.Response(200, text=f"data: {self.payload}\n\n", request=request)
        await self.blocked.wait()
        return httpx.Response(200, text="", request=request)


def _client_factory(handler: _TransportHandler) -> Callable[[httpx.Timeout], httpx.AsyncClient]:
    def create(_timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return create


def test_manager_archives_and_sends_payload(tmp_path: Path) -> None:
    """Archive each payload before forwarding it and waiting for the next response."""

    async def scenario() -> None:
        handler = _TransportHandler()
        states: list[ConnectionState] = []
        payloads: list[JSONValue] = []
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            gas_url="https://example.invalid/exec?token=secret",
            data_dir=tmp_path,
            on_state=states.append,
            on_payload=payloads.append,
            reconnect_delay=0.001,
            retry_interval=60,
            clock=lambda: datetime(2026, 6, 20, 9, 15, 33),
            client_factory=_client_factory(handler),
        )

        manager.start()
        manager.start()
        await _wait_for(lambda: manager.state.send_count == 1)
        await manager.stop()

        assert payloads == [{"Seed": 42}]
        assert manager.state.receive_count == 1
        assert manager.state.archive_count == 1
        assert manager.state.send_count == 1
        assert manager.state.queue_count == 0
        assert manager.state.status is RelayStatus.STOPPED
        assert any(state.status is RelayStatus.ARCHIVED for state in states)
        [archive] = (tmp_path / "archive" / "2026-06-20").glob("*.json")
        assert archive.read_text(encoding="utf-8") == '{"Seed":42}\n'

    asyncio.run(scenario())


def test_manager_retries_failed_delivery(tmp_path: Path) -> None:
    """Persist a failed delivery and remove it after a later successful retry."""

    async def scenario() -> None:
        handler = _TransportHandler(first_post_status=503)
        states: list[ConnectionState] = []
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            gas_url="https://example.invalid/exec?token=secret",
            data_dir=tmp_path,
            on_state=states.append,
            on_payload=lambda _payload: None,
            retry_interval=0.01,
            client_factory=_client_factory(handler),
        )

        manager.start()
        await _wait_for(lambda: any(state.status is RelayStatus.RETRY_QUEUED for state in states))
        queued_state = next(state for state in states if state.status is RelayStatus.RETRY_QUEUED)
        assert queued_state.last_error == "Sheets送信エラー: HTTP 503"
        await _wait_for(lambda: manager.state.status is RelayStatus.SENT)
        await manager.stop()

        assert handler.post_count == _EXPECTED_RETRY_REQUESTS
        assert manager.state.send_count == 1
        assert manager.state.queue_count == 0
        assert RetryQueue(tmp_path).pending() == []

    asyncio.run(scenario())


def test_manager_archives_invalid_json_without_sending(tmp_path: Path) -> None:
    """Keep malformed source data in the archive and report a parse error."""

    async def scenario() -> None:
        handler = _TransportHandler(payload="not-json")
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            gas_url="https://example.invalid/exec?token=secret",
            data_dir=tmp_path,
            on_state=lambda _state: None,
            on_payload=lambda _payload: None,
            retry_interval=60,
            client_factory=_client_factory(handler),
        )

        manager.start()
        await _wait_for(
            lambda: manager.state.last_error == "JSON解析エラー: JSONDecodeError",
        )
        await manager.stop()

        assert handler.post_count == 0
        assert manager.state.archive_count == 1

    asyncio.run(scenario())


def test_manager_can_stop_before_start(tmp_path: Path) -> None:
    """Treat stop as idempotent even before network work starts."""

    async def scenario() -> None:
        states: list[ConnectionState] = []
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            gas_url="https://example.invalid/exec",
            data_dir=tmp_path,
            on_state=states.append,
            on_payload=lambda _payload: None,
        )
        await manager.stop()
        assert states[-1].status is RelayStatus.STOPPED

    asyncio.run(scenario())


def test_manager_reconnects_after_receive_error(tmp_path: Path) -> None:
    """Report a failed request without terminating the receive loop."""
    request_count = 0
    blocked = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        if request_count == 1:
            return httpx.Response(503, request=request)
        if request_count == _EXPECTED_RETRY_REQUESTS:
            return httpx.Response(200, text='data: {"Seed":42}\n\n', request=request)
        await blocked.wait()
        return httpx.Response(200, request=request)

    async def scenario() -> None:
        states: list[ConnectionState] = []
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            gas_url="https://example.invalid/exec",
            data_dir=tmp_path,
            on_state=states.append,
            on_payload=lambda _payload: None,
            reconnect_delay=0,
            client_factory=lambda _timeout: httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
            ),
        )
        manager.start()
        await _wait_for(lambda: any(state.status is RelayStatus.ERROR for state in states))
        await _wait_for(lambda: manager.state.receive_count == 1)
        await manager.stop()

        error_state = next(state for state in states if state.status is RelayStatus.ERROR)
        assert error_state.last_error == "受信エラー: HTTP 503"

    asyncio.run(scenario())


def test_manager_reports_archive_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Do not send a consumed payload when durable archiving fails."""

    async def scenario() -> None:
        handler = _TransportHandler()
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            gas_url="https://example.invalid/exec",
            data_dir=tmp_path,
            on_state=lambda _state: None,
            on_payload=lambda _payload: None,
            client_factory=_client_factory(handler),
        )

        def fail_archive(_raw_json: str, *, received_at: datetime) -> Path:
            del received_at
            msg = "disk full"
            raise OSError(msg)

        monkeypatch.setattr(manager._archive, "write", fail_archive)
        manager.start()
        await _wait_for(lambda: manager.state.last_error == "アーカイブエラー: OSError")
        await manager.stop()
        assert handler.post_count == 0

    asyncio.run(scenario())


def test_manager_reports_queue_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Surface a queue disk failure after a Sheets delivery error."""

    async def scenario() -> None:
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            gas_url="https://example.invalid/exec",
            data_dir=tmp_path,
            on_state=lambda _state: None,
            on_payload=lambda _payload: None,
        )

        def fail_enqueue(
            _payload: JSONValue,
            *,
            archive_file: Path,
            queued_at: datetime,
        ) -> Path:
            del archive_file, queued_at
            msg = "disk full"
            raise OSError(msg)

        monkeypatch.setattr(manager._queue, "enqueue", fail_enqueue)
        transport = httpx.MockTransport(lambda _request: httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as client:
            sender = SheetSender("https://example.invalid/exec", client)
            await manager._send_or_queue(sender, {"Seed": 42}, tmp_path / "archive.json")

        assert manager.state.last_error == "再送キュー保存エラー: OSError"

    asyncio.run(scenario())


def test_retry_loop_reports_queue_and_send_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep retry-loop failures observable while retaining queued data."""

    async def scenario() -> None:
        states: list[ConnectionState] = []
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            gas_url="https://example.invalid/exec",
            data_dir=tmp_path,
            on_state=states.append,
            on_payload=lambda _payload: None,
            retry_interval=0.001,
        )
        transport = httpx.MockTransport(lambda _request: httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as client:
            sender = SheetSender("https://example.invalid/exec", client)

            def fail_pending() -> list[object]:
                msg = "invalid queue"
                raise TypeError(msg)

            original_pending = manager._queue.pending
            monkeypatch.setattr(manager._queue, "pending", fail_pending)
            queue_task = asyncio.create_task(manager._retry_loop(sender))
            await _wait_for(lambda: manager.state.last_error == "再送キュー読込エラー: TypeError")
            queue_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await queue_task

            monkeypatch.setattr(manager._queue, "pending", original_pending)
            manager._queue.enqueue(
                {"Seed": 42},
                archive_file=tmp_path / "archive.json",
                queued_at=datetime(2026, 6, 20),
            )
            send_task = asyncio.create_task(manager._retry_loop(sender))
            await _wait_for(lambda: manager.state.last_error == "再送エラー: HTTP 503")
            send_task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await send_task

        assert manager._queue.count() == 1
        assert any(state.last_error == "再送エラー: HTTP 503" for state in states)

    asyncio.run(scenario())


def test_send_and_retry_propagate_cancellation(tmp_path: Path) -> None:
    """Let cancellation stop both delivery paths immediately."""

    async def cancel_request(_request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    async def scenario() -> None:
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            gas_url="https://example.invalid/exec",
            data_dir=tmp_path,
            on_state=lambda _state: None,
            on_payload=lambda _payload: None,
            retry_interval=0,
        )
        manager._queue.enqueue(
            {"Seed": 42},
            archive_file=tmp_path / "archive.json",
            queued_at=datetime(2026, 6, 20),
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(cancel_request)) as client:
            sender = SheetSender("https://example.invalid/exec", client)
            with pytest.raises(asyncio.CancelledError):
                await manager._send_or_queue(sender, {"Seed": 42}, tmp_path / "archive.json")
            with pytest.raises(asyncio.CancelledError):
                await manager._retry_loop(sender)

    asyncio.run(scenario())


def test_preview_truncates_long_payload() -> None:
    """Keep event log previews bounded."""
    preview = ConnectionManager._preview("x" * 301)
    assert preview == f"{'x' * 300}..."


def test_default_client_factory_uses_supplied_timeout() -> None:
    """Create the production client with the manager timeout."""

    async def scenario() -> None:
        timeout = httpx.Timeout(30)
        async with _make_client(timeout) as client:
            assert client.timeout == timeout

    asyncio.run(scenario())

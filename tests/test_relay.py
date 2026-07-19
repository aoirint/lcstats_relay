"""Tests for manager, dispatcher, outputs, authentication, and state."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from lcstats_relay.app.composition import create_connection_manager
from lcstats_relay.core.auth import NoAuthentication, QueryTokenAuthentication
from lcstats_relay.core.dispatcher import BoundOutput, OutputDispatcher
from lcstats_relay.core.outputs import (
    ArchiveOutput,
    GasOutput,
    OutputDeliveryError,
    OutputReceipt,
    OutputRegistration,
)
from lcstats_relay.core.payload import JSONValue, RelayPayload
from lcstats_relay.core.relay import ConnectionManager, _make_client
from lcstats_relay.core.state import (
    ConnectionState,
    OutputStatus,
    RelayStateStore,
    RelayStatus,
)
from lcstats_relay.core.storage import ArchiveWriter, RetryQueue

_EXPECTED_RETRY_REQUESTS = 2


async def _wait_for(predicate: Callable[[], bool]) -> None:
    for _attempt in range(200):
        if predicate():
            return
        await asyncio.sleep(0.005)
    msg = "Timed out waiting for relay state"
    raise AssertionError(msg)


@dataclass
class _Sink:
    name: str
    calls: list[str]
    fail: OutputDeliveryError | None = None

    async def deliver(self, payload: RelayPayload) -> OutputReceipt:
        self.calls.append(self.name)
        if self.fail is not None:
            raise self.fail
        return OutputReceipt(message=f"{self.name} ok {payload.raw_json}")


class _TransportHandler:
    def __init__(self, *, first_post_status: int = 200, payload: str = '{"Seed":42}') -> None:
        self.first_post_status = first_post_status
        self.payload = payload
        self.get_count = 0
        self.post_count = 0
        self.last_request_url: str | None = None
        self.blocked = asyncio.Event()

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.last_request_url = str(request.url)
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


def _payload(raw_json: str = '{"Seed":42}') -> RelayPayload:
    return RelayPayload(
        raw_json=raw_json,
        payload={"Seed": 42},
        received_at=datetime(2026, 6, 20, 9, 15, 33, tzinfo=UTC),
    )


def test_authentication_policies_mutate_requests_independently() -> None:
    """Keep request credentials separate from GAS delivery implementation."""
    request = httpx.Request("POST", "https://script.google.com/macros/s/id/exec")
    NoAuthentication().apply(request)
    assert str(request.url) == "https://script.google.com/macros/s/id/exec"

    QueryTokenAuthentication("secret").apply(request)
    assert str(request.url) == "https://script.google.com/macros/s/id/exec?token=secret"


def test_archive_output_writes_raw_payload(tmp_path: Path) -> None:
    """ArchiveOutput owns archive-specific success text and persistence."""

    async def scenario() -> None:
        output = ArchiveOutput(ArchiveWriter(tmp_path))
        receipt = await output.deliver(_payload())

        [archive] = (tmp_path / "archive" / "2026-06-20").glob("*.json")
        assert archive.read_text(encoding="utf-8") == '{"Seed":42}\n'
        assert receipt.message.startswith("保存しました:")

    asyncio.run(scenario())


def test_archive_output_reports_safe_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Expose archive failure without leaking filesystem details."""

    async def scenario() -> None:
        writer = ArchiveWriter(tmp_path)

        def fail_write(_raw_json: str, *, received_at: datetime) -> Path:
            del received_at
            msg = "disk full"
            raise OSError(msg)

        monkeypatch.setattr(writer, "write", fail_write)
        with pytest.raises(OutputDeliveryError, match="ローカル保存"):
            await ArchiveOutput(writer).deliver(_payload())

    asyncio.run(scenario())


def test_gas_output_sends_authenticated_payload() -> None:
    """GasOutput handles delivery while auth stays injectable."""

    async def scenario() -> None:
        handler = _TransportHandler()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            output = GasOutput(
                "https://script.google.com/macros/s/id/exec",
                client=client,
                authenticator=QueryTokenAuthentication("secret"),
            )
            receipt = await output.deliver(_payload())

        assert receipt.message == "Google Sheetsへ送信しました"
        assert handler.post_count == 1
        assert handler.last_request_url is not None
        assert "token=secret" in handler.last_request_url

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("transport_error", "message"),
    [
        (httpx.Response(503), "HTTP 503"),
        (httpx.ConnectError("offline"), "ConnectError"),
    ],
)
def test_gas_output_reports_retryable_failures(
    transport_error: httpx.Response | httpx.HTTPError,
    message: str,
) -> None:
    """Convert HTTP client failures to safe retryable output errors."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(transport_error, httpx.Response):
            transport_error.request = request
            return transport_error
        raise transport_error

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            output = GasOutput(
                "https://script.google.com/macros/s/id/exec",
                client=client,
                authenticator=NoAuthentication(),
            )
            with pytest.raises(OutputDeliveryError, match=message) as error:
                await output.deliver(_payload())
            assert error.value.retryable is True

    asyncio.run(scenario())


def test_gas_output_rejects_unparsed_payload() -> None:
    """Do not send malformed JSON to GAS."""

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200))
        ) as client:
            output = GasOutput(
                "https://script.google.com/macros/s/id/exec",
                client=client,
                authenticator=NoAuthentication(),
            )
            with pytest.raises(OutputDeliveryError, match="JSONを解析"):
                await output.deliver(
                    RelayPayload(
                        raw_json="not-json",
                        payload=None,
                        received_at=datetime(2026, 6, 20, tzinfo=UTC),
                        parse_error="JSONDecodeError",
                    ),
                )

    asyncio.run(scenario())


def test_dispatcher_handles_success_required_failure_and_queue(tmp_path: Path) -> None:
    """Dispatch outputs generically and stop after a required output failure."""

    async def scenario() -> None:
        calls: list[str] = []
        states: list[ConnectionState] = []
        state = RelayStateStore(
            [("archive", "ローカル保存"), ("gas", "Google Sheets"), ("third", "Third")],
            on_change=states.append,
        )
        archive = _Sink(
            "archive",
            calls,
            fail=OutputDeliveryError("archive failed", retryable=False),
        )
        gas = _Sink("gas", calls)
        dispatcher = OutputDispatcher(
            [
                BoundOutput(
                    registration=OutputRegistration(
                        key="archive",
                        label="ローカル保存",
                        build=lambda _client: archive,
                        required=True,
                    ),
                    sink=archive,
                ),
                BoundOutput(
                    registration=OutputRegistration(
                        key="gas",
                        label="Google Sheets",
                        build=lambda _client: gas,
                    ),
                    sink=gas,
                ),
            ],
            queue=RetryQueue(tmp_path),
            state=state,
            clock=lambda: datetime(2026, 6, 20, tzinfo=UTC),
        )

        await dispatcher.dispatch(_payload())

        assert calls == ["archive"]
        assert state.state.outputs["archive"].status is OutputStatus.ERROR
        assert state.state.outputs["gas"].status is OutputStatus.IDLE

        calls.clear()
        archive.fail = None
        gas.fail = OutputDeliveryError("gas offline", retryable=True)
        await dispatcher.dispatch(_payload())

        assert calls == ["archive", "gas"]
        assert state.state.outputs["archive"].success_count == 1
        assert state.state.outputs["gas"].pending_count == 1
        assert RetryQueue(tmp_path).count("gas") == 1

    asyncio.run(scenario())


def test_dispatcher_retries_known_outputs_and_skips_unknown(tmp_path: Path) -> None:
    """Retry queue entries by output key instead of hard-coding GAS."""

    async def scenario() -> None:
        calls: list[str] = []
        state = RelayStateStore(
            [("gas", "Google Sheets")],
            on_change=lambda _state: None,
        )
        gas = _Sink("gas", calls)
        queue = RetryQueue(tmp_path)
        queued_at = datetime(2026, 6, 20, tzinfo=UTC)
        queue.enqueue("gas", payload=_payload(), queued_at=queued_at)
        queue.enqueue("missing", payload=_payload('{"Seed":43}'), queued_at=queued_at)
        dispatcher = OutputDispatcher(
            [
                BoundOutput(
                    registration=OutputRegistration(
                        key="gas",
                        label="Google Sheets",
                        build=lambda _client: gas,
                    ),
                    sink=gas,
                )
            ],
            queue=queue,
            state=state,
            clock=lambda: queued_at,
        )

        await dispatcher.retry_pending()

        assert calls == ["gas"]
        assert queue.count("gas") == 0
        assert queue.count("missing") == 1

        gas.fail = OutputDeliveryError("still offline", retryable=True)
        queue.enqueue("gas", payload=_payload(), queued_at=queued_at)
        await dispatcher.retry_pending()
        assert state.state.outputs["gas"].message == "still offline"

    asyncio.run(scenario())


def test_dispatcher_reports_queue_write_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep output-specific failure visible when retry persistence fails too."""

    async def scenario() -> None:
        calls: list[str] = []
        state = RelayStateStore(
            [("gas", "Google Sheets")],
            on_change=lambda _state: None,
        )
        gas = _Sink("gas", calls, fail=OutputDeliveryError("gas offline", retryable=True))
        queue = RetryQueue(tmp_path)

        def fail_enqueue(output_key: str, *, payload: RelayPayload, queued_at: datetime) -> Path:
            del output_key, payload, queued_at
            msg = "disk full"
            raise OSError(msg)

        monkeypatch.setattr(queue, "enqueue", fail_enqueue)
        dispatcher = OutputDispatcher(
            [
                BoundOutput(
                    registration=OutputRegistration(
                        key="gas",
                        label="Google Sheets",
                        build=lambda _client: gas,
                    ),
                    sink=gas,
                )
            ],
            queue=queue,
            state=state,
            clock=lambda: datetime(2026, 6, 20, tzinfo=UTC),
        )

        await dispatcher.dispatch(_payload())

        assert state.state.outputs["gas"].status is OutputStatus.ERROR
        assert (
            state.state.outputs["gas"].message == "gas offline / 再送キューの保存にも失敗しました"
        )

    asyncio.run(scenario())


def test_manager_dispatches_received_payload_to_registered_outputs(tmp_path: Path) -> None:
    """ConnectionManager receives input and delegates outputs by registration."""

    async def scenario() -> None:
        handler = _TransportHandler()
        calls: list[str] = []
        states: list[ConnectionState] = []
        payloads: list[JSONValue] = []
        archive = _Sink("archive", calls)
        gas = _Sink("gas", calls)
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            outputs=[
                OutputRegistration(
                    key="archive",
                    label="ローカル保存",
                    build=lambda _client: archive,
                    required=True,
                ),
                OutputRegistration(
                    key="gas",
                    label="Google Sheets",
                    build=lambda _client: gas,
                ),
            ],
            data_dir=tmp_path,
            on_state=states.append,
            on_payload=payloads.append,
            retry_interval=60,
            clock=lambda: datetime(2026, 6, 20, 9, 15, 33, tzinfo=UTC),
            client_factory=_client_factory(handler),
        )

        manager.start()
        manager.start()
        await _wait_for(lambda: manager.state.outputs["gas"].success_count == 1)
        await manager.stop()

        assert calls == ["archive", "gas"]
        assert payloads == [{"Seed": 42}]
        assert manager.state.status is RelayStatus.STOPPED
        assert any(state.status is RelayStatus.DISPATCHING for state in states)

    asyncio.run(scenario())


def test_manager_archives_invalid_json_without_payload_callback(tmp_path: Path) -> None:
    """Malformed JSON remains dispatchable to archive while GAS can reject it."""

    async def scenario() -> None:
        handler = _TransportHandler(payload="not-json")
        calls: list[str] = []
        payloads: list[JSONValue] = []
        archive = _Sink("archive", calls)
        gas = _Sink(
            "gas",
            calls,
            fail=OutputDeliveryError(
                "JSONを解析できないため送信しません: JSONDecodeError", retryable=False
            ),
        )
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            outputs=[
                OutputRegistration(
                    key="archive",
                    label="ローカル保存",
                    build=lambda _client: archive,
                    required=True,
                ),
                OutputRegistration(
                    key="gas",
                    label="Google Sheets",
                    build=lambda _client: gas,
                ),
            ],
            data_dir=tmp_path,
            on_state=lambda _state: None,
            on_payload=payloads.append,
            retry_interval=60,
            client_factory=_client_factory(handler),
        )

        manager.start()
        await _wait_for(lambda: manager.state.outputs["gas"].failure_count == 1)
        await manager.stop()

        assert calls == ["archive", "gas"]
        assert payloads == []
        assert manager.state.outputs["archive"].success_count == 1
        assert manager.state.outputs["gas"].status is OutputStatus.ERROR

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
        sleeps: list[float] = []

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            outputs=[],
            data_dir=tmp_path,
            on_state=states.append,
            on_payload=lambda _payload: None,
            reconnect_delay=3,
            reconnect_sleep=sleep,
            client_factory=lambda _timeout: httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
            ),
        )
        manager.start()
        await _wait_for(lambda: any(state.status is RelayStatus.ERROR for state in states))
        await _wait_for(lambda: manager.state.receive_count == 1)
        await manager.stop()

        error_states = [state for state in states if state.status is RelayStatus.ERROR]
        assert [state.retry_after_seconds for state in error_states] == [3, 2, 1]
        assert {state.last_error for state in error_states} == {"受信エラー: HTTP 503"}
        assert sleeps == [1.0, 1.0, 1.0]
        assert request_count >= _EXPECTED_RETRY_REQUESTS

    asyncio.run(scenario())


def test_retry_loop_reports_queue_read_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep retry queue parsing failures observable outside output states."""

    async def scenario() -> None:
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            outputs=[],
            data_dir=tmp_path,
            on_state=lambda _state: None,
            on_payload=lambda _payload: None,
            retry_interval=0.001,
        )

        async def retry_once() -> None:
            dispatcher = OutputDispatcher(
                [],
                queue=manager._queue,
                state=manager._state,
            )
            await manager._retry_loop(dispatcher)

        def fail_pending() -> list[object]:
            msg = "invalid queue"
            raise TypeError(msg)

        monkeypatch.setattr(manager._queue, "pending", fail_pending)
        task = asyncio.create_task(retry_once())
        await _wait_for(lambda: manager.state.last_error == "再送キュー読込エラー: TypeError")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_retry_loop_propagates_dispatcher_cancellation(tmp_path: Path) -> None:
    """Let dispatcher cancellation stop the retry loop immediately."""

    class CancellingDispatcher:
        async def retry_pending(self) -> None:
            raise asyncio.CancelledError

    async def scenario() -> None:
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            outputs=[],
            data_dir=tmp_path,
            on_state=lambda _state: None,
            on_payload=lambda _payload: None,
            retry_interval=0,
        )
        with pytest.raises(asyncio.CancelledError):
            await manager._retry_loop(CancellingDispatcher())  # type: ignore[arg-type]

    asyncio.run(scenario())


def test_stop_before_start_and_cancellation_paths(tmp_path: Path) -> None:
    """Treat stop as idempotent and propagate delivery cancellation."""

    async def scenario() -> None:
        states: list[ConnectionState] = []
        manager = ConnectionManager(
            sse_url="http://localhost:2145/",
            outputs=[],
            data_dir=tmp_path,
            on_state=states.append,
            on_payload=lambda _payload: None,
        )
        await manager.stop()
        assert states[-1].status is RelayStatus.STOPPED

        class CancelSink:
            async def deliver(self, _payload: RelayPayload) -> OutputReceipt:
                raise asyncio.CancelledError

        dispatcher = OutputDispatcher(
            [
                BoundOutput(
                    registration=OutputRegistration(
                        key="gas",
                        label="Google Sheets",
                        build=lambda _client: CancelSink(),
                    ),
                    sink=CancelSink(),
                )
            ],
            queue=RetryQueue(tmp_path),
            state=RelayStateStore(
                [("gas", "Google Sheets")],
                on_change=lambda _state: None,
            ),
        )
        with pytest.raises(asyncio.CancelledError):
            await dispatcher.dispatch(_payload())

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


def test_app_composition_builds_standard_outputs(tmp_path: Path) -> None:
    """Assemble archive, GAS, and auth without putting those details in the UI."""
    manager = create_connection_manager(
        sse_url="http://localhost:2145/",
        gas_url="https://script.google.com/macros/s/id/exec",
        gas_token="secret",  # noqa: S106 - inert test fixture, not a credential.
        data_dir=tmp_path,
        on_state=lambda _state: None,
        on_payload=lambda _payload: None,
    )

    assert isinstance(manager, ConnectionManager)
    assert list(manager.state.outputs) == ["archive", "gas"]

    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200)),
        ) as client:
            gas_output = manager._outputs[1].build(client)
            assert isinstance(gas_output, GasOutput)

    asyncio.run(scenario())


def test_app_composition_omits_gas_output_when_url_is_empty(tmp_path: Path) -> None:
    """Keep archive-only connections available without Google Sheets settings."""
    manager = create_connection_manager(
        sse_url="http://localhost:2145/",
        gas_url="",
        gas_token="",
        data_dir=tmp_path,
        on_state=lambda _state: None,
        on_payload=lambda _payload: None,
    )

    assert isinstance(manager, ConnectionManager)
    assert list(manager.state.outputs) == ["archive"]

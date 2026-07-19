"""Tests for manager, dispatcher, outputs, authentication, and state."""

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from lcstats_relay.application.dispatcher import OutputDispatcher
from lcstats_relay.application.ports import (
    BoundOutput,
    OutputDeliveryError,
    OutputPolicy,
    OutputReceipt,
    RelayRuntime,
    RetrySemantics,
)
from lcstats_relay.application.relay import ConnectionManager, RetryWorker, preview_payload
from lcstats_relay.application.state import (
    ConnectionState,
    OutputStatus,
    RelayStateStore,
    RelayStatus,
)
from lcstats_relay.composition.application import create_connection_manager
from lcstats_relay.domain.payload import JSONValue, RelayPayload
from lcstats_relay.infrastructure.auth import NoAuthentication, QueryTokenAuthentication
from lcstats_relay.infrastructure.outputs import ArchiveOutput, GasOutput
from lcstats_relay.infrastructure.runtime import (
    HttpOutputBinding,
    HttpRelayRuntime,
    make_http_client,
)
from lcstats_relay.infrastructure.storage import ArchiveWriter, RetryQueue

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


@dataclass(frozen=True, kw_only=True)
class _SinkFactory:
    sink: _Sink

    def __call__(self, _client: httpx.AsyncClient) -> _Sink:
        return self.sink


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


def _runtime_factory(
    handler: _TransportHandler,
    outputs: Sequence[tuple[OutputPolicy, _Sink]],
) -> Callable[[], RelayRuntime]:
    bindings = tuple(
        HttpOutputBinding(
            policy=policy,
            build=_SinkFactory(sink=sink),
        )
        for policy, sink in outputs
    )

    def create() -> RelayRuntime:
        return HttpRelayRuntime(
            sse_url="http://localhost:2145/",
            outputs=bindings,
            client_factory=_client_factory(handler),
        )

    return create


def _unused_runtime() -> RelayRuntime:
    msg = "runtime should not be opened by this test"
    raise AssertionError(msg)


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


def test_gas_output_bounds_total_request_time() -> None:
    """Bound GAS delivery even though the shared SSE client has no read timeout."""

    async def handler(_request: httpx.Request) -> httpx.Response:
        await asyncio.Event().wait()
        return httpx.Response(200)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            output = GasOutput(
                "https://script.google.com/macros/s/id/exec",
                client=client,
                authenticator=NoAuthentication(),
                request_timeout_seconds=0.001,
            )
            with pytest.raises(OutputDeliveryError, match="TimeoutError") as error:
                await output.deliver(_payload())
            assert error.value.retryable is True

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
                    policy=OutputPolicy(
                        key="archive",
                        label="ローカル保存",
                        required=True,
                    ),
                    sink=archive,
                ),
                BoundOutput(
                    policy=OutputPolicy(
                        key="gas",
                        label="Google Sheets",
                        retry_semantics=RetrySemantics.AT_LEAST_ONCE,
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
                    policy=OutputPolicy(
                        key="gas",
                        label="Google Sheets",
                        retry_semantics=RetrySemantics.AT_LEAST_ONCE,
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
                    policy=OutputPolicy(
                        key="gas",
                        label="Google Sheets",
                        retry_semantics=RetrySemantics.AT_LEAST_ONCE,
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
        archive_policy = OutputPolicy(
            key="archive",
            label="ローカル保存",
            required=True,
        )
        gas_policy = OutputPolicy(key="gas", label="Google Sheets")
        manager = ConnectionManager(
            output_policies=[archive_policy, gas_policy],
            runtime_factory=_runtime_factory(
                handler,
                [(archive_policy, archive), (gas_policy, gas)],
            ),
            retry_queue=RetryQueue(tmp_path),
            on_state=states.append,
            on_payload=payloads.append,
            retry_interval=60,
            clock=lambda: datetime(2026, 6, 20, 9, 15, 33, tzinfo=UTC),
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
        archive_policy = OutputPolicy(
            key="archive",
            label="ローカル保存",
            required=True,
        )
        gas_policy = OutputPolicy(key="gas", label="Google Sheets")
        manager = ConnectionManager(
            output_policies=[archive_policy, gas_policy],
            runtime_factory=_runtime_factory(
                handler,
                [(archive_policy, archive), (gas_policy, gas)],
            ),
            retry_queue=RetryQueue(tmp_path),
            on_state=lambda _state: None,
            on_payload=payloads.append,
            retry_interval=60,
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
            output_policies=[],
            runtime_factory=lambda: HttpRelayRuntime(
                sse_url="http://localhost:2145/",
                outputs=[],
                client_factory=lambda _timeout: httpx.AsyncClient(
                    transport=httpx.MockTransport(handler),
                ),
            ),
            retry_queue=RetryQueue(tmp_path),
            on_state=states.append,
            on_payload=lambda _payload: None,
            reconnect_delay=3,
            reconnect_sleep=sleep,
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
        queue = RetryQueue(tmp_path)
        state = RelayStateStore(
            [],
            on_change=lambda _state: None,
        )
        dispatcher = OutputDispatcher([], queue=queue, state=state)
        worker = RetryWorker(
            dispatcher=dispatcher,
            state=state,
            interval=0.001,
        )

        def fail_pending() -> list[object]:
            msg = "invalid queue"
            raise TypeError(msg)

        monkeypatch.setattr(queue, "pending", fail_pending)
        task = asyncio.create_task(worker.run_forever())
        await _wait_for(lambda: state.state.last_error == "再送キュー読込エラー: TypeError")
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_manager_keeps_running_after_initial_queue_read_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report startup queue corruption without abandoning the receiver session."""

    async def scenario() -> None:
        handler = _TransportHandler()
        states: list[ConnectionState] = []
        queue = RetryQueue(tmp_path)
        original_count = queue.count
        attempts = 0

        def fail_once(output_key: str | None = None) -> int:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                msg = "invalid queue"
                raise ValueError(msg)
            return original_count(output_key)

        monkeypatch.setattr(queue, "count", fail_once)
        archive_policy = OutputPolicy(
            key="archive",
            label="ローカル保存",
            required=True,
        )
        manager = ConnectionManager(
            output_policies=[archive_policy],
            runtime_factory=_runtime_factory(handler, [(archive_policy, _Sink("archive", []))]),
            retry_queue=queue,
            on_state=states.append,
            on_payload=lambda _payload: None,
            retry_interval=60,
        )

        manager.start()
        await _wait_for(lambda: manager.state.receive_count == 1)
        await manager.stop()

        assert any(state.last_error == "再送キュー読込エラー: ValueError" for state in states)

    asyncio.run(scenario())


def test_retry_loop_propagates_dispatcher_cancellation() -> None:
    """Let dispatcher cancellation stop the retry loop immediately."""

    class CancellingDispatcher:
        async def retry_pending(self) -> None:
            raise asyncio.CancelledError

    async def scenario() -> None:
        worker = RetryWorker(
            dispatcher=CancellingDispatcher(),
            state=RelayStateStore([], on_change=lambda _state: None),
            interval=0,
        )
        with pytest.raises(asyncio.CancelledError):
            await worker.run_forever()

    asyncio.run(scenario())


def test_stop_before_start_and_cancellation_paths(tmp_path: Path) -> None:
    """Treat stop as idempotent and propagate delivery cancellation."""

    async def scenario() -> None:
        states: list[ConnectionState] = []
        manager = ConnectionManager(
            output_policies=[],
            runtime_factory=_unused_runtime,
            retry_queue=RetryQueue(tmp_path),
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
                    policy=OutputPolicy(
                        key="gas",
                        label="Google Sheets",
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
    preview = preview_payload("x" * 301)
    assert preview == f"{'x' * 300}..."


def test_default_client_factory_uses_supplied_timeout() -> None:
    """Create the production client with the manager timeout."""

    async def scenario() -> None:
        timeout = httpx.Timeout(30)
        async with make_http_client(timeout) as client:
            assert client.timeout == timeout

    asyncio.run(scenario())


def test_app_composition_builds_standard_outputs(tmp_path: Path) -> None:
    """Assemble archive, GAS, and auth without putting those details in the UI."""
    handler = _TransportHandler()
    manager = create_connection_manager(
        sse_url="http://localhost:2145/",
        gas_url="https://script.google.com/macros/s/id/exec",
        gas_token="secret",  # noqa: S106 - inert test fixture, not a credential.
        data_dir=tmp_path,
        on_state=lambda _state: None,
        on_payload=lambda _payload: None,
        client_factory=_client_factory(handler),
    )

    assert isinstance(manager, ConnectionManager)
    assert list(manager.state.outputs) == ["archive", "gas"]

    async def scenario() -> None:
        manager.start()
        await _wait_for(lambda: manager.state.outputs["gas"].success_count == 1)
        await manager.stop()

    asyncio.run(scenario())
    assert handler.post_count == 1


def test_http_runtime_exit_before_entry_is_a_noop() -> None:
    """Keep cleanup safe if an owner unwinds before opening resources."""

    async def scenario() -> None:
        runtime = HttpRelayRuntime(sse_url="https://example.com/events", outputs=[])
        await runtime.__aexit__(None, None, None)

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

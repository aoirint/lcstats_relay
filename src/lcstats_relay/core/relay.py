"""Coordinate input receiving and implementation-independent output dispatch."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import httpx

from lcstats_relay.core.dispatcher import BoundOutput, OutputDispatcher
from lcstats_relay.core.outputs import OutputRegistration
from lcstats_relay.core.payload import JSONValue, RelayPayload, parse_json
from lcstats_relay.core.receiver import StatsReceiver
from lcstats_relay.core.state import ConnectionState, RelayStateStore, StateCallback
from lcstats_relay.core.storage import RetryQueue

type PayloadCallback = Callable[[JSONValue], None]
type Clock = Callable[[], datetime]
type ClientFactory = Callable[[httpx.Timeout], httpx.AsyncClient]

_PREVIEW_LENGTH = 300


def _make_client(timeout: httpx.Timeout) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)


class ConnectionManager:
    """Own input and retry loops while delegating every output to registrations."""

    def __init__(  # noqa: PLR0913 - callbacks and timing seams keep layers decoupled.
        self,
        *,
        sse_url: str,
        outputs: Sequence[OutputRegistration],
        data_dir: Path,
        on_state: StateCallback,
        on_payload: PayloadCallback,
        reconnect_delay: float = 3.0,
        retry_interval: float = 30.0,
        clock: Clock = datetime.now,
        client_factory: ClientFactory = _make_client,
    ) -> None:
        """Configure input, output registrations, state, persistence, and timing."""
        self._sse_url = sse_url
        self._outputs = tuple(outputs)
        self._queue = RetryQueue(data_dir)
        self._on_payload = on_payload
        self._reconnect_delay = reconnect_delay
        self._retry_interval = retry_interval
        self._clock = clock
        self._client_factory = client_factory
        self._task: asyncio.Task[None] | None = None
        pending = {output.key: self._queue.count(output.key) for output in self._outputs}
        self._state = RelayStateStore(
            ((output.key, output.label) for output in self._outputs),
            on_state,
            pending_counts=pending,
        )

    @property
    def state(self) -> ConnectionState:
        """Expose the current state for synchronous UI inspection."""
        return self._state.state

    def start(self) -> None:
        """Start the manager once; repeated calls while running are ignored."""
        if self._task is not None and not self._task.done():
            return
        self._state.start()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel all network work and publish a stopped state."""
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self._state.stop()

    async def _run(self) -> None:
        timeout = httpx.Timeout(30.0, read=None)
        async with self._client_factory(timeout) as client:
            receiver = StatsReceiver(self._sse_url, client)
            dispatcher = OutputDispatcher(
                [
                    BoundOutput(registration=registration, sink=registration.build(client))
                    for registration in self._outputs
                ],
                self._queue,
                self._state,
                clock=self._clock,
            )
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self._receive_loop(receiver, dispatcher))
                tasks.create_task(self._retry_loop(dispatcher))

    async def _receive_loop(
        self,
        receiver: StatsReceiver,
        dispatcher: OutputDispatcher,
    ) -> None:
        while True:
            self._state.waiting()
            try:
                raw_json = await receiver.receive_once()
            except asyncio.CancelledError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                self._state.receiver_error(
                    self._safe_error("受信", exc),
                    retry_after_seconds=self._reconnect_delay,
                )
                await asyncio.sleep(self._reconnect_delay)
                continue

            now = self._clock()
            self._state.received(at=now, preview=self._preview(raw_json))
            payload = self._build_payload(raw_json, received_at=now)
            if payload.parse_error is None:
                self._on_payload(payload.payload)
            await dispatcher.dispatch(payload)

    async def _retry_loop(self, dispatcher: OutputDispatcher) -> None:
        while True:
            await asyncio.sleep(self._retry_interval)
            try:
                await dispatcher.retry_pending()
            except asyncio.CancelledError:
                raise
            except (OSError, TypeError, ValueError) as exc:
                self._state.receiver_error(self._safe_error("再送キュー読込", exc))

    @staticmethod
    def _build_payload(raw_json: str, *, received_at: datetime) -> RelayPayload:
        try:
            payload = parse_json(raw_json)
        except json.JSONDecodeError as exc:
            return RelayPayload(
                raw_json=raw_json,
                payload=None,
                received_at=received_at,
                parse_error=type(exc).__name__,
            )
        return RelayPayload(raw_json=raw_json, payload=payload, received_at=received_at)

    @staticmethod
    def _preview(raw_json: str) -> str:
        if len(raw_json) <= _PREVIEW_LENGTH:
            return raw_json
        return f"{raw_json[:_PREVIEW_LENGTH]}..."

    @staticmethod
    def _safe_error(operation: str, error: Exception) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"{operation}エラー: HTTP {error.response.status_code}"
        return f"{operation}エラー: {type(error).__name__}"

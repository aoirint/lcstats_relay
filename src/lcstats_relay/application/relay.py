"""Coordinate input receiving and implementation-independent output dispatch."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import Protocol

from lcstats_relay.application.dispatcher import OutputDispatcher
from lcstats_relay.application.ports import (
    OutputPolicy,
    ReceiverError,
    ReceiverPort,
    RetryQueuePort,
    RuntimeFactory,
)
from lcstats_relay.application.state import ConnectionState, RelayStateStore, StateCallback
from lcstats_relay.domain.payload import JSONValue, RelayPayload, parse_json

type PayloadCallback = Callable[[JSONValue], None]
type Clock = Callable[[], datetime]
type Sleep = Callable[[float], Awaitable[None]]

_PREVIEW_LENGTH = 300


def _utc_now() -> datetime:
    return datetime.now(UTC)


def preview_payload(raw_json: str) -> str:
    """Return a bounded payload preview suitable for presentation state."""
    if len(raw_json) <= _PREVIEW_LENGTH:
        return raw_json
    return f"{raw_json[:_PREVIEW_LENGTH]}..."


class RetryDispatcher(Protocol):
    """Retry queued output deliveries."""

    async def retry_pending(self) -> None:
        """Attempt all currently queued deliveries."""


class RetryWorker:
    """Periodically retry persisted output deliveries."""

    def __init__(
        self,
        *,
        dispatcher: RetryDispatcher,
        state: RelayStateStore,
        interval: float,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        """Configure the dispatcher, observable state, and scheduling seam."""
        self._dispatcher = dispatcher
        self._state = state
        self._interval = interval
        self._sleep = sleep

    async def run_forever(self) -> None:
        """Retry until cancellation, keeping queue read failures observable."""
        while True:
            await self._sleep(self._interval)
            try:
                await self._dispatcher.retry_pending()
            except asyncio.CancelledError:
                raise
            except (OSError, TypeError, ValueError) as exc:
                self._state.receiver_error(_safe_error("再送キュー読込", error=exc))


class ConnectionManager:
    """Own input and retry loops while delegating every output to registrations."""

    def __init__(  # noqa: PLR0913 - callbacks and timing seams keep layers decoupled.
        self,
        *,
        output_policies: Sequence[OutputPolicy],
        runtime_factory: RuntimeFactory,
        retry_queue: RetryQueuePort,
        on_state: StateCallback,
        on_payload: PayloadCallback,
        reconnect_delay: float = 3.0,
        retry_interval: float = 30.0,
        clock: Clock = _utc_now,
        reconnect_sleep: Sleep = asyncio.sleep,
    ) -> None:
        """Configure application ports, state, and timing policy."""
        self._output_policies = tuple(output_policies)
        self._runtime_factory = runtime_factory
        self._queue = retry_queue
        self._on_payload = on_payload
        self._reconnect_delay = reconnect_delay
        self._retry_interval = retry_interval
        self._clock = clock
        self._reconnect_sleep = reconnect_sleep
        self._task: asyncio.Task[None] | None = None
        self._state = RelayStateStore(
            ((output.key, output.label) for output in self._output_policies),
            on_change=on_state,
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
        async with self._runtime_factory() as session:
            dispatcher = OutputDispatcher(
                session.outputs,
                queue=self._queue,
                state=self._state,
                clock=self._clock,
            )
            try:
                await dispatcher.load_pending_counts()
            except (OSError, TypeError, ValueError) as exc:
                self._state.receiver_error(_safe_error("再送キュー読込", error=exc))
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self._receive_loop(session.receiver, dispatcher=dispatcher))
                tasks.create_task(
                    RetryWorker(
                        dispatcher=dispatcher,
                        state=self._state,
                        interval=self._retry_interval,
                    ).run_forever()
                )

    async def _receive_loop(
        self,
        receiver: ReceiverPort,
        *,
        dispatcher: OutputDispatcher,
    ) -> None:
        while True:
            self._state.waiting()
            try:
                raw_json = await receiver.receive_once()
            except asyncio.CancelledError:
                raise
            except ReceiverError as exc:
                message = _safe_error("受信", error=exc)
                self._state.receiver_error(message, retry_after_seconds=self._reconnect_delay)
                await self._wait_before_reconnect(message)
                continue

            now = self._clock()
            self._state.received(at=now, preview=preview_payload(raw_json))
            payload = self._build_payload(raw_json, received_at=now)
            if payload.parse_error is None:
                self._on_payload(payload.payload)
            await dispatcher.dispatch(payload)

    async def _wait_before_reconnect(self, message: str) -> None:
        remaining = self._reconnect_delay
        while remaining > 0:
            step = min(1.0, remaining)
            await self._reconnect_sleep(step)
            remaining = max(0.0, remaining - step)
            if remaining > 0:
                self._state.receiver_error(message, retry_after_seconds=remaining)

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


def _safe_error(operation: str, *, error: Exception) -> str:
    if isinstance(error, ReceiverError):
        return f"{operation}エラー: {error.detail}"
    return f"{operation}エラー: {type(error).__name__}"

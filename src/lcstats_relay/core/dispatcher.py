"""Generic output dispatch and retry orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from lcstats_relay.core.outputs import (
    OutputDeliveryError,
    OutputReceipt,
    OutputRegistration,
    OutputSink,
)
from lcstats_relay.core.payload import RelayPayload
from lcstats_relay.core.state import RelayStateStore
from lcstats_relay.core.storage import RetryQueue

type Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, kw_only=True, slots=True)
class BoundOutput:
    """An instantiated sink paired with its registration policy."""

    registration: OutputRegistration
    sink: OutputSink


class OutputDispatcher:
    """Dispatch and retry registered outputs without knowing their implementations."""

    def __init__(
        self,
        outputs: Sequence[BoundOutput],
        *,
        queue: RetryQueue,
        state: RelayStateStore,
        clock: Clock = _utc_now,
    ) -> None:
        """Index output bindings and retain generic state and queue collaborators."""
        self._outputs = outputs
        self._by_key = {output.registration.key: output for output in outputs}
        self._queue = queue
        self._state = state
        self._clock = clock

    async def dispatch(self, payload: RelayPayload) -> None:
        """Deliver to outputs in registration order, respecting required failures."""
        for output in self._outputs:
            succeeded = await self._deliver(output, payload=payload, queue_on_failure=True)
            if not succeeded and output.registration.required:
                break

    async def retry_pending(self) -> None:
        """Attempt every queued item against its registered output."""
        for item in self._queue.pending():
            output = self._by_key.get(item.output_key)
            if output is None:
                continue
            succeeded = await self._deliver(output, payload=item.payload, queue_on_failure=False)
            if succeeded:
                self._queue.remove(item)
                self._refresh_pending(output.registration.key)

    async def _deliver(
        self,
        output: BoundOutput,
        *,
        payload: RelayPayload,
        queue_on_failure: bool,
    ) -> bool:
        key = output.registration.key
        self._state.output_started(key, at=self._clock())
        try:
            receipt = await output.sink.deliver(payload)
        except asyncio.CancelledError:
            raise
        except OutputDeliveryError as exc:
            self._handle_failure(
                output,
                payload=payload,
                error=exc,
                queue_on_failure=queue_on_failure,
            )
            return False
        self._handle_success(key, receipt=receipt)
        return True

    def _handle_success(self, key: str, *, receipt: OutputReceipt) -> None:
        self._state.output_succeeded(
            key,
            at=self._clock(),
            message=receipt.message,
            pending_count=self._queue.count(key),
        )

    def _handle_failure(
        self,
        output: BoundOutput,
        *,
        payload: RelayPayload,
        error: OutputDeliveryError,
        queue_on_failure: bool,
    ) -> None:
        registration = output.registration
        queued = False
        message = error.message
        if queue_on_failure and registration.queue_failures and error.retryable:
            try:
                self._queue.enqueue(
                    registration.key,
                    payload=payload,
                    queued_at=self._clock(),
                )
                queued = True
            except OSError:
                message = f"{message} / 再送キューの保存にも失敗しました"
        self._state.output_failed(
            registration.key,
            message=message,
            pending_count=self._queue.count(registration.key),
            queued=queued,
        )

    def _refresh_pending(self, key: str) -> None:
        self._state.state.outputs[key].pending_count = self._queue.count(key)

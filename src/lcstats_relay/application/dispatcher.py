"""Generic output dispatch and retry orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from lcstats_relay.application.diagnostics import emit
from lcstats_relay.application.ports import (
    BoundOutput,
    OutputDeliveryError,
    OutputReceipt,
    RetryQueuePort,
    RetrySemantics,
)
from lcstats_relay.application.state import RelayStateStore
from lcstats_relay.domain.payload import RelayPayload

type Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class OutputDispatcher:
    """Dispatch and retry registered outputs without knowing their implementations."""

    def __init__(
        self,
        *,
        outputs: Sequence[BoundOutput],
        queue: RetryQueuePort,
        state: RelayStateStore,
        clock: Clock = _utc_now,
    ) -> None:
        """Index output bindings and retain generic state and queue collaborators."""
        self._outputs = outputs
        self._by_key = {output.policy.key: output for output in outputs}
        self._queue = queue
        self._state = state
        self._clock = clock

    async def dispatch(self, *, payload: RelayPayload) -> None:
        """Deliver to outputs in registration order, respecting required failures."""
        for output in self._outputs:
            succeeded = await self._deliver(output=output, payload=payload, queue_on_failure=True)
            if not succeeded and output.policy.required:
                break

    async def load_pending_counts(self) -> None:
        """Load persisted queue state without blocking the event loop."""
        counts = {
            output.policy.key: await asyncio.to_thread(
                self._queue.count, output_key=output.policy.key
            )
            for output in self._outputs
        }
        emit(event="queue_loaded")
        self._state.pending_counts_loaded(counts=counts)

    async def retry_pending(self) -> None:
        """Attempt every queued item against its registered output."""
        for item in await asyncio.to_thread(self._queue.pending):
            output = self._by_key.get(item.output_key)
            if output is None:
                emit(event="retry_skipped", correlation_id=item.payload.correlation_id)
                continue
            emit(
                event="retry_started",
                correlation_id=item.payload.correlation_id,
                output=output.policy.key,
            )
            succeeded = await self._deliver(
                output=output, payload=item.payload, queue_on_failure=False
            )
            if succeeded:
                try:
                    await asyncio.to_thread(self._queue.remove, item=item)
                except OSError:
                    emit(
                        event="retry_remove_failed",
                        correlation_id=item.payload.correlation_id,
                        category="queue",
                        failed=True,
                    )
                    raise
                emit(
                    event="retry_removed",
                    correlation_id=item.payload.correlation_id,
                    output=output.policy.key,
                )
                await self._refresh_pending(key=output.policy.key)

    async def _deliver(
        self,
        *,
        output: BoundOutput,
        payload: RelayPayload,
        queue_on_failure: bool,
    ) -> bool:
        key = output.policy.key
        emit(event="output_started", correlation_id=payload.correlation_id, output=key)
        self._state.output_started(key=key, at=self._clock())
        try:
            receipt = await output.sink.deliver(payload=payload)
        except asyncio.CancelledError:
            emit(event="output_cancelled", correlation_id=payload.correlation_id, output=key)
            raise
        except OutputDeliveryError as exc:
            await self._handle_failure(
                output=output,
                payload=payload,
                error=exc,
                queue_on_failure=queue_on_failure,
            )
            return False
        emit(event="output_succeeded", correlation_id=payload.correlation_id, output=key)
        await self._handle_success(key=key, receipt=receipt)
        return True

    async def _handle_success(self, *, key: str, receipt: OutputReceipt) -> None:
        self._state.output_succeeded(
            key=key,
            at=self._clock(),
            message=receipt.message,
            pending_count=await asyncio.to_thread(self._queue.count, output_key=key),
        )

    async def _handle_failure(
        self,
        *,
        output: BoundOutput,
        payload: RelayPayload,
        error: OutputDeliveryError,
        queue_on_failure: bool,
    ) -> None:
        policy = output.policy
        emit(
            event="output_failed",
            correlation_id=payload.correlation_id,
            output=policy.key,
            category=error.category,
            status_code=error.status_code,
            failed=True,
        )
        queued = False
        message = error.message
        if (
            queue_on_failure
            and policy.retry_semantics is RetrySemantics.AT_LEAST_ONCE
            and error.retryable
        ):
            try:
                await asyncio.to_thread(
                    self._queue.enqueue,
                    output_key=policy.key,
                    payload=payload,
                    queued_at=self._clock(),
                )
                emit(event="queue_saved", correlation_id=payload.correlation_id, output=policy.key)
                queued = True
            except OSError:
                emit(
                    event="queue_save_failed",
                    correlation_id=payload.correlation_id,
                    category="queue",
                    failed=True,
                )
                message = f"{message} / 再送キューの保存にも失敗しました"
        self._state.output_failed(
            key=policy.key,
            message=message,
            pending_count=await asyncio.to_thread(self._queue.count, output_key=policy.key),
            queued=queued,
        )

    async def _refresh_pending(self, *, key: str) -> None:
        self._state.pending_count_changed(
            key=key,
            count=await asyncio.to_thread(self._queue.count, output_key=key),
        )

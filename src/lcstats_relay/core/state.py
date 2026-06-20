"""Observable relay state independent from output implementations."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum


class RelayStatus(StrEnum):
    """Current input-side relay lifecycle phase."""

    STOPPED = "stopped"
    WAITING = "waiting"
    RECEIVED = "received"
    DISPATCHING = "dispatching"
    ERROR = "error"


class OutputStatus(StrEnum):
    """Current lifecycle phase for one registered output."""

    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    RETRY_QUEUED = "retry_queued"


@dataclass(slots=True)
class OutputState:
    """Observable status and counters for one output."""

    key: str
    label: str
    status: OutputStatus = OutputStatus.IDLE
    success_count: int = 0
    failure_count: int = 0
    pending_count: int = 0
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    message: str = "待機中"


@dataclass(slots=True)
class ConnectionState:
    """Observable receiver state with independently managed output states."""

    status: RelayStatus = RelayStatus.STOPPED
    running: bool = False
    receive_count: int = 0
    last_received_at: datetime | None = None
    last_payload_preview: str | None = None
    last_error: str | None = None
    retry_after_seconds: float | None = None
    outputs: dict[str, OutputState] = field(default_factory=dict)


type StateCallback = Callable[[ConnectionState], None]


class RelayStateStore:
    """Own state transitions without knowing receiver or output implementations."""

    def __init__(
        self,
        outputs: Iterable[tuple[str, str]],
        on_change: StateCallback,
        *,
        pending_counts: Mapping[str, int] | None = None,
    ) -> None:
        """Initialize output state entries and a snapshot callback."""
        counts = pending_counts or {}
        self._on_change = on_change
        self.state = ConnectionState(
            outputs={
                key: OutputState(key=key, label=label, pending_count=counts.get(key, 0))
                for key, label in outputs
            },
        )

    def start(self) -> None:
        """Mark the receiver as active and waiting."""
        self.state.running = True
        self.state.status = RelayStatus.WAITING
        self.state.retry_after_seconds = None
        self._emit()

    def stop(self) -> None:
        """Mark the receiver as stopped."""
        self.state.running = False
        self.state.status = RelayStatus.STOPPED
        self.state.retry_after_seconds = None
        self._emit()

    def waiting(self) -> None:
        """Mark the receiver as waiting for the next response."""
        self.state.status = RelayStatus.WAITING
        self.state.retry_after_seconds = None
        self._emit()

    def received(self, *, at: datetime, preview: str) -> None:
        """Record one received payload."""
        self.state.status = RelayStatus.RECEIVED
        self.state.receive_count += 1
        self.state.last_received_at = at
        self.state.last_payload_preview = preview
        self.state.last_error = None
        self.state.retry_after_seconds = None
        self._emit()

    def receiver_error(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        """Expose an input-side error independently from output failures."""
        self.state.status = RelayStatus.ERROR
        self.state.last_error = message
        self.state.retry_after_seconds = retry_after_seconds
        self._emit()

    def output_started(self, key: str, *, at: datetime) -> None:
        """Mark one output attempt as running."""
        output = self.state.outputs[key]
        output.status = OutputStatus.RUNNING
        output.last_attempt_at = at
        output.message = "処理中"
        self.state.status = RelayStatus.DISPATCHING
        self._emit()

    def output_succeeded(
        self,
        key: str,
        *,
        at: datetime,
        message: str,
        pending_count: int,
    ) -> None:
        """Record an output-specific success message and counters."""
        output = self.state.outputs[key]
        output.status = OutputStatus.SUCCESS
        output.success_count += 1
        output.pending_count = pending_count
        output.last_success_at = at
        output.message = message
        self._emit()

    def output_failed(
        self,
        key: str,
        *,
        message: str,
        pending_count: int,
        queued: bool,
    ) -> None:
        """Record an output-specific failure without changing other outputs."""
        output = self.state.outputs[key]
        output.status = OutputStatus.RETRY_QUEUED if queued else OutputStatus.ERROR
        output.failure_count += 1
        output.pending_count = pending_count
        output.message = message
        self._emit()

    def _emit(self) -> None:
        snapshot = replace(
            self.state,
            outputs={key: replace(value) for key, value in self.state.outputs.items()},
        )
        self._on_change(snapshot)

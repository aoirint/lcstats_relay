"""Framework-free ports and values used by relay orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import TracebackType
from typing import Protocol

from lcstats_relay.domain.payload import RelayPayload


class OutputDeliveryError(Exception):
    """An output failure carrying safe UI text and retry eligibility."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        """Retain a user-facing message without sensitive boundary details."""
        super().__init__(message)
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True, kw_only=True, slots=True)
class OutputReceipt:
    """Output-specific success details for state and presentation."""

    message: str


class RetrySemantics(StrEnum):
    """Delivery guarantee accepted by an output policy."""

    NONE = "none"
    AT_LEAST_ONCE = "at-least-once"


class OutputSink(Protocol):
    """Deliver one received payload to an output surface."""

    async def deliver(self, payload: RelayPayload) -> OutputReceipt:
        """Deliver a payload or raise OutputDeliveryError."""


@dataclass(frozen=True, kw_only=True, slots=True)
class OutputPolicy:
    """Application policy for one independently implemented output."""

    key: str
    label: str
    required: bool = False
    retry_semantics: RetrySemantics = RetrySemantics.NONE


@dataclass(frozen=True, kw_only=True, slots=True)
class BoundOutput:
    """Pair application policy with a runtime output implementation."""

    policy: OutputPolicy
    sink: OutputSink


@dataclass(frozen=True, kw_only=True, slots=True)
class RetryItem:
    """Queued delivery with an opaque persistence-owned storage key."""

    storage_key: str
    output_key: str
    payload: RelayPayload


class RetryQueuePort(Protocol):
    """Persist and enumerate failed output deliveries."""

    def enqueue(
        self,
        output_key: str,
        *,
        payload: RelayPayload,
        queued_at: datetime,
    ) -> object:
        """Persist a failed delivery and return implementation-owned identity."""

    def pending(self) -> list[RetryItem]:
        """Return queued deliveries in deterministic order."""

    def remove(self, item: RetryItem) -> None:
        """Remove a successfully delivered item."""

    def count(self, output_key: str | None = None) -> int:
        """Return all queued deliveries or those for one output."""


class ReceiverPort(Protocol):
    """Receive one raw relay payload."""

    async def receive_once(self) -> str:
        """Return one raw payload or raise a boundary error."""


class ReceiverError(Exception):
    """A receive-boundary failure containing only presentation-safe detail."""

    def __init__(self, detail: str) -> None:
        """Retain a stable safe detail without leaking request data."""
        super().__init__(detail)
        self.detail = detail

    @classmethod
    def from_http_status(cls, status_code: int) -> ReceiverError:
        """Build a safe error from an HTTP response status."""
        return cls(f"HTTP {status_code}")

    @classmethod
    def from_transport_error(cls, error: Exception) -> ReceiverError:
        """Build a safe error without exposing request or credential details."""
        return cls(type(error).__name__)


@dataclass(frozen=True, kw_only=True, slots=True)
class RelaySession:
    """Runtime resources available for one manager session."""

    receiver: ReceiverPort
    outputs: tuple[BoundOutput, ...]


class RelayRuntime(Protocol):
    """Own runtime resources such as HTTP clients for one session."""

    async def __aenter__(self) -> RelaySession:
        """Open resources and return application-facing ports."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close all runtime resources."""


class RuntimeFactory(Protocol):
    """Create an isolated runtime for one connection session."""

    def __call__(self) -> RelayRuntime:
        """Return a not-yet-entered runtime."""

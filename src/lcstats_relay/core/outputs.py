"""Pluggable output implementations and registration metadata."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

from lcstats_relay.core.auth import RequestAuthenticator
from lcstats_relay.core.payload import RelayPayload
from lcstats_relay.core.storage import ArchiveWriter


class OutputDeliveryError(Exception):
    """An output failure carrying safe UI text and retry eligibility."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        """Retain a user-facing message without sensitive request details."""
        super().__init__(message)
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class OutputReceipt:
    """Output-specific success details for state and UI presentation."""

    message: str


class OutputSink(Protocol):
    """Deliver one received payload to an output surface."""

    async def deliver(self, payload: RelayPayload) -> OutputReceipt:
        """Deliver a payload or raise OutputDeliveryError."""


type OutputFactory = Callable[[httpx.AsyncClient], OutputSink]


@dataclass(frozen=True, slots=True)
class OutputRegistration:
    """Register an output implementation and its orchestration policy."""

    key: str
    label: str
    build: OutputFactory
    required: bool = False
    queue_failures: bool = True


class ArchiveOutput:
    """Write the exact received JSON to the durable local archive."""

    def __init__(self, writer: ArchiveWriter) -> None:
        """Use the supplied archive persistence implementation."""
        self._writer = writer

    async def deliver(self, payload: RelayPayload) -> OutputReceipt:
        """Archive raw JSON before any required downstream output proceeds."""
        try:
            path = self._writer.write(payload.raw_json, received_at=payload.received_at)
        except OSError as exc:
            msg = "ローカル保存に失敗しました"
            raise OutputDeliveryError(msg, retryable=False) from exc
        return OutputReceipt(message=f"保存しました: {path}")


class GasOutput:
    """Post parsed JSON to a GAS Web App independently from authentication."""

    def __init__(
        self,
        url: str,
        client: httpx.AsyncClient,
        authenticator: RequestAuthenticator,
    ) -> None:
        """Configure delivery while receiving authentication as a separate policy."""
        self._url = url
        self._client = client
        self._authenticator = authenticator

    async def deliver(self, payload: RelayPayload) -> OutputReceipt:
        """Send parsed JSON and return GAS-specific UI text."""
        if payload.parse_error is not None:
            msg = f"JSONを解析できないため送信しません: {payload.parse_error}"
            raise OutputDeliveryError(msg, retryable=False)

        request = self._client.build_request("POST", self._url, json=payload.payload)
        self._authenticator.apply(request)
        try:
            response = await self._client.send(request)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            msg = f"GAS送信に失敗しました: HTTP {exc.response.status_code}"
            raise OutputDeliveryError(msg, retryable=True) from exc
        except httpx.HTTPError as exc:
            msg = f"GAS送信に失敗しました: {type(exc).__name__}"
            raise OutputDeliveryError(msg, retryable=True) from exc
        return OutputReceipt(message="Google Sheetsへ送信しました")

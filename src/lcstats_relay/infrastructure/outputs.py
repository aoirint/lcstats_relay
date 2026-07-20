"""Archive and Google Apps Script output adapters."""

from __future__ import annotations

import asyncio

import httpx

from lcstats_relay.application.ports import OutputDeliveryError, OutputReceipt
from lcstats_relay.domain.payload import RelayPayload
from lcstats_relay.infrastructure.auth import RequestAuthenticator
from lcstats_relay.infrastructure.storage import ArchiveWriter


class ArchiveOutput:
    """Write the exact received JSON to the durable local archive."""

    def __init__(self, *, writer: ArchiveWriter) -> None:
        """Use the supplied archive persistence implementation."""
        self._writer = writer

    async def deliver(self, *, payload: RelayPayload) -> OutputReceipt:
        """Archive raw JSON before any required downstream output proceeds."""
        try:
            path = await asyncio.to_thread(
                self._writer.write,
                raw_json=payload.raw_json,
                received_at=payload.received_at,
            )
        except OSError as exc:
            msg = "ローカル保存に失敗しました"
            raise OutputDeliveryError(message=msg, retryable=False) from exc
        return OutputReceipt(message=f"保存しました: {path}")


class GasOutput:
    """Post parsed JSON to a GAS Web App independently from authentication."""

    def __init__(
        self,
        *,
        url: str,
        client: httpx.AsyncClient,
        authenticator: RequestAuthenticator,
        request_timeout_seconds: float = 30.0,
    ) -> None:
        """Configure delivery while receiving authentication as a separate policy."""
        self._url = url
        self._client = client
        self._authenticator = authenticator
        self._request_timeout_seconds = request_timeout_seconds

    async def deliver(self, *, payload: RelayPayload) -> OutputReceipt:
        """Send parsed JSON and return GAS-specific UI text."""
        if payload.parse_error is not None:
            msg = f"JSONを解析できないため送信しません: {payload.parse_error}"
            raise OutputDeliveryError(message=msg, retryable=False)

        request = self._client.build_request("POST", self._url, json=payload.payload)
        self._authenticator.apply(request=request)
        try:
            async with asyncio.timeout(self._request_timeout_seconds):
                response = await self._client.send(request)
            response.raise_for_status()
        except TimeoutError as exc:
            msg = "GAS送信に失敗しました: TimeoutError"
            raise OutputDeliveryError(message=msg, retryable=True) from exc
        except httpx.HTTPStatusError as exc:
            msg = f"GAS送信に失敗しました: HTTP {exc.response.status_code}"
            raise OutputDeliveryError(message=msg, retryable=True) from exc
        except httpx.HTTPError as exc:
            msg = f"GAS送信に失敗しました: {type(exc).__name__}"
            raise OutputDeliveryError(message=msg, retryable=True) from exc
        return OutputReceipt(message="Google Sheetsへ送信しました")

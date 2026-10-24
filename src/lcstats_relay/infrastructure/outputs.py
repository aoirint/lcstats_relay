"""Archive and Google Apps Script output adapters."""

from __future__ import annotations

import asyncio
import json

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
                correlation_id=payload.correlation_id,
            )
        except OSError as exc:
            msg = "ローカル保存に失敗しました"
            raise OutputDeliveryError(message=msg, retryable=False, category="archive") from exc
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
            raise OutputDeliveryError(message=msg, retryable=False, category="json_parse")

        request = self._client.build_request("POST", self._url, json=payload.payload)
        self._authenticator.apply(request=request)
        try:
            async with asyncio.timeout(self._request_timeout_seconds):
                response = await self._client.send(request)
            response.raise_for_status()
        except TimeoutError as exc:
            msg = "GAS送信に失敗しました: TimeoutError"
            raise OutputDeliveryError(message=msg, retryable=True, category="timeout") from exc
        except httpx.HTTPStatusError as exc:
            msg = f"GAS送信に失敗しました: HTTP {exc.response.status_code}"
            raise OutputDeliveryError(
                message=msg,
                retryable=True,
                category=("authentication" if exc.response.status_code in (401, 403) else "http"),
                status_code=exc.response.status_code,
            ) from exc
        except httpx.HTTPError as exc:
            msg = f"GAS送信に失敗しました: {type(exc).__name__}"
            raise OutputDeliveryError(message=msg, retryable=True, category="transport") from exc
        _validate_gas_response(response=response)
        return OutputReceipt(message="Google Sheetsへ送信しました")


def _validate_gas_response(*, response: httpx.Response) -> None:
    # GAS may return an HTML application error with HTTP 200.
    if (
        response.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json"
        and "invalid token" in response.text.lower()
    ):
        msg = "GAS認証に失敗しました"
        raise OutputDeliveryError(message=msg, retryable=True, category="authentication")
    if response.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        msg = "GAS応答の形式が不正です(JSONが必要です)"
        raise OutputDeliveryError(message=msg, retryable=True, category="response_format")
    try:
        result = response.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        msg = "GAS応答のJSONを解析できません"
        raise OutputDeliveryError(message=msg, retryable=True, category="json_parse") from exc
    if not isinstance(result, dict) or result.get("ok") is not True:
        msg = "GASが処理成功を返しませんでした"
        raise OutputDeliveryError(message=msg, retryable=True, category="application")

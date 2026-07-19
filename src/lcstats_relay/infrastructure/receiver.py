"""Receive the one-payload SSE responses emitted by LCStatsTracker."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from lcstats_relay.application.ports import ReceiverError

_MAX_SSE_LINE_BYTES = 1_048_576


class EmptyPayloadError(ReceiverError):
    """Raised when an SSE response closes without a data payload."""


class InvalidPayloadError(ReceiverError):
    """Raised when an SSE payload cannot be decoded safely."""


class PayloadTooLargeError(ReceiverError):
    """Raised when one SSE line exceeds the accepted memory bound."""


class StatsReceiver:
    """Receive one JSON payload from one SSE response."""

    def __init__(self, url: str, *, client: httpx.AsyncClient) -> None:
        """Configure the endpoint and shared asynchronous HTTP client."""
        self._url = url
        self._client = client

    async def receive_once(self) -> str:
        """Wait for and return the single data payload in one response."""
        headers = {"Accept": "text/event-stream"}
        try:
            async with self._client.stream("GET", self._url, headers=headers) as response:
                response.raise_for_status()
                async for line in _bounded_lines(response):
                    if line.startswith(b"data:"):
                        try:
                            return line.removeprefix(b"data:").lstrip(b" ").decode("utf-8")
                        except UnicodeDecodeError as exc:
                            raise InvalidPayloadError(InvalidPayloadError.__name__) from exc
        except httpx.HTTPStatusError as exc:
            raise ReceiverError.from_http_status(exc.response.status_code) from exc
        except httpx.HTTPError as exc:
            raise ReceiverError.from_transport_error(exc) from exc

        raise EmptyPayloadError(EmptyPayloadError.__name__)


async def _bounded_lines(response: httpx.Response) -> AsyncIterator[bytes]:
    """Yield raw response lines while bounding attacker-controlled buffering."""
    buffered = bytearray()
    async for chunk in response.aiter_bytes():
        buffered.extend(chunk)
        while (newline := buffered.find(b"\n")) >= 0:
            if newline > _MAX_SSE_LINE_BYTES:
                raise PayloadTooLargeError(PayloadTooLargeError.__name__)
            line = bytes(buffered[:newline]).removesuffix(b"\r")
            del buffered[: newline + 1]
            yield line
        if len(buffered) > _MAX_SSE_LINE_BYTES:
            raise PayloadTooLargeError(PayloadTooLargeError.__name__)
    if buffered:
        yield bytes(buffered).removesuffix(b"\r")

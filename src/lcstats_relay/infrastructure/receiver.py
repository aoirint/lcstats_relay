"""Receive the one-payload SSE responses emitted by LCStatsTracker."""

from __future__ import annotations

import httpx

from lcstats_relay.application.ports import ReceiverError


class EmptyPayloadError(ReceiverError):
    """Raised when an SSE response closes without a data payload."""


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
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        return line.removeprefix("data:").lstrip(" ")
        except httpx.HTTPStatusError as exc:
            raise ReceiverError.from_http_status(exc.response.status_code) from exc
        except httpx.HTTPError as exc:
            raise ReceiverError.from_transport_error(exc) from exc

        raise EmptyPayloadError(EmptyPayloadError.__name__)

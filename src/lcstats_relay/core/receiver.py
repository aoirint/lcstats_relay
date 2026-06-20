"""Receive the one-payload SSE responses emitted by LCStatsTracker."""

from __future__ import annotations

import httpx


class EmptyPayloadError(ValueError):
    """Raised when an SSE response closes without a data payload."""


class StatsReceiver:
    """Receive one JSON payload from one SSE response."""

    def __init__(self, url: str, client: httpx.AsyncClient) -> None:
        """Configure the endpoint and shared asynchronous HTTP client."""
        self._url = url
        self._client = client

    async def receive_once(self) -> str:
        """Wait for and return the single data payload in one response."""
        headers = {"Accept": "text/event-stream"}
        async with self._client.stream("GET", self._url, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    return line.removeprefix("data:").lstrip(" ")

        msg = "SSE response closed without a data payload"
        raise EmptyPayloadError(msg)

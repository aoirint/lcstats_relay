"""Receive the one-payload SSE responses emitted by LCStatsTracker."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

import httpx

_LOCALHOST = "localhost"
_IPV4_LOOPBACK = "127.0.0.1"


class EmptyPayloadError(ValueError):
    """Raised when an SSE response closes without a data payload."""


@dataclass(frozen=True, slots=True)
class ReceiverEndpoint:
    """HTTP request target and headers after loopback normalization."""

    url: str
    headers: dict[str, str]


def normalize_receiver_endpoint(url: str) -> ReceiverEndpoint:
    """Avoid localhost dual-stack fallback while preserving the HTTP Host value."""
    parsed = urlsplit(url)
    headers = {"Accept": "text/event-stream"}
    if parsed.hostname != _LOCALHOST:
        return ReceiverEndpoint(url=url, headers=headers)

    headers["Host"] = parsed.netloc
    target = _replace_hostname(parsed, _IPV4_LOOPBACK)
    return ReceiverEndpoint(url=urlunsplit(target), headers=headers)


def _replace_hostname(parsed: SplitResult, hostname: str) -> SplitResult:
    port = f":{parsed.port}" if parsed.port is not None else ""
    return parsed._replace(netloc=f"{hostname}{port}")


class StatsReceiver:
    """Receive one JSON payload from one SSE response."""

    def __init__(self, url: str, client: httpx.AsyncClient) -> None:
        """Configure the endpoint and shared asynchronous HTTP client."""
        self._url = url
        self._client = client

    async def receive_once(self) -> str:
        """Wait for and return the single data payload in one response."""
        endpoint = normalize_receiver_endpoint(self._url)
        async with self._client.stream("GET", endpoint.url, headers=endpoint.headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    return line.removeprefix("data:").lstrip(" ")

        msg = "SSE response closed without a data payload"
        raise EmptyPayloadError(msg)

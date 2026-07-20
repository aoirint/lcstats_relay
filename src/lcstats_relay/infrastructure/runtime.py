"""HTTP resource lifetime and output binding for one relay session."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

import httpx

from lcstats_relay.application.ports import BoundOutput, OutputPolicy, OutputSink, RelaySession
from lcstats_relay.infrastructure.receiver import StatsReceiver


class ClientFactory(Protocol):
    """Build an HTTP client from an explicit timeout."""

    def __call__(self, *, timeout: httpx.Timeout) -> httpx.AsyncClient:
        """Create one unentered client."""


class OutputFactory(Protocol):
    """Bind an output to the shared HTTP client."""

    def __call__(self, *, client: httpx.AsyncClient) -> OutputSink:
        """Create one output adapter."""


def make_http_client(*, timeout: httpx.Timeout) -> httpx.AsyncClient:
    """Create the production HTTP client with explicit redirect policy."""
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)


@dataclass(frozen=True, kw_only=True, slots=True)
class HttpOutputBinding:
    """Build one output adapter inside the shared HTTP client lifetime."""

    policy: OutputPolicy
    build: OutputFactory


class HttpRelayRuntime:
    """Own the shared HTTP client used by the receiver and remote outputs."""

    def __init__(
        self,
        *,
        sse_url: str,
        outputs: Sequence[HttpOutputBinding],
        client_factory: ClientFactory = make_http_client,
    ) -> None:
        """Retain immutable configuration until the runtime is entered."""
        self._sse_url = sse_url
        self._outputs = tuple(outputs)
        self._client_factory = client_factory
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> RelaySession:
        """Open the client and bind every application output policy."""
        timeout = httpx.Timeout(30.0, read=None)
        client = self._client_factory(timeout=timeout)
        self._client = await client.__aenter__()
        return RelaySession(
            receiver=StatsReceiver(url=self._sse_url, client=self._client),
            outputs=tuple(
                BoundOutput(policy=output.policy, sink=output.build(client=self._client))
                for output in self._outputs
            ),
        )

    async def __aexit__(  # noqa: PLR0917 -- keyword-only-exception: async context manager protocol ABI
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the exact client opened by this runtime."""
        if self._client is not None:
            await self._client.__aexit__(exc_type, exc, traceback)
            self._client = None

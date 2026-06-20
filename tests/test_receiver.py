"""Tests for the one-response receiver."""

import asyncio

import httpx
import pytest

from lcstats_relay.core.receiver import EmptyPayloadError, StatsReceiver


def test_receive_once_returns_data_payload() -> None:
    """Return the first data field from a successful SSE response."""

    async def scenario() -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, text='data: {"Seed": 42}\n\n'),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver("http://localhost:2145/", client)
            assert await receiver.receive_once() == '{"Seed": 42}'

    asyncio.run(scenario())


def test_receive_once_raises_for_http_error() -> None:
    """Surface HTTP failures to the connection manager."""

    async def scenario() -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver("http://localhost:2145/", client)
            with pytest.raises(httpx.HTTPStatusError):
                await receiver.receive_once()

    asyncio.run(scenario())


def test_receive_once_rejects_response_without_data() -> None:
    """Reject a closed response that did not contain the expected payload."""

    async def scenario() -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, text=": ping\n\n"))
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver("http://localhost:2145/", client)
            with pytest.raises(EmptyPayloadError):
                await receiver.receive_once()

    asyncio.run(scenario())

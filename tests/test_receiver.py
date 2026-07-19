"""Tests for the one-response receiver."""

import asyncio

import httpx
import pytest

from lcstats_relay.application.ports import ReceiverError
from lcstats_relay.infrastructure.receiver import EmptyPayloadError, StatsReceiver


def test_receive_once_returns_data_payload() -> None:
    """Return the first data field from a successful SSE response."""

    async def scenario() -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, text='data: {"Seed": 42}\n\n'),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver("http://localhost:2145/", client=client)
            assert await receiver.receive_once() == '{"Seed": 42}'

    asyncio.run(scenario())


def test_receive_once_uses_configured_endpoint() -> None:
    """Respect an explicitly configured endpoint instead of rewriting it."""

    async def scenario() -> None:
        seen_url = ""

        def handle(request: httpx.Request) -> httpx.Response:
            nonlocal seen_url
            seen_url = str(request.url)
            return httpx.Response(200, text='data: {"Seed": 42}\n\n')

        transport = httpx.MockTransport(handle)
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver("http://localhost:2145/", client=client)
            assert await receiver.receive_once() == '{"Seed": 42}'

        assert seen_url == "http://localhost:2145/"

    asyncio.run(scenario())


def test_receive_once_raises_for_http_error() -> None:
    """Surface HTTP failures to the connection manager."""

    async def scenario() -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver("http://localhost:2145/", client=client)
            with pytest.raises(ReceiverError, match="HTTP 503"):
                await receiver.receive_once()

    asyncio.run(scenario())


def test_receive_once_redacts_transport_error_detail() -> None:
    """Expose only the transport error type at the application boundary."""

    async def handle(request: httpx.Request) -> httpx.Response:
        detail = "secret endpoint detail"
        raise httpx.ConnectError(detail, request=request)

    async def scenario() -> None:
        transport = httpx.MockTransport(handle)
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver("https://example.com/events", client=client)
            with pytest.raises(ReceiverError, match=r"^ConnectError$"):
                await receiver.receive_once()

    asyncio.run(scenario())


def test_receive_once_rejects_response_without_data() -> None:
    """Reject a closed response that did not contain the expected payload."""

    async def scenario() -> None:
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, text=": ping\n\n"))
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver("http://localhost:2145/", client=client)
            with pytest.raises(EmptyPayloadError):
                await receiver.receive_once()

    asyncio.run(scenario())

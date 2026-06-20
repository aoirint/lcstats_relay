"""Tests for the one-response receiver."""

import asyncio

import httpx
import pytest

from lcstats_relay.core.receiver import (
    EmptyPayloadError,
    StatsReceiver,
    normalize_receiver_endpoint,
)


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


def test_receive_once_normalizes_localhost_to_ipv4_loopback() -> None:
    """Avoid localhost IPv6/IPv4 fallback while preserving the Host header."""

    async def scenario() -> None:
        seen_url = ""
        seen_host = ""

        def handle(request: httpx.Request) -> httpx.Response:
            nonlocal seen_url, seen_host
            seen_url = str(request.url)
            seen_host = request.headers["Host"]
            return httpx.Response(200, text='data: {"Seed": 42}\n\n')

        transport = httpx.MockTransport(handle)
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver("http://localhost:2145/", client)
            assert await receiver.receive_once() == '{"Seed": 42}'

        assert seen_url == "http://127.0.0.1:2145/"
        assert seen_host == "localhost:2145"

    asyncio.run(scenario())


def test_receiver_endpoint_keeps_explicit_loopback_hosts() -> None:
    """Leave direct loopback addresses untouched."""
    ipv4 = normalize_receiver_endpoint("http://127.0.0.1:2145/")
    ipv6 = normalize_receiver_endpoint("http://[::1]:2145/")

    assert ipv4.url == "http://127.0.0.1:2145/"
    assert ipv4.headers == {"Accept": "text/event-stream"}
    assert ipv6.url == "http://[::1]:2145/"
    assert ipv6.headers == {"Accept": "text/event-stream"}


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

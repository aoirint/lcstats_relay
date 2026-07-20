"""Tests for the one-response receiver."""

import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from lcstats_relay.application.ports import ReceiverError
from lcstats_relay.infrastructure import receiver as receiver_module
from lcstats_relay.infrastructure.receiver import (
    EmptyPayloadError,
    InvalidPayloadError,
    PayloadTooLargeError,
    StatsReceiver,
)


def _transport(*, response: httpx.Response) -> httpx.MockTransport:
    def handle(  # keyword-only-exception: httpx MockTransport handler ABI
        _request: httpx.Request,
    ) -> httpx.Response:
        return response

    return httpx.MockTransport(handle)


def test_receive_once_returns_data_payload() -> None:
    """Return the first data field from a successful SSE response."""

    async def scenario() -> None:
        transport = _transport(
            response=httpx.Response(200, text='data: {"Seed": 42}\n\n'),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver(url="http://localhost:2145/", client=client)
            assert await receiver.receive_once() == '{"Seed": 42}'

    asyncio.run(scenario())


def test_receive_once_uses_configured_endpoint() -> None:
    """Respect an explicitly configured endpoint instead of rewriting it."""

    async def scenario() -> None:
        seen_url = ""

        def handle(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917 -- keyword-only-exception: httpx MockTransport handler ABI
            nonlocal seen_url
            seen_url = str(request.url)
            return httpx.Response(200, text='data: {"Seed": 42}\n\n')

        transport = httpx.MockTransport(handle)
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver(url="http://localhost:2145/", client=client)
            assert await receiver.receive_once() == '{"Seed": 42}'

        assert seen_url == "http://localhost:2145/"

    asyncio.run(scenario())


def test_receive_once_raises_for_http_error() -> None:
    """Surface HTTP failures to the connection manager."""

    async def scenario() -> None:
        transport = _transport(response=httpx.Response(503))
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver(url="http://localhost:2145/", client=client)
            with pytest.raises(ReceiverError, match="HTTP 503"):
                await receiver.receive_once()

    asyncio.run(scenario())


def test_receive_once_redacts_transport_error_detail() -> None:
    """Expose only the transport error type at the application boundary."""

    async def handle(request: httpx.Request) -> httpx.Response:  # noqa: PLR0917 -- keyword-only-exception: httpx MockTransport handler ABI
        detail = "secret endpoint detail"
        raise httpx.ConnectError(detail, request=request)

    async def scenario() -> None:
        transport = httpx.MockTransport(handle)
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver(url="https://example.com/events", client=client)
            with pytest.raises(ReceiverError, match=r"^ConnectError$"):
                await receiver.receive_once()

    asyncio.run(scenario())


def test_receive_once_rejects_response_without_data() -> None:
    """Reject a closed response that did not contain the expected payload."""

    async def scenario() -> None:
        transport = _transport(response=httpx.Response(200, text=": ping\n\n"))
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver(url="http://localhost:2145/", client=client)
            with pytest.raises(EmptyPayloadError):
                await receiver.receive_once()

    asyncio.run(scenario())


def test_receive_once_accepts_chunked_data_without_final_newline() -> None:
    """Reassemble a bounded SSE line across transport chunks."""

    class ChunkedStream(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"da"
            yield b'ta: {"Seed": 42}'

    async def scenario() -> None:
        transport = _transport(
            response=httpx.Response(200, stream=ChunkedStream()),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver(url="http://localhost:2145/", client=client)
            assert await receiver.receive_once() == '{"Seed": 42}'

    asyncio.run(scenario())


def test_receive_once_rejects_invalid_utf8() -> None:
    """Convert malformed payload encoding into a presentation-safe error."""

    async def scenario() -> None:
        transport = _transport(
            response=httpx.Response(200, content=b"data: \xff\n\n"),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver(url="http://localhost:2145/", client=client)
            with pytest.raises(InvalidPayloadError, match="InvalidPayloadError"):
                await receiver.receive_once()

    asyncio.run(scenario())


@pytest.mark.parametrize("content", [b"data: too-long\n", b"data: too-long"])
def test_receive_once_bounds_sse_lines(
    *,
    content: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a line whether the over-limit buffer has terminated or remains open."""
    monkeypatch.setattr(receiver_module, "_MAX_SSE_LINE_BYTES", 5)

    async def scenario() -> None:
        transport = _transport(
            response=httpx.Response(200, content=content),
        )
        async with httpx.AsyncClient(transport=transport) as client:
            receiver = StatsReceiver(url="http://localhost:2145/", client=client)
            with pytest.raises(PayloadTooLargeError, match="PayloadTooLargeError"):
                await receiver.receive_once()

    asyncio.run(scenario())

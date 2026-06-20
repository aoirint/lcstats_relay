"""Coordinate receiving, archiving, forwarding, and delivery retries."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import httpx

from lcstats_relay.core.receiver import StatsReceiver
from lcstats_relay.core.storage import ArchiveWriter, JSONValue, RetryQueue, parse_json

type StateCallback = Callable[[ConnectionState], None]
type PayloadCallback = Callable[[JSONValue], None]
type Clock = Callable[[], datetime]
type ClientFactory = Callable[[httpx.Timeout], httpx.AsyncClient]

_PREVIEW_LENGTH = 300


def _make_client(timeout: httpx.Timeout) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True)


class RelayStatus(StrEnum):
    """Current relay lifecycle phase."""

    STOPPED = "stopped"
    WAITING = "waiting"
    RECEIVED = "received"
    ARCHIVED = "archived"
    SENT = "sent"
    RETRY_QUEUED = "retry_queued"
    ERROR = "error"


@dataclass(slots=True)
class ConnectionState:
    """Observable relay counters and most recent activity."""

    status: RelayStatus = RelayStatus.STOPPED
    running: bool = False
    receive_count: int = 0
    archive_count: int = 0
    send_count: int = 0
    queue_count: int = 0
    last_received_at: datetime | None = None
    last_archived_at: datetime | None = None
    last_sent_at: datetime | None = None
    last_archive_file: str | None = None
    last_payload_preview: str | None = None
    last_error: str | None = None


class SheetSender:
    """Post JSON values to a GAS Web App."""

    def __init__(self, url: str, client: httpx.AsyncClient) -> None:
        """Configure the destination and shared asynchronous HTTP client."""
        self._url = url
        self._client = client

    async def send(self, payload: JSONValue) -> None:
        """Send one payload and require a successful HTTP response."""
        response = await self._client.post(self._url, json=payload)
        response.raise_for_status()


class ConnectionManager:
    """Own the async receive and retry loops for the desktop application."""

    def __init__(  # noqa: PLR0913 - callbacks and timing seams keep UI and tests decoupled.
        self,
        *,
        sse_url: str,
        gas_url: str,
        data_dir: Path,
        on_state: StateCallback,
        on_payload: PayloadCallback,
        reconnect_delay: float = 3.0,
        retry_interval: float = 30.0,
        clock: Clock = datetime.now,
        client_factory: ClientFactory = _make_client,
    ) -> None:
        """Configure relay endpoints, persistence, callbacks, and timing."""
        self._sse_url = sse_url
        self._gas_url = gas_url
        self._archive = ArchiveWriter(data_dir)
        self._queue = RetryQueue(data_dir)
        self._on_state = on_state
        self._on_payload = on_payload
        self._reconnect_delay = reconnect_delay
        self._retry_interval = retry_interval
        self._clock = clock
        self._client_factory = client_factory
        self._task: asyncio.Task[None] | None = None
        self.state = ConnectionState(queue_count=self._queue.count())

    def start(self) -> None:
        """Start the manager once; repeated calls while running are ignored."""
        if self._task is not None and not self._task.done():
            return
        self.state = ConnectionState(
            status=RelayStatus.WAITING,
            running=True,
            queue_count=self._queue.count(),
        )
        self._emit_state()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel all network work and publish a stopped state."""
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        self.state.running = False
        self.state.status = RelayStatus.STOPPED
        self._emit_state()

    async def _run(self) -> None:
        timeout = httpx.Timeout(30.0, read=None)
        async with self._client_factory(timeout) as client:
            receiver = StatsReceiver(self._sse_url, client)
            sender = SheetSender(self._gas_url, client)
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self._receive_loop(receiver, sender))
                tasks.create_task(self._retry_loop(sender))

    async def _receive_loop(self, receiver: StatsReceiver, sender: SheetSender) -> None:
        while True:
            self.state.status = RelayStatus.WAITING
            self._emit_state()
            try:
                raw_json = await receiver.receive_once()
            except asyncio.CancelledError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                self.state.status = RelayStatus.ERROR
                self.state.last_error = self._safe_error("受信", exc)
                self._emit_state()
                await asyncio.sleep(self._reconnect_delay)
                continue

            now = self._clock()
            self.state.status = RelayStatus.RECEIVED
            self.state.receive_count += 1
            self.state.last_received_at = now
            self.state.last_payload_preview = self._preview(raw_json)
            self._emit_state()

            try:
                archive_path = self._archive.write(raw_json, received_at=now)
            except OSError as exc:
                self.state.status = RelayStatus.ERROR
                self.state.last_error = self._safe_error("アーカイブ", exc)
                self._emit_state()
                continue
            self.state.status = RelayStatus.ARCHIVED
            self.state.archive_count += 1
            self.state.last_archived_at = now
            self.state.last_archive_file = str(archive_path)
            self._emit_state()

            try:
                payload = parse_json(raw_json)
            except (json.JSONDecodeError, ValueError) as exc:
                self.state.status = RelayStatus.ERROR
                self.state.last_error = self._safe_error("JSON解析", exc)
                self._emit_state()
                continue

            self._on_payload(payload)
            await self._send_or_queue(sender, payload, archive_path)

    async def _send_or_queue(
        self,
        sender: SheetSender,
        payload: JSONValue,
        archive_path: Path,
    ) -> None:
        try:
            await sender.send(payload)
        except asyncio.CancelledError:
            raise
        except httpx.HTTPError as exc:
            try:
                self._queue.enqueue(payload, archive_file=archive_path, queued_at=self._clock())
            except OSError as queue_error:
                self.state.status = RelayStatus.ERROR
                self.state.last_error = self._safe_error("再送キュー保存", queue_error)
                self._emit_state()
                return
            self.state.status = RelayStatus.RETRY_QUEUED
            self.state.queue_count = self._queue.count()
            self.state.last_error = self._safe_error("Sheets送信", exc)
            self._emit_state()
            return

        self.state.status = RelayStatus.SENT
        self.state.send_count += 1
        self.state.last_sent_at = self._clock()
        self.state.last_error = None
        self._emit_state()

    async def _retry_loop(self, sender: SheetSender) -> None:
        while True:
            await asyncio.sleep(self._retry_interval)
            try:
                items = self._queue.pending()
            except (OSError, TypeError, ValueError) as exc:
                self.state.status = RelayStatus.ERROR
                self.state.last_error = self._safe_error("再送キュー読込", exc)
                self._emit_state()
                continue

            for item in items:
                try:
                    await sender.send(item.payload)
                except asyncio.CancelledError:
                    raise
                except httpx.HTTPError as exc:
                    self.state.last_error = self._safe_error("再送", exc)
                    self._emit_state()
                    break
                self._queue.remove(item)
                self.state.status = RelayStatus.SENT
                self.state.send_count += 1
                self.state.queue_count = self._queue.count()
                self.state.last_sent_at = self._clock()
                self.state.last_error = None
                self._emit_state()

    def _emit_state(self) -> None:
        self._on_state(replace(self.state))

    @staticmethod
    def _preview(raw_json: str) -> str:
        if len(raw_json) <= _PREVIEW_LENGTH:
            return raw_json
        return f"{raw_json[:_PREVIEW_LENGTH]}..."

    @staticmethod
    def _safe_error(operation: str, error: Exception) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            return f"{operation}エラー: HTTP {error.response.status_code}"
        return f"{operation}エラー: {type(error).__name__}"

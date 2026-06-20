"""Async Flet monitor view."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import flet as ft

from lcstats_relay.core.relay import ConnectionManager, ConnectionState, RelayStatus
from lcstats_relay.core.storage import JSONValue

_DEFAULT_SSE_URL = "http://localhost:2145/"
_MAX_LOG_ENTRIES = 100
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_STATUS_LABELS = {
    RelayStatus.STOPPED: "停止中",
    RelayStatus.WAITING: "統計データ待機中",
    RelayStatus.RECEIVED: "ペイロード受信",
    RelayStatus.ARCHIVED: "アーカイブ済み",
    RelayStatus.SENT: "Sheets送信済み",
    RelayStatus.RETRY_QUEUED: "再送待ち",
    RelayStatus.ERROR: "エラー",
}


class PagePort(Protocol):
    """Page operations used by the view."""

    def update(self) -> None:
        """Push changed controls to the client."""


class ManagerPort(Protocol):
    """Connection manager operations used by the view."""

    def start(self) -> None:
        """Start receiving payloads."""

    async def stop(self) -> None:
        """Stop receiving payloads."""


type ManagerFactory = Callable[
    [str, str, Path, Callable[[ConnectionState], None], Callable[[JSONValue], None]],
    ManagerPort,
]


def _create_manager(
    sse_url: str,
    gas_url: str,
    data_dir: Path,
    on_state: Callable[[ConnectionState], None],
    on_payload: Callable[[JSONValue], None],
) -> ManagerPort:
    return ConnectionManager(
        sse_url=sse_url,
        gas_url=gas_url,
        data_dir=data_dir,
        on_state=on_state,
        on_payload=on_payload,
    )


def validate_sse_url(value: str) -> str:
    """Validate and normalize the local stats endpoint URL."""
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in _LOCAL_HOSTS:
        msg = "SSE URLにはlocalhostのHTTP URLを指定してください"
        raise ValueError(msg)
    if parsed.username is not None or parsed.password is not None:
        msg = "SSE URLに認証情報を含めることはできません"
        raise ValueError(msg)
    return url


def validate_gas_url(value: str) -> str:
    """Validate and normalize a Google Apps Script Web App URL."""
    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "script.google.com":
        msg = "GAS URLにはscript.google.comのHTTPS URLを指定してください"
        raise ValueError(msg)
    if not parsed.path.startswith("/macros/s/"):
        msg = "GAS Web Appの実行URLを指定してください"
        raise ValueError(msg)
    return url


class MonitorView:
    """Render relay state and translate user actions into manager calls."""

    def __init__(
        self,
        page: PagePort,
        *,
        data_dir: Path = Path("data"),
        manager_factory: ManagerFactory = _create_manager,
    ) -> None:
        """Create controls and retain injected application boundaries."""
        self._page = page
        self._data_dir = data_dir
        self._manager_factory = manager_factory
        self._manager: ManagerPort | None = None

        self.sse_url = ft.TextField(label="SSE URL", value=_DEFAULT_SSE_URL, expand=True)
        self.gas_url = ft.TextField(
            label="GAS Web App URL",
            password=True,
            can_reveal_password=True,
            expand=True,
        )
        self.start_button = ft.FilledButton(
            "接続開始",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.start,
        )
        self.stop_button = ft.OutlinedButton(
            "停止",
            icon=ft.Icons.STOP,
            on_click=self.stop,
            disabled=True,
        )
        self.status = ft.Text(_STATUS_LABELS[RelayStatus.STOPPED], weight=ft.FontWeight.BOLD)
        self.receive_count = ft.Text("0")
        self.archive_count = ft.Text("0")
        self.send_count = ft.Text("0")
        self.queue_count = ft.Text("0")
        self.last_received = ft.Text("-")
        self.last_archived = ft.Text("-")
        self.last_sent = ft.Text("-")
        self.archive_file = ft.Text("-", selectable=True)
        self.error = ft.Text("", color=ft.Colors.RED_700, selectable=True)
        self.event_list = ft.ListView(expand=True, spacing=6, auto_scroll=True)

    def build(self) -> ft.Column:
        """Build the complete monitor control tree."""
        return ft.Column(
            [
                ft.Text("LCStats Relay", size=26, weight=ft.FontWeight.BOLD),
                ft.Text("受信した統計JSONを保存してGoogle Sheetsへ転送します。"),
                self.sse_url,
                self.gas_url,
                ft.Row([self.start_button, self.stop_button]),
                ft.Divider(),
                ft.Row(
                    [
                        self._metric("状態", self.status),
                        self._metric("受信", self.receive_count),
                        self._metric("保存", self.archive_count),
                        self._metric("送信", self.send_count),
                        self._metric("再送待ち", self.queue_count),
                    ],
                    wrap=True,
                ),
                self._detail("最終受信", self.last_received),
                self._detail("最終保存", self.last_archived),
                self._detail("最終送信", self.last_sent),
                self._detail("保存先", self.archive_file),
                self.error,
                ft.Divider(),
                ft.Text("最近のペイロード", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(
                    content=self.event_list,
                    border=ft.Border.all(1, ft.Colors.GREY_300),
                    border_radius=8,
                    padding=12,
                    expand=True,
                ),
            ],
            expand=True,
            spacing=12,
        )

    async def start(self) -> None:
        """Validate settings and start a new connection manager."""
        try:
            sse_url = validate_sse_url(self.sse_url.value or "")
            gas_url = validate_gas_url(self.gas_url.value or "")
        except ValueError as exc:
            self.error.value = str(exc)
            self._page.update()
            return

        if self._manager is not None:
            await self._manager.stop()
        self._manager = self._manager_factory(
            sse_url,
            gas_url,
            self._data_dir,
            self.update_state,
            self.add_payload,
        )
        self.error.value = ""
        self.start_button.disabled = True
        self.stop_button.disabled = False
        self.sse_url.disabled = True
        self.gas_url.disabled = True
        self._manager.start()
        self._page.update()

    async def stop(self) -> None:
        """Stop the active manager and unlock connection settings."""
        if self._manager is not None:
            await self._manager.stop()
            self._manager = None
        self.start_button.disabled = False
        self.stop_button.disabled = True
        self.sse_url.disabled = False
        self.gas_url.disabled = False
        self._page.update()

    async def close(self) -> None:
        """Stop background work when the desktop window closes."""
        if self._manager is not None:
            await self._manager.stop()
            self._manager = None

    def update_state(self, state: ConnectionState) -> None:
        """Apply a manager state snapshot to visible controls."""
        self.status.value = _STATUS_LABELS[state.status]
        self.receive_count.value = str(state.receive_count)
        self.archive_count.value = str(state.archive_count)
        self.send_count.value = str(state.send_count)
        self.queue_count.value = str(state.queue_count)
        self.last_received.value = self._format_time(state.last_received_at)
        self.last_archived.value = self._format_time(state.last_archived_at)
        self.last_sent.value = self._format_time(state.last_sent_at)
        self.archive_file.value = state.last_archive_file or "-"
        self.error.value = state.last_error or ""
        self._page.update()

    def add_payload(self, payload: JSONValue) -> None:
        """Append a compact JSON preview while bounding UI memory use."""
        rendered = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.event_list.controls.append(ft.Text(f"{timestamp}  {rendered}", selectable=True))
        if len(self.event_list.controls) > _MAX_LOG_ENTRIES:
            self.event_list.controls.pop(0)
        self._page.update()

    @staticmethod
    def _metric(label: str, value: ft.Text) -> ft.Container:
        return ft.Container(
            content=ft.Column([ft.Text(label, color=ft.Colors.GREY_700), value], spacing=4),
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            padding=12,
        )

    @staticmethod
    def _detail(label: str, value: ft.Text) -> ft.Row:
        return ft.Row([ft.Text(f"{label}:", width=90), value], wrap=True)

    @staticmethod
    def _format_time(value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else "-"

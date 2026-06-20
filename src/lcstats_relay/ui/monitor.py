"""Async Flet monitor view."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qsl, urlparse

import flet as ft

from lcstats_relay.core.payload import JSONValue
from lcstats_relay.core.state import ConnectionState, OutputState, OutputStatus, RelayStatus

_DEFAULT_SSE_URL = "http://localhost:2145/"
_MAX_LOG_ENTRIES = 100
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

_STATUS_LABELS = {
    RelayStatus.STOPPED: "停止中",
    RelayStatus.WAITING: "統計データ待機中",
    RelayStatus.RECEIVED: "ペイロード受信",
    RelayStatus.DISPATCHING: "出力処理中",
    RelayStatus.ERROR: "エラー",
}

_OUTPUT_STATUS_LABELS = {
    OutputStatus.IDLE: "待機中",
    OutputStatus.RUNNING: "処理中",
    OutputStatus.SUCCESS: "成功",
    OutputStatus.ERROR: "エラー",
    OutputStatus.RETRY_QUEUED: "再送待ち",
}

_OUTPUT_STATUS_COLORS = {
    OutputStatus.IDLE: ft.Colors.GREY_700,
    OutputStatus.RUNNING: ft.Colors.BLUE_700,
    OutputStatus.SUCCESS: ft.Colors.GREEN_700,
    OutputStatus.ERROR: ft.Colors.RED_700,
    OutputStatus.RETRY_QUEUED: ft.Colors.ORANGE_800,
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
    [
        str,
        str,
        str,
        Path,
        Callable[[ConnectionState], None],
        Callable[[JSONValue], None],
    ],
    ManagerPort,
]


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
    if any(key.lower() == "token" for key, _value in parse_qsl(parsed.query)):
        msg = "GAS tokenはURLではなくToken欄に指定してください"
        raise ValueError(msg)
    return url


class MonitorView:
    """Render relay state and translate user actions into manager calls."""

    def __init__(
        self,
        page: PagePort,
        *,
        data_dir: Path = Path("data"),
        manager_factory: ManagerFactory,
    ) -> None:
        """Create controls and retain injected application boundaries."""
        self._page = page
        self._data_dir = data_dir
        self._manager_factory = manager_factory
        self._manager: ManagerPort | None = None

        self.sse_url = ft.TextField(label="SSE URL", value=_DEFAULT_SSE_URL, expand=True)
        self.gas_url = ft.TextField(label="GAS Web App URL", expand=True)
        self.gas_token = ft.TextField(
            label="GAS Token",
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
        self.last_received = ft.Text("-")
        self.error = ft.Text("", color=ft.Colors.RED_700, selectable=True)
        self.outputs = ft.Column([], spacing=8)
        self.event_list = ft.ListView(expand=True, spacing=6, auto_scroll=True)

    def build(self) -> ft.Column:
        """Build the complete monitor control tree."""
        return ft.Column(
            [
                ft.Text("LCStats Relay", size=26, weight=ft.FontWeight.BOLD),
                ft.Text("受信した統計JSONを保存して設定済みの出力面へ転送します。"),
                self.sse_url,
                self.gas_url,
                self.gas_token,
                ft.Row([self.start_button, self.stop_button]),
                ft.Divider(),
                ft.Row(
                    [
                        self._metric("状態", self.status),
                        self._metric("受信", self.receive_count),
                    ],
                    wrap=True,
                ),
                self._detail("最終受信", self.last_received),
                self.error,
                ft.Text("出力面", size=18, weight=ft.FontWeight.BOLD),
                self.outputs,
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
            (self.gas_token.value or "").strip(),
            self._data_dir,
            self.update_state,
            self.add_payload,
        )
        self.error.value = ""
        self.start_button.disabled = True
        self.stop_button.disabled = False
        self.sse_url.disabled = True
        self.gas_url.disabled = True
        self.gas_token.disabled = True
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
        self.gas_token.disabled = False
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
        self.last_received.value = self._format_time(state.last_received_at)
        self.error.value = state.last_error or ""
        self.outputs.controls = [self._output_card(output) for output in state.outputs.values()]
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
    def _output_card(output: OutputState) -> ft.Container:
        status = ft.Text(
            _OUTPUT_STATUS_LABELS[output.status],
            color=_OUTPUT_STATUS_COLORS[output.status],
            weight=ft.FontWeight.BOLD,
        )
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row([ft.Text(output.label, weight=ft.FontWeight.BOLD), status]),
                    ft.Row(
                        [
                            ft.Text(f"成功: {output.success_count}"),
                            ft.Text(f"失敗: {output.failure_count}"),
                            ft.Text(f"再送待ち: {output.pending_count}"),
                        ],
                        wrap=True,
                    ),
                    ft.Text(output.message, selectable=True),
                    ft.Text(
                        f"最終成功: {MonitorView._format_time(output.last_success_at)}",
                        selectable=True,
                    ),
                ],
                spacing=4,
            ),
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=8,
            padding=12,
        )

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

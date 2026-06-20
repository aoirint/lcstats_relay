"""Async Flet monitor view."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qsl, urlparse

import flet as ft

from lcstats_relay.core.config import RelaySettings, SettingsStore
from lcstats_relay.core.payload import JSONValue
from lcstats_relay.core.state import ConnectionState, OutputState, OutputStatus, RelayStatus

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

_UNHEALTHY_OUTPUT_STATUSES = frozenset({OutputStatus.ERROR, OutputStatus.RETRY_QUEUED})
_DEFAULT_OUTPUT_ORDER = ("archive", "gas")


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
        msg = "LCStatsTracker URLにはlocalhostのHTTP URLを指定してください"
        raise ValueError(msg)
    if parsed.username is not None or parsed.password is not None:
        msg = "LCStatsTracker URLに認証情報を含めることはできません"
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


def validate_data_dir(value: str) -> Path:
    """Validate and normalize the local archive root directory."""
    raw_path = value.strip()
    if not raw_path:
        msg = "ローカル保存先ディレクトリを指定してください"
        raise ValueError(msg)
    return Path(raw_path).expanduser()


class MonitorView:
    """Render relay state and translate user actions into manager calls."""

    def __init__(
        self,
        page: PagePort,
        *,
        settings_store: SettingsStore | None = None,
        manager_factory: ManagerFactory,
    ) -> None:
        """Create controls and retain injected application boundaries."""
        self._page = page
        self._settings_store = settings_store or SettingsStore()
        self._settings = self._settings_store.load()
        self._manager_factory = manager_factory
        self._manager: ManagerPort | None = None
        self._gas_token = ""

        self.settings_summary = ft.Text(selectable=True)
        self.gas_summary = ft.Text(selectable=True)
        self.settings_button = ft.OutlinedButton(
            "設定",
            icon=ft.Icons.SETTINGS,
            on_click=self.open_settings,
        )
        self.gas_auth_button = ft.OutlinedButton(
            "GAS認証",
            icon=ft.Icons.KEY,
            on_click=self.open_gas_auth,
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
        self.health = ft.Text(
            "停止中", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700
        )
        self.health_detail = ft.Text("未接続", selectable=True)
        self.health_icon = ft.Icon(ft.Icons.ERROR_OUTLINE, size=30, color=ft.Colors.RED_700)
        self.receive_count = ft.Text("0")
        self.last_received = ft.Text("-")
        self.error = ft.Text("", color=ft.Colors.RED_700, selectable=True)
        self.tracker_url_field = ft.TextField(label="LCStatsTracker URL", expand=True)
        self.data_dir_field = ft.TextField(label="ローカル保存先ディレクトリ", expand=True)
        self.gas_url_field = ft.TextField(label="GAS Web App URL", expand=True)
        self.gas_token_field = ft.TextField(
            label="GAS Token",
            password=True,
            can_reveal_password=True,
            expand=True,
        )
        self.output_destinations = ft.Column([], spacing=4)
        self.root_view = ft.Column([], spacing=8, expand=True)
        self.root_container = ft.Container(
            content=self.root_view,
            expand=True,
            padding=8,
            border_radius=6,
        )
        self._refresh_settings_summary()
        self._refresh_health(ConnectionState())

    def build(self) -> ft.Container:
        """Build the complete monitor control tree."""
        self._show_monitor_view(update=False)
        return self.root_container

    def open_settings(self, _event: object | None = None) -> None:
        """Switch to the full-window tracker, storage, and output settings view."""
        self.tracker_url_field.value = self._settings.tracker_url
        self.data_dir_field.value = str(self._settings.data_dir)
        self._show_settings_view(update=True)

    def open_gas_auth(self, _event: object | None = None) -> None:
        """Switch to the full-window Google Apps Script settings view."""
        self.gas_url_field.value = self._settings.gas_url
        self.gas_token_field.value = self._gas_token
        self._show_gas_auth_view(update=True)

    def save_settings(self, tracker_url: str, data_dir: str) -> None:
        """Validate and persist tracker plus local storage settings."""
        self._settings = RelaySettings(
            tracker_url=validate_sse_url(tracker_url),
            gas_url=self._settings.gas_url,
            data_dir=validate_data_dir(data_dir),
        )
        self._settings_store.save(self._settings)
        self.error.value = ""
        self._refresh_settings_summary()
        self._page.update()

    def save_gas_auth(self, gas_url: str, gas_token: str) -> None:
        """Validate and persist the GAS destination while keeping the token in memory."""
        normalized_gas_url = validate_gas_url(gas_url) if gas_url.strip() else ""
        self._settings = RelaySettings(
            tracker_url=self._settings.tracker_url,
            gas_url=normalized_gas_url,
            data_dir=self._settings.data_dir,
        )
        self._gas_token = gas_token.strip() if normalized_gas_url else ""
        self._settings_store.save(self._settings)
        self.error.value = ""
        self._refresh_settings_summary()
        self._page.update()

    async def start(self, _event: object | None = None) -> None:
        """Validate settings and start a new connection manager."""
        try:
            tracker_url = validate_sse_url(self._settings.tracker_url)
            gas_url = (
                validate_gas_url(self._settings.gas_url) if self._settings.gas_url.strip() else ""
            )
            data_dir = validate_data_dir(str(self._settings.data_dir))
        except ValueError as exc:
            self.error.value = str(exc)
            self._page.update()
            return

        if self._manager is not None:
            await self._manager.stop()
        self._manager = self._manager_factory(
            tracker_url,
            gas_url,
            self._gas_token,
            data_dir,
            self.update_state,
            self.add_payload,
        )
        self.error.value = ""
        self.start_button.disabled = True
        self.stop_button.disabled = False
        self.settings_button.disabled = True
        self.gas_auth_button.disabled = True
        self._show_monitor_view(update=False)
        self._manager.start()
        self._page.update()

    async def stop(self, _event: object | None = None) -> None:
        """Stop the active manager and unlock connection settings."""
        if self._manager is not None:
            await self._manager.stop()
            self._manager = None
        self.start_button.disabled = False
        self.stop_button.disabled = True
        self.settings_button.disabled = False
        self.gas_auth_button.disabled = False
        self._show_monitor_view(update=False)
        self._page.update()

    async def close(self, _event: object | None = None) -> None:
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
        self._refresh_health(state)
        self._page.update()

    def add_payload(self, payload: JSONValue) -> None:
        """Accept payload callbacks without rendering raw details in the monitor."""

    def _show_monitor_view(self, *, update: bool) -> None:
        self.root_view.controls = [
            ft.Row(
                [
                    ft.Text(
                        "LCStats Relay Monitor", size=20, weight=ft.FontWeight.BOLD, expand=True
                    ),
                    self.settings_button,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Row(
                [
                    self.start_button,
                    self.stop_button,
                ],
                wrap=True,
            ),
            self.error,
            ft.Divider(),
            ft.Row(
                [
                    self._global_alert_panel(),
                    self._output_destinations_panel(),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ]
        if update:
            self._page.update()

    def _show_settings_view(self, *, update: bool) -> None:
        self.root_view.controls = [
            self._full_view_title("設定"),
            ft.Column(
                [
                    self.error,
                    self._settings_section(
                        "接続元",
                        [
                            self.tracker_url_field,
                        ],
                    ),
                    self._settings_section(
                        "出力先",
                        [
                            self.data_dir_field,
                            self._gas_output_setting_row(),
                        ],
                    ),
                ],
                spacing=12,
                expand=True,
            ),
            ft.Row(
                [
                    ft.FilledButton(
                        "保存",
                        icon=ft.Icons.SAVE,
                        on_click=self._save_settings_from_view,
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        ]
        if update:
            self._page.update()

    @staticmethod
    def _settings_section(title: str, controls: list[ft.Control]) -> ft.Column:
        return ft.Column(
            [
                ft.Text(title, size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_700),
                *controls,
            ],
            spacing=6,
        )

    def _gas_output_setting_row(self) -> ft.Container:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text("Google Apps Script", weight=ft.FontWeight.BOLD, expand=True),
                    ft.OutlinedButton(
                        "設定",
                        icon=ft.Icons.KEY,
                        on_click=self._open_gas_auth_from_settings,
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=2,
        )

    def _show_gas_auth_view(self, *, update: bool) -> None:
        self.root_view.controls = [
            self._full_view_title("GAS認証"),
            self.gas_url_field,
            self.gas_token_field,
            ft.Row(
                [
                    ft.FilledButton(
                        "保存",
                        icon=ft.Icons.SAVE,
                        on_click=self._save_gas_auth_from_view,
                    ),
                ],
                wrap=True,
            ),
        ]
        if update:
            self._page.update()

    def _full_view_title(self, title: str) -> ft.Row:
        return ft.Row(
            [
                ft.Text(title, size=20, weight=ft.FontWeight.BOLD, expand=True),
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    tooltip="閉じる",
                    on_click=lambda _event: self._show_monitor_view(update=True),
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _open_gas_auth_from_settings(self, _event: object | None = None) -> None:
        self.open_gas_auth()

    def _save_settings_from_view(self, _event: object | None = None) -> None:
        try:
            self.save_settings(
                self.tracker_url_field.value or "",
                self.data_dir_field.value or "",
            )
        except ValueError as exc:
            self.error.value = str(exc)
            self._page.update()
            return
        self._show_monitor_view(update=True)

    def _save_gas_auth_from_view(self, _event: object | None = None) -> None:
        try:
            self.save_gas_auth(
                self.gas_url_field.value or "",
                self.gas_token_field.value or "",
            )
        except ValueError as exc:
            self.error.value = str(exc)
            self._page.update()
            return
        self.open_settings()

    def _refresh_settings_summary(self) -> None:
        self.settings_summary.value = (
            f"LCStatsTracker: {self._settings.tracker_url} / 保存先: {self._settings.data_dir}"
        )
        gas_state = self._settings.gas_url if self._settings.gas_url else "未設定"
        token_state = "設定済み" if self._gas_token else "未設定"
        self.gas_summary.value = f"GAS: {gas_state} / Token: {token_state}"

    def _refresh_health(self, state: ConnectionState) -> None:
        display_outputs = self._display_outputs(state)
        unhealthy_outputs = [
            output
            for output in display_outputs
            if output.status in _UNHEALTHY_OUTPUT_STATUSES or output.pending_count > 0
        ]
        if state.running and state.receive_count == 0 and not unhealthy_outputs:
            self.health.value = "接続試行中"
            self.health.color = ft.Colors.ORANGE_800
            self.health_icon.icon = ft.Icons.SYNC
            self.health_icon.color = ft.Colors.ORANGE_800
            self.health_detail.value = "再試行中" if state.last_error else "待機中"
        elif state.last_error:
            self.health.value = "要確認"
            self.health.color = ft.Colors.RED_700
            self.health_icon.icon = ft.Icons.ERROR_OUTLINE
            self.health_icon.color = ft.Colors.RED_700
            self.health_detail.value = state.last_error
        elif unhealthy_outputs:
            self.health.value = "要確認"
            self.health.color = ft.Colors.RED_700
            self.health_icon.icon = ft.Icons.WARNING_AMBER
            self.health_icon.color = ft.Colors.RED_700
            self.health_detail.value = "出力先を確認"
        elif state.running:
            self.health.value = "異常なし"
            self.health.color = ft.Colors.GREEN_700
            self.health_icon.icon = ft.Icons.CHECK_CIRCLE
            self.health_icon.color = ft.Colors.GREEN_700
            self.health_detail.value = "監視中"
        else:
            self.health.value = "停止中"
            self.health.color = ft.Colors.GREY_700
            self.health_icon.icon = ft.Icons.ERROR_OUTLINE
            self.health_icon.color = ft.Colors.RED_700
            self.health_detail.value = "未接続"

        self.output_destinations.controls = [
            self._output_destination(output, connected=state.running) for output in display_outputs
        ]

    def _display_outputs(self, state: ConnectionState) -> list[OutputState]:
        if state.outputs and not any(key in state.outputs for key in _DEFAULT_OUTPUT_ORDER):
            return list(state.outputs.values())
        outputs = self._default_output_states() | state.outputs
        return [outputs[key] for key in _DEFAULT_OUTPUT_ORDER if key in outputs]

    def _default_output_states(self) -> dict[str, OutputState]:
        outputs = {
            "archive": OutputState(key="archive", label="ローカル保存"),
        }
        if self._settings.gas_url:
            outputs["gas"] = OutputState(key="gas", label="Google Sheets")
        return outputs

    def _global_alert_panel(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row([self.health_icon, self.health], spacing=8),
                    self.health_detail,
                ],
                spacing=4,
            ),
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=6,
            padding=8,
            expand=1,
        )

    def _output_destinations_panel(self) -> ft.Container:
        return ft.Container(
            content=self.output_destinations,
            expand=1,
        )

    @staticmethod
    def _output_destination(output: OutputState, *, connected: bool) -> ft.Container:
        status_label = _OUTPUT_STATUS_LABELS[output.status]
        status_color = _OUTPUT_STATUS_COLORS[output.status]
        if output.status == OutputStatus.IDLE and not connected:
            status_label = "未接続"
            status_color = ft.Colors.GREY_700
        status = ft.Text(
            status_label,
            color=status_color,
            weight=ft.FontWeight.BOLD,
        )
        icon = MonitorView._output_icon(output, connected=connected)
        controls: list[ft.Control] = [
            ft.Row(
                [
                    icon,
                    ft.Text(output.label, weight=ft.FontWeight.BOLD, expand=True),
                    status,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        ]
        if output.status in _UNHEALTHY_OUTPUT_STATUSES or output.pending_count > 0:
            controls.append(ft.Text(output.message, selectable=True))
        return ft.Container(
            content=ft.Column(controls, spacing=2),
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=6,
            padding=8,
        )

    @staticmethod
    def _output_icon(output: OutputState, *, connected: bool) -> ft.Icon:
        if output.status == OutputStatus.ERROR:
            return ft.Icon(ft.Icons.ERROR_OUTLINE, color=ft.Colors.RED_700)
        if output.status == OutputStatus.RETRY_QUEUED or output.pending_count > 0:
            return ft.Icon(ft.Icons.WARNING_AMBER, color=ft.Colors.ORANGE_800)
        if output.status == OutputStatus.SUCCESS:
            return ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_700)
        if output.status == OutputStatus.RUNNING:
            return ft.Icon(ft.Icons.SYNC, color=ft.Colors.BLUE_700)
        if not connected:
            return ft.Icon(ft.Icons.LINK_OFF, color=ft.Colors.GREY_700)
        return ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, color=ft.Colors.GREY_700)

    @staticmethod
    def _format_time(value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else "-"

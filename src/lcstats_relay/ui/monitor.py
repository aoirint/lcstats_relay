"""Async Flet monitor view."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import flet as ft

from lcstats_relay.application.settings import RelaySettings
from lcstats_relay.application.state import ConnectionState
from lcstats_relay.domain.payload import JSONValue
from lcstats_relay.infrastructure.config import SettingsStore
from lcstats_relay.presentation.models import OutputViewState, StatusGlyph, Tone
from lcstats_relay.presentation.presenters import present_relay, settings_summaries
from lcstats_relay.presentation.validation import (
    validate_data_dir,
    validate_gas_url,
    validate_sse_url,
)

_TONE_COLORS = {
    Tone.NEUTRAL: ft.Colors.GREY_700,
    Tone.INFO: ft.Colors.BLUE_700,
    Tone.SUCCESS: ft.Colors.GREEN_700,
    Tone.WARNING: ft.Colors.ORANGE_800,
    Tone.ERROR: ft.Colors.RED_700,
}

_STATUS_ICONS = {
    StatusGlyph.CHECK: ft.Icons.CHECK_CIRCLE,
    StatusGlyph.ERROR: ft.Icons.ERROR_OUTLINE,
    StatusGlyph.IDLE: ft.Icons.RADIO_BUTTON_UNCHECKED,
    StatusGlyph.LINK_OFF: ft.Icons.LINK_OFF,
    StatusGlyph.SYNC: ft.Icons.SYNC,
    StatusGlyph.WARNING: ft.Icons.WARNING_AMBER,
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


class ManagerFactory(Protocol):
    """Create a connection manager from validated settings and callbacks."""

    def __call__(  # noqa: PLR0913 - the composition boundary receives one complete session.
        self,
        *,
        sse_url: str,
        gas_url: str,
        gas_token: str,
        data_dir: Path,
        on_state: Callable[[ConnectionState], None],
        on_payload: Callable[[JSONValue], None],
    ) -> ManagerPort:
        """Build one manager for a connection session."""


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
        self.status = ft.Text("停止中", weight=ft.FontWeight.BOLD)
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
        self._show_settings_view()

    def open_gas_auth(self, _event: object | None = None) -> None:
        """Switch to the full-window Google Apps Script settings view."""
        self.gas_url_field.value = self._settings.gas_url
        self.gas_token_field.value = self._gas_token
        self._show_gas_auth_view()

    def save_settings(self, tracker_url: str, *, data_dir: str) -> None:
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

    def save_gas_auth(self, gas_url: str, *, gas_token: str) -> None:
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
            sse_url=tracker_url,
            gas_url=gas_url,
            gas_token=self._gas_token,
            data_dir=data_dir,
            on_state=self.update_state,
            on_payload=self.add_payload,
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
        relay = present_relay(state, gas_enabled=bool(self._settings.gas_url))
        self.status.value = relay.status_label
        self.receive_count.value = relay.receive_count
        self.last_received.value = relay.last_received
        self.error.value = relay.error
        self.health.value = relay.health.label
        self.health.color = _TONE_COLORS[relay.health.tone]
        self.health_icon.icon = _STATUS_ICONS[relay.health.glyph]
        self.health_icon.color = _TONE_COLORS[relay.health.glyph_tone]
        self.health_detail.value = relay.health.detail
        self.output_destinations.controls = [
            self._output_destination(output) for output in relay.outputs
        ]
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

    def _show_settings_view(self) -> None:
        self.root_view.controls = [
            self._full_view_title("設定"),
            ft.Column(
                [
                    self.error,
                    self._settings_section(
                        "接続元",
                        controls=[
                            self.tracker_url_field,
                        ],
                    ),
                    self._settings_section(
                        "出力先",
                        controls=[
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
                        on_click=self.submit_settings,
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        ]
        self._page.update()

    @staticmethod
    def _settings_section(title: str, *, controls: list[ft.Control]) -> ft.Column:
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

    def _show_gas_auth_view(self) -> None:
        self.root_view.controls = [
            self._full_view_title("GAS認証"),
            self.gas_url_field,
            self.gas_token_field,
            ft.Row(
                [
                    ft.FilledButton(
                        "保存",
                        icon=ft.Icons.SAVE,
                        on_click=self.submit_gas_auth,
                    ),
                ],
                wrap=True,
            ),
        ]
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

    def submit_settings(self, _event: object | None = None) -> None:
        """Validate the visible settings fields and return to the monitor on success."""
        try:
            self.save_settings(
                self.tracker_url_field.value or "",
                data_dir=self.data_dir_field.value or "",
            )
        except ValueError as exc:
            self.error.value = str(exc)
            self._page.update()
            return
        self._show_monitor_view(update=True)

    def submit_gas_auth(self, _event: object | None = None) -> None:
        """Validate the visible GAS fields and return to settings on success."""
        try:
            self.save_gas_auth(
                self.gas_url_field.value or "",
                gas_token=self.gas_token_field.value or "",
            )
        except ValueError as exc:
            self.error.value = str(exc)
            self._page.update()
            return
        self.open_settings()

    def _refresh_settings_summary(self) -> None:
        settings, gas = settings_summaries(
            tracker_url=self._settings.tracker_url,
            data_dir=str(self._settings.data_dir),
            gas_url=self._settings.gas_url,
            has_gas_token=bool(self._gas_token),
        )
        self.settings_summary.value = settings
        self.gas_summary.value = gas

    def _refresh_health(self, state: ConnectionState) -> None:
        relay = present_relay(state, gas_enabled=bool(self._settings.gas_url))
        self.health.value = relay.health.label
        self.health.color = _TONE_COLORS[relay.health.tone]
        self.health_icon.icon = _STATUS_ICONS[relay.health.glyph]
        self.health_icon.color = _TONE_COLORS[relay.health.glyph_tone]
        self.health_detail.value = relay.health.detail
        self.output_destinations.controls = [
            self._output_destination(output) for output in relay.outputs
        ]

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
    def _output_destination(output: OutputViewState) -> ft.Container:
        status = ft.Text(
            output.status_label,
            color=_TONE_COLORS[output.tone],
            weight=ft.FontWeight.BOLD,
        )
        icon = ft.Icon(_STATUS_ICONS[output.glyph], color=_TONE_COLORS[output.glyph_tone])
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
        if output.detail is not None:
            controls.append(ft.Text(output.detail, selectable=True))
        return ft.Container(
            content=ft.Column(controls, spacing=2),
            border=ft.Border.all(1, ft.Colors.GREY_300),
            border_radius=6,
            padding=8,
        )

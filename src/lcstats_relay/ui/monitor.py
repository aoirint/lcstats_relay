"""Async Flet monitor view."""

from __future__ import annotations

from typing import Protocol

import flet as ft

from lcstats_relay.application.state import ConnectionState
from lcstats_relay.domain.payload import JSONValue
from lcstats_relay.presentation.controller import MonitorController
from lcstats_relay.presentation.models import OutputViewState, StatusGlyph, Tone
from lcstats_relay.presentation.presenters import present_relay, settings_summaries

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
    """Page operation required by the monitor adapter."""

    def update(self) -> None:
        """Push changed controls to the client."""


class MonitorView:
    """Render relay state and translate user actions into manager calls."""

    def __init__(
        self,
        *,
        page: PagePort,
        controller: MonitorController,
    ) -> None:
        """Create controls and bind them to a Flet-free controller."""
        self._page = page
        self._controller = controller

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
        self._controller.bind(on_change=self._controller_changed, on_payload=self.add_payload)
        self._refresh_settings_summary()
        self._apply_relay(state=self._controller.relay_state)

    def build(self) -> ft.Container:
        """Build the complete monitor control tree."""
        self._show_monitor_view(update=False)
        return self.root_container

    def open_settings(  # keyword-only-exception: Flet event callback ABI
        self, _event: object | None = None
    ) -> None:
        """Switch to the full-window tracker, storage, and output settings view."""
        self.tracker_url_field.value = self._controller.settings.tracker_url
        self.data_dir_field.value = str(self._controller.settings.data_dir)
        self._show_settings_view()

    def open_gas_auth(  # keyword-only-exception: Flet event callback ABI
        self, _event: object | None = None
    ) -> None:
        """Switch to the full-window Google Apps Script settings view."""
        self.gas_url_field.value = self._controller.settings.gas_url
        self.gas_token_field.value = ""
        self._show_gas_auth_view()

    def save_settings(self, *, tracker_url: str, data_dir: str) -> bool:
        """Validate and persist tracker plus local storage settings."""
        return self._controller.save_settings(tracker_url=tracker_url, data_dir=data_dir)

    def save_gas_auth(self, *, gas_url: str, gas_token: str) -> bool:
        """Validate and persist the GAS destination while keeping the token in memory."""
        return self._controller.save_gas_auth(gas_url=gas_url, gas_token=gas_token)

    async def start(  # keyword-only-exception: Flet event callback ABI
        self, _event: object | None = None
    ) -> None:
        """Validate settings and start a new connection manager."""
        if not await self._controller.start():
            return
        self._show_monitor_view(update=False)

    async def stop(  # keyword-only-exception: Flet event callback ABI
        self, _event: object | None = None
    ) -> None:
        """Stop the active manager and unlock connection settings."""
        await self._controller.stop()
        self._show_monitor_view(update=False)

    async def close(  # keyword-only-exception: Flet event callback ABI
        self, _event: object | None = None
    ) -> None:
        """Stop background work when the desktop window closes."""
        await self._controller.close()

    def update_state(self, *, state: ConnectionState) -> None:
        """Apply a manager state snapshot to visible controls."""
        self._apply_relay(state=state)
        self._page.update()

    def _apply_relay(self, *, state: ConnectionState) -> None:
        relay = present_relay(state=state, gas_enabled=bool(self._controller.settings.gas_url))
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
            self._output_destination(output=output) for output in relay.outputs
        ]

    def add_payload(self, *, payload: JSONValue) -> None:
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
            self._full_view_title(title="設定"),
            ft.Column(
                [
                    self.error,
                    self._settings_section(
                        title="接続元",
                        controls=[
                            self.tracker_url_field,
                        ],
                    ),
                    self._settings_section(
                        title="出力先",
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
    def _settings_section(*, title: str, controls: list[ft.Control]) -> ft.Column:
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
            self._full_view_title(title="GAS認証"),
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

    def _full_view_title(self, *, title: str) -> ft.Row:
        return ft.Row(
            [
                ft.Text(title, size=20, weight=ft.FontWeight.BOLD, expand=True),
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    tooltip="閉じる",
                    on_click=self._close_full_view,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    def _close_full_view(  # keyword-only-exception: Flet event callback ABI
        self, _event: object | None = None
    ) -> None:
        self._show_monitor_view(update=True)

    def _open_gas_auth_from_settings(  # keyword-only-exception: Flet event callback ABI
        self, _event: object | None = None
    ) -> None:
        self.open_gas_auth()

    def submit_settings(  # keyword-only-exception: Flet event callback ABI
        self, _event: object | None = None
    ) -> None:
        """Validate the visible settings fields and return to the monitor on success."""
        if not self.save_settings(
            tracker_url=self.tracker_url_field.value or "",
            data_dir=self.data_dir_field.value or "",
        ):
            return
        self._show_monitor_view(update=True)

    def submit_gas_auth(  # keyword-only-exception: Flet event callback ABI
        self, _event: object | None = None
    ) -> None:
        """Validate the visible GAS fields and return to settings on success."""
        if not self.save_gas_auth(
            gas_url=self.gas_url_field.value or "",
            gas_token=self.gas_token_field.value or "",
        ):
            return
        self.open_settings()

    def _refresh_settings_summary(self) -> None:
        settings, gas = settings_summaries(
            tracker_url=self._controller.settings.tracker_url,
            data_dir=str(self._controller.settings.data_dir),
            gas_url=self._controller.settings.gas_url,
            has_gas_token=self._controller.gas_token_configured,
        )
        self.settings_summary.value = settings
        self.gas_summary.value = gas

    def _controller_changed(self) -> None:
        self._apply_relay(state=self._controller.relay_state)
        self.error.value = self._controller.error
        self.start_button.disabled = self._controller.active
        self.stop_button.disabled = not self._controller.active
        self.settings_button.disabled = self._controller.active
        self.gas_auth_button.disabled = self._controller.active
        self._refresh_settings_summary()
        self._page.update()

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
    def _output_destination(*, output: OutputViewState) -> ft.Container:
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

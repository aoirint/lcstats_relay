"""Flet desktop application entry point."""

from __future__ import annotations

import flet as ft
from flet_secure_storage import SecureStorage, WindowsOptions

from lcstats_relay.composition.application import create_monitor_controller
from lcstats_relay.infrastructure.diagnostics import logging_session
from lcstats_relay.ui.credentials import FletTokenStore, credential_store_name
from lcstats_relay.ui.monitor import MonitorView


async def main(page: ft.Page) -> None:  # noqa: PLR0917 -- keyword-only-exception: Flet target ABI
    """Configure the desktop page and mount the async monitor view."""
    page.title = "LCStats Relay"
    page.window.min_width = 420
    page.window.min_height = 300
    page.padding = 8

    controller = create_monitor_controller(
        token_store=FletTokenStore(
            storage=SecureStorage(windows_options=WindowsOptions(use_backward_compatibility=False)),
            native=not page.web,
        )
    )
    await controller.restore_gas_token()
    view = MonitorView(
        page=page,
        controller=controller,
        credential_store_name=credential_store_name(platform=page.platform),
    )
    page.on_close = view.close
    page.add(view.build())


def run() -> None:
    """Start the Flet desktop runtime."""
    with logging_session():
        ft.run(main)

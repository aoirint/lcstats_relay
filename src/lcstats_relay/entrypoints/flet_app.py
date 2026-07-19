"""Flet desktop application entry point."""

from __future__ import annotations

import flet as ft

from lcstats_relay.composition.application import create_monitor_controller
from lcstats_relay.ui.monitor import MonitorView


async def main(page: ft.Page) -> None:
    """Configure the desktop page and mount the async monitor view."""
    page.title = "LCStats Relay"
    page.window.min_width = 420
    page.window.min_height = 300
    page.padding = 8

    view = MonitorView(page, controller=create_monitor_controller())
    page.on_close = view.close
    page.add(view.build())


def run() -> None:
    """Start the Flet desktop runtime."""
    ft.run(main)

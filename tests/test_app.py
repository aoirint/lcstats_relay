"""Tests for Flet application assembly."""

import asyncio
from typing import cast

import flet as ft
import pytest

from lcstats_relay.app import main as package_main
from lcstats_relay.app import run
from lcstats_relay.app.main import main
from lcstats_relay.ui.monitor import MonitorView

_WINDOW_MIN_WIDTH = 760
_WINDOW_MIN_HEIGHT = 640
_PAGE_PADDING = 20


class _FakeWindow:
    min_width: int | None = None
    min_height: int | None = None


class _FakePage:
    def __init__(self) -> None:
        self.title: str | None = None
        self.window = _FakeWindow()
        self.padding: int | None = None
        self.on_close = None
        self.controls: list[ft.Control] = []

    def add(self, *controls: ft.Control) -> None:
        self.controls.extend(controls)


def test_main_configures_and_mounts_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure the window, close handler, and root monitor control."""
    page = _FakePage()
    root = ft.Column()

    monkeypatch.setattr(MonitorView, "build", lambda _self: root)
    asyncio.run(main(cast("ft.Page", page)))

    assert page.title == "LCStats Relay"
    assert page.window.min_width == _WINDOW_MIN_WIDTH
    assert page.window.min_height == _WINDOW_MIN_HEIGHT
    assert page.padding == _PAGE_PADDING
    assert page.on_close is not None
    assert page.controls == [root]


def test_run_starts_flet_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pass the async page target to the Flet runtime."""
    targets: list[object] = []
    monkeypatch.setattr(ft, "run", targets.append)

    run()

    assert targets == [main]
    assert package_main is main

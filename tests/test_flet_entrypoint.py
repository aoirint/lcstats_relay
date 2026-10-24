"""Tests for the Flet runtime entry point."""

import asyncio
import json
import struct
import sys
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import flet as ft
import pytest
from credential_fakes import MemoryTokens

from lcstats_relay.entrypoints import flet_app
from lcstats_relay.entrypoints.flet_app import main, run
from lcstats_relay.ui.monitor import MonitorView

_WINDOW_MIN_WIDTH = 420
_WINDOW_MIN_HEIGHT = 300
_PAGE_PADDING = 8
_RENDER_SIZE = (640, 480)


@pytest.fixture(autouse=True)
def _isolated_settings(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("LCSTATS_RELAY_STARTUP_CHECK", raising=False)


class _FakeWindow:
    min_width: int | None = None
    min_height: int | None = None
    destroyed: bool = False

    async def wait_until_ready_to_show(self) -> None:
        pass

    async def destroy(self) -> None:
        self.destroyed = True


class _FakePage:
    def __init__(self) -> None:
        self.platform = ft.PagePlatform.WINDOWS
        self.web = False
        self.title: str | None = None
        self.fonts: dict[str, str] = {}
        self.theme: ft.Theme | None = None
        self.dark_theme: ft.Theme | None = None
        self.window = _FakeWindow()
        self.padding: int | None = None
        self.on_close: object | None = None
        self.controls: list[ft.Control] = []

    def add(  # keyword-only-exception: Flet Page ABI
        self, *controls: ft.Control
    ) -> None:
        self.controls.extend(controls)

    def update(self) -> None:
        pass


def test_main_configures_and_mounts_monitor(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Configure the window, close handler, and root monitor control."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    page = _FakePage()
    root = ft.Column()

    def build(  # keyword-only-exception: monkeypatched Flet control method ABI
        _self: MonitorView,
    ) -> ft.Control:
        return root

    monkeypatch.setattr(MonitorView, "build", build)
    asyncio.run(main(cast("ft.Page", page)))

    assert page.title == "LCStats Relay"
    assert set(page.fonts) == {"NotoSansJP"}
    font = Path(page.fonts["NotoSansJP"])
    assert font.is_absolute()
    assert font.is_file()
    assert page.theme is not None
    assert page.theme.font_family == "NotoSansJP"
    assert page.dark_theme is not None
    assert page.dark_theme.font_family == "NotoSansJP"
    assert page.window.min_width == _WINDOW_MIN_WIDTH
    assert page.window.min_height == _WINDOW_MIN_HEIGHT
    assert page.padding == _PAGE_PADDING
    assert page.on_close is not None
    assert page.controls == [root]


def test_run_starts_flet_runtime(*, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Pass the async page target to the Flet runtime."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    runner = Mock()
    monkeypatch.setattr(ft, "run", runner)

    run()

    assert runner.call_count == 1
    assert runner.call_args.args == (main,)
    assets = Path(runner.call_args.kwargs["assets_dir"])
    assert (assets / "fonts/NotoSansJP.ttf").is_file()
    assert (assets / "fonts/OFL.txt").is_file()


@pytest.mark.parametrize("valid_png", [True, False])
def test_packaged_startup_requires_a_rendered_page(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, valid_png: bool
) -> None:
    """Accept native rendering evidence and close cleanly on a failed capture."""
    page = _FakePage()
    report = tmp_path / "startup.json"
    (tmp_path / "VERSION").write_text("0.1.0-alpha.1", encoding="ascii")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "lcstats-relay.exe"))
    monkeypatch.setenv("LCSTATS_RELAY_STARTUP_CHECK", str(report))
    png = b"\x89PNG\r\n\x1a\n" + bytes(8) + struct.pack(">II", *_RENDER_SIZE)

    async def capture(  # keyword-only-exception: monkeypatched Flet Screenshot.capture method ABI
        _self: ft.Screenshot, *, delay: object = None
    ) -> bytes:
        del _self, delay
        return png if valid_png else b"not a PNG"

    monkeypatch.setattr(ft.Screenshot, "capture", capture)
    if valid_png:
        monkeypatch.setenv("LCSTATS_RELAY_PROBE_PHASE", "absent")
        monkeypatch.setenv("LCSTATS_RELAY_PROBE_VALUE", "inert-fixture")
        monkeypatch.setattr(flet_app, "FletTokenStore", lambda **_options: MemoryTokens())
    if valid_png:
        asyncio.run(main(cast("ft.Page", page)))
        data = json.loads(report.read_text(encoding="utf-8"))
        assert data["version"] == "0.1.0-alpha.1"
        assert data["page_title"] == "LCStats Relay"
        assert (data["width"], data["height"]) == _RENDER_SIZE
        assert report.with_suffix(".png").read_bytes() == png
    else:
        with pytest.raises(ValueError, match="PNG"):
            asyncio.run(main(cast("ft.Page", page)))
        assert not report.exists()
    assert page.window.destroyed


@pytest.mark.parametrize("case", ["roundtrip", "lost", "retained", "unknown"])
def test_native_credential_probe_requires_restart_persistence_and_deletion(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, case: str
) -> None:
    """Do not emit readiness evidence for lost or resurrected OS credentials."""
    store = MemoryTokens()
    report = tmp_path / "startup.json"
    (tmp_path / "VERSION").write_text("0.1.0-alpha.1", encoding="ascii")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "lcstats-relay.exe"))
    monkeypatch.setattr(flet_app, "FletTokenStore", lambda **_options: store)
    monkeypatch.setenv("LCSTATS_RELAY_STARTUP_CHECK", str(report))
    monkeypatch.setenv("LCSTATS_RELAY_PROBE_VALUE", "inert-fixture")

    async def capture(  # keyword-only-exception: monkeypatched Flet Screenshot.capture method ABI
        _self: ft.Screenshot, *, delay: object = None
    ) -> bytes:
        del _self, delay
        return b"\x89PNG\r\n\x1a\n" + bytes(8) + struct.pack(">II", *_RENDER_SIZE)

    monkeypatch.setattr(ft.Screenshot, "capture", capture)
    phases = (
        ["write", "read-delete", "absent"]
        if case == "roundtrip"
        else ["write", {"lost": "read-delete", "retained": "absent", "unknown": "unknown"}[case]]
    )
    for index, phase in enumerate(phases):
        monkeypatch.setenv("LCSTATS_RELAY_PROBE_PHASE", phase)
        report.unlink(missing_ok=True)
        page = _FakePage()
        if case == "lost" and index:
            store.values.clear()
        if index and case != "roundtrip":
            with pytest.raises(ValueError, match=r"Credential|Deleted|Unknown"):
                asyncio.run(main(cast("ft.Page", page)))
            assert not report.exists()
        else:
            asyncio.run(main(cast("ft.Page", page)))
            assert report.exists()
        assert page.window.destroyed

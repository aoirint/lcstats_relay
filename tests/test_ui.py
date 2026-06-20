"""Tests for monitor control state and async actions."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import flet as ft
import pytest

from lcstats_relay.core.relay import ConnectionManager, ConnectionState, RelayStatus
from lcstats_relay.core.storage import JSONValue
from lcstats_relay.ui.monitor import (
    MonitorView,
    _create_manager,
    validate_gas_url,
    validate_sse_url,
)

_PAYLOAD_LIMIT = 100
_PAYLOAD_CALLS = 101


class _FakePage:
    def __init__(self) -> None:
        self.update_count = 0

    def update(self) -> None:
        self.update_count += 1


class _FakeManager:
    def __init__(self) -> None:
        self.start_count = 0
        self.stop_count = 0

    def start(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1


def test_url_validation_accepts_expected_endpoints() -> None:
    """Accept the local source and deployed Apps Script endpoint shapes."""
    assert validate_sse_url(" http://localhost:2145/ ") == "http://localhost:2145/"
    assert validate_sse_url("http://127.0.0.1:2145/") == "http://127.0.0.1:2145/"
    assert validate_sse_url("http://[::1]:2145/") == "http://[::1]:2145/"
    gas_url = "https://script.google.com/macros/s/deployment-id/exec?token=secret"
    assert validate_gas_url(gas_url) == gas_url


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("https://localhost:2145/", "localhost"),
        ("http://example.com:2145/", "localhost"),
        ("http://user:password@localhost:2145/", "認証情報"),
    ],
)
def test_sse_url_validation_rejects_unsafe_endpoint(value: str, message: str) -> None:
    """Restrict the receiver to an unauthenticated local HTTP endpoint."""
    with pytest.raises(ValueError, match=message):
        validate_sse_url(value)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("http://script.google.com/macros/s/id/exec", "HTTPS"),
        ("https://example.com/macros/s/id/exec", "HTTPS"),
        ("https://script.google.com/not-a-web-app", "実行URL"),
    ],
)
def test_gas_url_validation_rejects_unexpected_endpoint(value: str, message: str) -> None:
    """Prevent forwarding archived stats to an unintended host."""
    with pytest.raises(ValueError, match=message):
        validate_gas_url(value)


def test_start_validates_inputs_before_creating_manager(tmp_path: Path) -> None:
    """Keep controls editable and show an error when settings are incomplete."""

    async def scenario() -> None:
        page = _FakePage()
        view = MonitorView(page, data_dir=tmp_path)

        await view.start()

        assert view.error.value == "GAS URLにはscript.google.comのHTTPS URLを指定してください"
        assert view.start_button.disabled is False
        assert page.update_count == 1

    asyncio.run(scenario())


def test_start_replaces_manager_and_stop_unlocks_settings(tmp_path: Path) -> None:
    """Wire validated controls to one manager and replace an earlier instance safely."""

    async def scenario() -> None:
        page = _FakePage()
        managers: list[_FakeManager] = []
        arguments: list[tuple[str, str, Path]] = []

        def factory(
            sse_url: str,
            gas_url: str,
            data_dir: Path,
            _on_state: Callable[[ConnectionState], None],
            _on_payload: Callable[[JSONValue], None],
        ) -> _FakeManager:
            arguments.append((sse_url, gas_url, data_dir))
            manager = _FakeManager()
            managers.append(manager)
            return manager

        view = MonitorView(page, data_dir=tmp_path, manager_factory=factory)
        view.gas_url.value = "https://script.google.com/macros/s/id/exec?token=secret"

        await view.start()
        await view.start()

        assert arguments == [
            ("http://localhost:2145/", view.gas_url.value, tmp_path),
            ("http://localhost:2145/", view.gas_url.value, tmp_path),
        ]
        assert managers[0].start_count == 1
        assert managers[0].stop_count == 1
        assert managers[1].start_count == 1
        assert view.start_button.disabled is True
        assert view.stop_button.disabled is False
        assert view.sse_url.disabled is True
        assert view.gas_url.disabled is True

        await view.stop()
        await view.stop()

        assert managers[1].stop_count == 1
        assert view.start_button.disabled is False
        assert view.stop_button.disabled is True
        assert view.sse_url.disabled is False
        assert view.gas_url.disabled is False

    asyncio.run(scenario())


def test_close_stops_active_manager(tmp_path: Path) -> None:
    """Stop background work without issuing a page update during window shutdown."""

    async def scenario() -> None:
        page = _FakePage()
        manager = _FakeManager()

        def factory(
            _sse_url: str,
            _gas_url: str,
            _data_dir: Path,
            _on_state: Callable[[ConnectionState], None],
            _on_payload: Callable[[JSONValue], None],
        ) -> _FakeManager:
            return manager

        view = MonitorView(page, data_dir=tmp_path, manager_factory=factory)
        view.gas_url.value = "https://script.google.com/macros/s/id/exec"
        await view.start()
        updates_before_close = page.update_count

        await view.close()
        await view.close()

        assert manager.stop_count == 1
        assert page.update_count == updates_before_close

    asyncio.run(scenario())


def test_build_and_state_update_render_monitor(tmp_path: Path) -> None:
    """Build the page and format every observable state field."""
    page = _FakePage()
    view = MonitorView(page, data_dir=tmp_path)

    control = view.build()
    state = ConnectionState(
        status=RelayStatus.RETRY_QUEUED,
        running=True,
        receive_count=4,
        archive_count=3,
        send_count=2,
        queue_count=1,
        last_received_at=datetime(2026, 6, 20, 9, 15, 33),
        last_archived_at=datetime(2026, 6, 20, 9, 15, 34),
        last_sent_at=datetime(2026, 6, 20, 9, 15, 35),
        last_archive_file="data/archive/2026-06-20/payload.json",
        last_error="Sheets送信エラー: HTTP 503",
    )
    view.update_state(state)

    assert isinstance(control, ft.Column)
    assert view.status.value == "再送待ち"
    assert view.receive_count.value == "4"
    assert view.archive_count.value == "3"
    assert view.send_count.value == "2"
    assert view.queue_count.value == "1"
    assert view.last_received.value == "2026-06-20 09:15:33"
    assert view.last_archived.value == "2026-06-20 09:15:34"
    assert view.last_sent.value == "2026-06-20 09:15:35"
    assert view.archive_file.value == "data/archive/2026-06-20/payload.json"
    assert view.error.value == "Sheets送信エラー: HTTP 503"

    view.update_state(ConnectionState())
    assert view.last_received.value == "-"
    assert view.archive_file.value == "-"
    assert view.error.value == ""


def test_payload_log_is_bounded(tmp_path: Path) -> None:
    """Retain only the latest 100 rendered payloads."""
    page = _FakePage()
    view = MonitorView(page, data_dir=tmp_path)

    for seed in range(_PAYLOAD_CALLS):
        view.add_payload({"Seed": seed})

    assert len(view.event_list.controls) == _PAYLOAD_LIMIT
    first = view.event_list.controls[0]
    last = view.event_list.controls[-1]
    assert isinstance(first, ft.Text)
    assert isinstance(last, ft.Text)
    assert first.value is not None
    assert '"Seed":1' in first.value
    assert last.value is not None
    assert '"Seed":100' in last.value
    assert page.update_count == _PAYLOAD_CALLS


def test_default_manager_factory_builds_core_manager(tmp_path: Path) -> None:
    """Assemble the concrete core manager at the UI boundary."""
    manager = _create_manager(
        "http://localhost:2145/",
        "https://script.google.com/macros/s/id/exec",
        tmp_path,
        lambda _state: None,
        lambda _payload: None,
    )
    assert isinstance(manager, ConnectionManager)

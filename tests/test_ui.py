"""Tests for monitor control state and async actions."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from lcstats_relay.core.config import DEFAULT_TRACKER_URL, SettingsStore
from lcstats_relay.core.payload import JSONValue
from lcstats_relay.core.state import ConnectionState, OutputState, OutputStatus, RelayStatus
from lcstats_relay.ui.monitor import (
    MonitorView,
    validate_data_dir,
    validate_gas_url,
    validate_sse_url,
)

_PAYLOAD_CALLS = 101


class _FakePage:
    def __init__(self) -> None:
        self.update_count = 0
        self.dialogs: list[ft.AlertDialog] = []

    def update(self) -> None:
        self.update_count += 1

    def show_dialog(self, dialog: ft.AlertDialog) -> None:
        dialog.open = True
        self.dialogs.append(dialog)

    def pop_dialog(self) -> ft.AlertDialog | None:
        if not self.dialogs:
            return None
        dialog = self.dialogs.pop()
        dialog.open = False
        return dialog


class _FakeManager:
    def __init__(self) -> None:
        self.start_count = 0
        self.stop_count = 0

    def start(self) -> None:
        self.start_count += 1

    async def stop(self) -> None:
        self.stop_count += 1


def _factory_for(
    manager: _FakeManager,
) -> Callable[
    [
        str,
        str,
        str,
        Path,
        Callable[[ConnectionState], None],
        Callable[[JSONValue], None],
    ],
    _FakeManager,
]:
    def create(
        _sse_url: str,
        _gas_url: str,
        _gas_token: str,
        _data_dir: Path,
        _on_state: Callable[[ConnectionState], None],
        _on_payload: Callable[[JSONValue], None],
    ) -> _FakeManager:
        return manager

    return create


def _settings_store(tmp_path: Path) -> SettingsStore:
    return SettingsStore(tmp_path / "settings.json")


def _active_heading(view: MonitorView) -> str | None:
    header = cast("ft.Row", view.root_view.controls[0])
    heading = cast("ft.Text", header.controls[0])
    return heading.value


def test_url_validation_accepts_expected_endpoints() -> None:
    """Accept the local source and deployed Apps Script endpoint shapes."""
    assert validate_sse_url(" http://localhost:2145/ ") == "http://localhost:2145/"
    assert validate_sse_url("http://127.0.0.1:2145/") == "http://127.0.0.1:2145/"
    assert validate_sse_url("http://[::1]:2145/") == "http://[::1]:2145/"
    assert validate_data_dir(" ~/lcstats-data ") == Path("~/lcstats-data").expanduser()
    gas_url = "https://script.google.com/macros/s/deployment-id/exec"
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
        ("https://script.google.com/macros/s/id/exec?token=secret", "Token"),
    ],
)
def test_gas_url_validation_rejects_unexpected_endpoint(value: str, message: str) -> None:
    """Prevent forwarding archived stats to an unintended host or URL credential."""
    with pytest.raises(ValueError, match=message):
        validate_gas_url(value)


def test_start_validates_inputs_before_creating_manager(tmp_path: Path) -> None:
    """Keep controls editable and show an error when settings are incomplete."""

    async def scenario() -> None:
        page = _FakePage()
        view = MonitorView(
            page,
            settings_store=_settings_store(tmp_path),
            manager_factory=_factory_for(_FakeManager()),
        )

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
        arguments: list[tuple[str, str, str, Path]] = []

        def factory(
            sse_url: str,
            gas_url: str,
            gas_token: str,
            data_dir: Path,
            _on_state: Callable[[ConnectionState], None],
            _on_payload: Callable[[JSONValue], None],
        ) -> _FakeManager:
            arguments.append((sse_url, gas_url, gas_token, data_dir))
            manager = _FakeManager()
            managers.append(manager)
            return manager

        view = MonitorView(page, settings_store=_settings_store(tmp_path), manager_factory=factory)
        view.save_settings(DEFAULT_TRACKER_URL, str(tmp_path))
        view.save_gas_auth("https://script.google.com/macros/s/id/exec", "secret")
        updates_before_start = page.update_count

        await view.start()
        await view.start()

        expected_arguments = (
            "http://127.0.0.1:2145/",
            "https://script.google.com/macros/s/id/exec",
            "secret",
            tmp_path,
        )
        assert arguments == [
            expected_arguments,
            expected_arguments,
        ]
        assert managers[0].start_count == 1
        assert managers[0].stop_count == 1
        assert managers[1].start_count == 1
        assert view.start_button.disabled is True
        assert view.stop_button.disabled is False
        assert view.settings_button.disabled is True
        assert view.gas_auth_button.disabled is True
        assert page.update_count == updates_before_start + 2

        await view.stop()
        await view.stop()

        assert managers[1].stop_count == 1
        assert view.start_button.disabled is False
        assert view.stop_button.disabled is True
        assert view.settings_button.disabled is False
        assert view.gas_auth_button.disabled is False

    asyncio.run(scenario())


def test_close_stops_active_manager(tmp_path: Path) -> None:
    """Stop background work without issuing a page update during window shutdown."""

    async def scenario() -> None:
        page = _FakePage()
        manager = _FakeManager()
        view = MonitorView(
            page,
            settings_store=_settings_store(tmp_path),
            manager_factory=_factory_for(manager),
        )
        view.save_gas_auth("https://script.google.com/macros/s/id/exec", "")
        await view.start()
        updates_before_close = page.update_count

        await view.close()
        await view.close()

        assert manager.stop_count == 1
        assert page.update_count == updates_before_close

    asyncio.run(scenario())


def test_build_and_state_update_render_monitor(tmp_path: Path) -> None:
    """Build the page and format receiver plus output state fields."""
    page = _FakePage()
    view = MonitorView(
        page,
        settings_store=_settings_store(tmp_path),
        manager_factory=_factory_for(_FakeManager()),
    )

    control = view.build()
    state = ConnectionState(
        status=RelayStatus.DISPATCHING,
        running=True,
        receive_count=4,
        last_received_at=datetime(2026, 6, 20, 9, 15, 33),
        last_error="受信エラー: HTTP 503",
        outputs={
            "archive": OutputState(
                key="archive",
                label="ローカル保存",
                status=OutputStatus.SUCCESS,
                success_count=3,
                message="保存しました",
                last_success_at=datetime(2026, 6, 20, 9, 15, 34),
            ),
            "gas": OutputState(
                key="gas",
                label="Google Sheets",
                status=OutputStatus.RETRY_QUEUED,
                failure_count=2,
                pending_count=1,
                message="GAS送信に失敗しました",
            ),
        },
    )
    view.update_state(state)

    assert isinstance(control, ft.Container)
    assert view.status.value == "出力処理中"
    assert view.receive_count.value == "4"
    assert view.last_received.value == "2026-06-20 09:15:33"
    assert view.error.value == "受信エラー: HTTP 503"
    assert view.health.value == "要確認"
    assert view.health_detail.value == "受信エラー: HTTP 503"
    assert view.root_container.bgcolor == ft.Colors.RED_50
    assert len(view.output_alerts.controls) == 1

    first = view.output_alerts.controls[0]
    assert isinstance(first, ft.Container)

    view.update_state(ConnectionState())
    assert view.last_received.value == "-"
    assert view.error.value == ""
    assert view.health.value == "停止中"
    assert view.root_container.bgcolor == ft.Colors.RED_50
    assert len(view.output_alerts.controls) == 1


def test_monitor_health_focuses_on_normal_and_output_alerts(tmp_path: Path) -> None:
    """Summarize normal operation and surface only abnormal outputs."""
    page = _FakePage()
    view = MonitorView(
        page,
        settings_store=_settings_store(tmp_path),
        manager_factory=_factory_for(_FakeManager()),
    )
    view.build()

    view.update_state(ConnectionState(status=RelayStatus.WAITING, running=True))

    assert view.health.value == "異常なし"
    assert view.health_detail.value == "受信と出力を監視中です"
    assert view.root_container.bgcolor == ft.Colors.GREEN_50
    assert len(view.output_alerts.controls) == 1

    view.update_state(
        ConnectionState(
            status=RelayStatus.DISPATCHING,
            running=True,
            outputs={
                "archive": OutputState(
                    key="archive",
                    label="ローカル保存",
                    status=OutputStatus.SUCCESS,
                    success_count=1,
                    message="保存しました",
                ),
                "gas": OutputState(
                    key="gas",
                    label="Google Sheets",
                    status=OutputStatus.ERROR,
                    failure_count=1,
                    message="GAS送信に失敗しました",
                ),
            },
        ),
    )

    assert view.health.value == "要確認"
    assert view.health_detail.value == "出力に失敗または再送待ちがあります"
    assert view.root_container.bgcolor == ft.Colors.RED_50
    assert len(view.output_alerts.controls) == 1


def test_payload_callback_does_not_render_raw_payloads(tmp_path: Path) -> None:
    """Avoid raw payload logs on the abnormality-focused monitor."""
    page = _FakePage()
    view = MonitorView(
        page,
        settings_store=_settings_store(tmp_path),
        manager_factory=_factory_for(_FakeManager()),
    )

    for seed in range(_PAYLOAD_CALLS):
        view.add_payload({"Seed": seed})

    assert page.update_count == 0


def test_settings_modal_links_to_gas_auth_modal(tmp_path: Path) -> None:
    """Open GAS auth as an output setting from the settings modal."""
    page = _FakePage()
    store = _settings_store(tmp_path)
    view = MonitorView(page, settings_store=store, manager_factory=_factory_for(_FakeManager()))
    view.build()

    view.open_settings()
    assert page.dialogs[-1].open is True
    settings_dialog = page.dialogs[-1]
    settings_title = cast("ft.Row", settings_dialog.title)
    assert cast("ft.Text", settings_title.controls[0]).value == "設定"
    view.tracker_url_field.value = "http://localhost:2145/"
    view.data_dir_field.value = str(tmp_path / "archive-root")

    settings_content = cast("ft.Column", settings_dialog.content)
    output_row = cast("ft.Row", settings_content.controls[4])
    gas_button = cast("Any", output_row.controls[1])
    gas_button.on_click(None)

    assert settings_dialog.open is False
    gas_dialog = page.dialogs[-1]
    gas_title = cast("ft.Row", gas_dialog.title)
    assert cast("ft.Text", gas_title.controls[0]).value == "GAS認証"
    view.gas_url_field.value = "https://script.google.com/macros/s/id/exec"
    view.gas_token_field.value = "secret"
    view._save_gas_auth_from_modal()

    view.open_settings()
    view.tracker_url_field.value = "http://localhost:2145/"
    view.data_dir_field.value = str(tmp_path / "archive-root")
    view._save_settings_from_modal()

    settings = store.load()
    assert settings.tracker_url == "http://localhost:2145/"
    assert settings.gas_url == "https://script.google.com/macros/s/id/exec"
    assert settings.data_dir == tmp_path / "archive-root"
    assert view.gas_summary.value.split(" / ")[1] == "Token: 設定済み"
    assert "secret" not in store.path.read_text(encoding="utf-8")


def test_modal_save_errors_keep_modal_open(tmp_path: Path) -> None:
    """Report validation errors without closing the active modal."""
    page = _FakePage()
    view = MonitorView(
        page,
        settings_store=_settings_store(tmp_path),
        manager_factory=_factory_for(_FakeManager()),
    )
    view.build()

    view.open_settings()
    view.data_dir_field.value = ""
    settings_dialog = page.dialogs[-1]
    view._save_settings_from_modal()
    assert settings_dialog.open is True
    assert view.error.value == "ローカル保存先ディレクトリを指定してください"

    view.open_gas_auth()
    gas_dialog = page.dialogs[-1]
    view._save_gas_auth_from_modal()
    assert gas_dialog.open is True
    assert view.error.value == "GAS URLにはscript.google.comのHTTPS URLを指定してください"

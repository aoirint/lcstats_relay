"""Tests for monitor control state and async actions."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import flet as ft
import pytest

from lcstats_relay.application.state import ConnectionState, OutputState, OutputStatus, RelayStatus
from lcstats_relay.domain.payload import JSONValue
from lcstats_relay.infrastructure.config import DEFAULT_TRACKER_URL, RelaySettings, SettingsStore
from lcstats_relay.ui.monitor import (
    ManagerFactory,
    MonitorView,
    validate_data_dir,
    validate_gas_url,
    validate_sse_url,
)

_PAYLOAD_CALLS = 101
_OUTPUT_DESTINATION_COUNT = 2


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


def _factory_for(
    manager: _FakeManager,
) -> ManagerFactory:
    def create(  # noqa: PLR0913 - fake mirrors the complete composition protocol.
        *,
        sse_url: str,
        gas_url: str,
        gas_token: str,
        data_dir: Path,
        on_state: Callable[[ConnectionState], None],
        on_payload: Callable[[JSONValue], None],
    ) -> _FakeManager:
        del sse_url, gas_url, gas_token, data_dir, on_state, on_payload
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


def test_start_allows_connection_without_gas_destination(tmp_path: Path) -> None:
    """Allow local archive-only connections when GAS is not configured."""

    async def scenario() -> None:
        page = _FakePage()
        manager = _FakeManager()
        view = MonitorView(
            page,
            settings_store=_settings_store(tmp_path),
            manager_factory=_factory_for(manager),
        )

        await view.start()

        assert view.error.value == ""
        assert bool(view.start_button.disabled)
        assert manager.start_count == 1
        assert page.update_count == 1

    asyncio.run(scenario())


def test_start_rejects_invalid_configured_gas_destination(tmp_path: Path) -> None:
    """Validate a configured GAS destination before creating the manager."""

    async def scenario() -> None:
        page = _FakePage()
        store = _settings_store(tmp_path)
        store.save(
            RelaySettings(
                tracker_url=DEFAULT_TRACKER_URL,
                gas_url="https://example.com/macros/s/id/exec",
                data_dir=tmp_path,
            ),
        )
        view = MonitorView(
            page,
            settings_store=store,
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

        def factory(  # noqa: PLR0913 - captures every composition argument for assertion.
            *,
            sse_url: str,
            gas_url: str,
            gas_token: str,
            data_dir: Path,
            on_state: Callable[[ConnectionState], None],
            on_payload: Callable[[JSONValue], None],
        ) -> _FakeManager:
            del on_state, on_payload
            arguments.append((sse_url, gas_url, gas_token, data_dir))
            manager = _FakeManager()
            managers.append(manager)
            return manager

        view = MonitorView(page, settings_store=_settings_store(tmp_path), manager_factory=factory)
        view.save_settings(DEFAULT_TRACKER_URL, data_dir=str(tmp_path))
        view.save_gas_auth(
            "https://script.google.com/macros/s/id/exec",
            gas_token="secret",  # noqa: S106 - inert test fixture, not a credential.
        )
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
        assert not bool(view.stop_button.disabled)
        assert bool(view.settings_button.disabled)
        assert bool(view.gas_auth_button.disabled)
        assert page.update_count == updates_before_start + 2

        await view.stop()
        await view.stop()

        assert managers[1].stop_count == 1
        assert not bool(view.start_button.disabled)
        assert bool(view.stop_button.disabled)
        assert not bool(view.settings_button.disabled)
        assert not bool(view.gas_auth_button.disabled)

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
        view.save_gas_auth("https://script.google.com/macros/s/id/exec", gas_token="")
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
        last_received_at=datetime(2026, 6, 20, 9, 15, 33, tzinfo=UTC),
        last_error="受信エラー: HTTP 503",
        outputs={
            "archive": OutputState(
                key="archive",
                label="ローカル保存",
                status=OutputStatus.SUCCESS,
                success_count=3,
                message="保存しました",
                last_success_at=datetime(2026, 6, 20, 9, 15, 34, tzinfo=UTC),
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
    monitor_row = cast("ft.Row", view.root_view.controls[4])
    output_panel = cast("ft.Container", monitor_row.controls[1])
    assert output_panel.border is None
    assert view.status.value == "出力処理中"
    assert view.receive_count.value == "4"
    assert view.last_received.value == "2026-06-20 09:15:33"
    assert view.error.value == "受信エラー: HTTP 503"
    assert view.health.value == "要確認"
    assert view.health_detail.value == "受信エラー: HTTP 503"
    assert view.health_icon.icon == ft.Icons.ERROR_OUTLINE
    assert len(view.output_destinations.controls) == _OUTPUT_DESTINATION_COUNT

    first = view.output_destinations.controls[0]
    assert isinstance(first, ft.Container)

    view.update_state(ConnectionState())
    assert view.last_received.value == "-"
    assert view.error.value == ""
    assert view.health.value == "停止中"
    assert view.health_icon.icon == ft.Icons.ERROR_OUTLINE
    assert len(view.output_destinations.controls) == 1

    disconnected_item = cast("ft.Container", view.output_destinations.controls[0])
    disconnected_row = cast("ft.Row", cast("ft.Column", disconnected_item.content).controls[0])
    disconnected_icon = cast("ft.Icon", disconnected_row.controls[0])
    disconnected_status = cast("ft.Text", disconnected_row.controls[2])
    assert disconnected_icon.icon == ft.Icons.LINK_OFF
    assert disconnected_status.value == "未接続"


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

    assert view.health.value == "接続試行中"
    assert view.health.color == ft.Colors.ORANGE_800
    assert view.health_detail.value == "待機中"
    assert view.health_icon.icon == ft.Icons.SYNC
    assert view.health_icon.color == ft.Colors.ORANGE_800
    assert len(view.output_destinations.controls) == 1

    view.update_state(
        ConnectionState(
            status=RelayStatus.ERROR,
            running=True,
            last_error="受信エラー: ConnectError",
            retry_after_seconds=3.0,
        ),
    )

    assert view.health.value == "接続失敗"
    assert view.health_detail.value == "3秒後に再試行"
    assert view.health_icon.icon == ft.Icons.WARNING_AMBER

    view.update_state(
        ConnectionState(status=RelayStatus.WAITING, running=True, receive_count=1),
    )

    assert view.health.value == "異常なし"
    assert view.health_detail.value == "監視中"
    assert view.health_icon.icon == ft.Icons.CHECK_CIRCLE
    assert len(view.output_destinations.controls) == 1

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
    assert view.health_detail.value == "出力先を確認"
    assert view.health_icon.icon == ft.Icons.WARNING_AMBER
    assert len(view.output_destinations.controls) == _OUTPUT_DESTINATION_COUNT


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


def test_output_destination_icons_reflect_each_output_state(tmp_path: Path) -> None:
    """Show a compact status icon for each configured destination."""
    page = _FakePage()
    view = MonitorView(
        page,
        settings_store=_settings_store(tmp_path),
        manager_factory=_factory_for(_FakeManager()),
    )
    view.build()

    view.update_state(
        ConnectionState(
            running=True,
            outputs={
                "idle": OutputState(key="idle", label="待機", status=OutputStatus.IDLE),
                "running": OutputState(
                    key="running",
                    label="処理",
                    status=OutputStatus.RUNNING,
                ),
                "queued": OutputState(
                    key="queued",
                    label="再送",
                    status=OutputStatus.SUCCESS,
                    pending_count=1,
                ),
            },
        ),
    )

    icons = [
        cast("ft.Icon", cast("ft.Row", cast("ft.Column", item.content).controls[0]).controls[0])
        for item in cast("list[ft.Container]", view.output_destinations.controls)
    ]

    assert [icon.icon for icon in icons] == [
        ft.Icons.RADIO_BUTTON_UNCHECKED,
        ft.Icons.SYNC,
        ft.Icons.WARNING_AMBER,
    ]


def test_settings_view_links_to_full_window_gas_auth_view(tmp_path: Path) -> None:
    """Open GAS auth as an output setting without using modal backdrops."""
    page = _FakePage()
    store = _settings_store(tmp_path)
    view = MonitorView(page, settings_store=store, manager_factory=_factory_for(_FakeManager()))
    view.build()

    view.open_settings()
    assert _active_heading(view) == "設定"
    view.tracker_url_field.value = "http://localhost:2145/"
    view.data_dir_field.value = str(tmp_path / "archive-root")

    settings_body = cast("ft.Column", view.root_view.controls[1])
    output_section = cast("ft.Column", settings_body.controls[2])
    output_row_container = cast("ft.Container", output_section.controls[2])
    output_row = cast("ft.Row", output_row_container.content)
    gas_button = cast("Any", output_row.controls[1])
    gas_button.on_click(None)

    assert _active_heading(view) == "GAS認証"
    view.gas_url_field.value = "https://script.google.com/macros/s/id/exec"
    view.gas_token_field.value = "secret"
    view.submit_gas_auth()
    assert _active_heading(view) == "設定"

    view.tracker_url_field.value = "http://localhost:2145/"
    view.data_dir_field.value = str(tmp_path / "archive-root")
    view.submit_settings()
    assert _active_heading(view) == "LCStats Relay Monitor"

    settings = store.load()
    assert settings.tracker_url == "http://localhost:2145/"
    assert settings.gas_url == "https://script.google.com/macros/s/id/exec"
    assert settings.data_dir == tmp_path / "archive-root"
    assert view.gas_summary.value.split(" / ")[1] == "Token: 設定済み"
    assert "secret" not in store.path.read_text(encoding="utf-8")


def test_full_window_view_save_errors_keep_active_view(tmp_path: Path) -> None:
    """Report validation errors without leaving the active settings view."""
    page = _FakePage()
    view = MonitorView(
        page,
        settings_store=_settings_store(tmp_path),
        manager_factory=_factory_for(_FakeManager()),
    )
    view.build()

    view.open_settings()
    view.data_dir_field.value = ""
    view.submit_settings()
    assert _active_heading(view) == "設定"
    assert view.error.value == "ローカル保存先ディレクトリを指定してください"

    view.open_gas_auth()
    view.submit_gas_auth()
    assert _active_heading(view) == "設定"
    assert view.error.value == ""

    view.open_gas_auth()
    view.gas_url_field.value = "https://example.com/macros/s/id/exec"
    view.submit_gas_auth()
    assert _active_heading(view) == "GAS認証"
    assert view.error.value == "GAS URLにはscript.google.comのHTTPS URLを指定してください"

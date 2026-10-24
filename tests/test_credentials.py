"""Credential persistence, destination isolation, failures, and native bridge contracts."""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, Mock

import flet as ft
import pytest
from credential_fakes import MemoryTokens
from flet_secure_storage import SecureStorage

from lcstats_relay.application.credentials import CredentialStoreError
from lcstats_relay.application.settings import RelaySettings
from lcstats_relay.infrastructure.config import SettingsStore
from lcstats_relay.presentation.controller import MonitorController
from lcstats_relay.ui.credentials import FletTokenStore
from lcstats_relay.ui.monitor import MonitorView

_URL = "https://script.google.com/macros/s/test-only/exec"
_OTHER_URL = "https://script.google.com/macros/s/other-test-only/exec"
_TOKEN = "inert-credential-test-value"  # noqa: S105 - offline fixture, not a credential.


def _controller(*, settings: SettingsStore, tokens: MemoryTokens) -> MonitorController:
    manager = Mock()
    manager.stop = AsyncMock()
    return MonitorController(
        settings_gateway=settings, token_store=tokens, manager_factory=Mock(return_value=manager)
    )


def test_token_survives_controller_restart_and_can_be_forgotten(*, tmp_path: Path) -> None:
    """Keep the secret out of settings/UI, restore it, reuse it, and explicitly delete it."""

    async def scenario() -> None:
        settings = SettingsStore(path=tmp_path / "settings.json")
        tokens = MemoryTokens()
        first = _controller(settings=settings, tokens=tokens)
        assert await first.save_gas_auth(gas_url=_URL, gas_token=_TOKEN)
        second = _controller(settings=settings, tokens=tokens)
        await second.restore_gas_token()
        assert second.gas_token_configured
        view = MonitorView(page=Mock(), controller=second)
        view.build()
        view.open_gas_auth()
        assert view.gas_token_field.value == ""
        assert view.gas_token_field.hint_text == "••••••••"
        assert bool(view.gas_token_field.can_reveal_password) is False
        await view.submit_gas_auth()
        assert tokens.values[_URL] == _TOKEN
        view.open_gas_auth()
        view.gas_token_field.value = "replacement-fixture-value"
        cast("Callable[[object | None], None]", view.gas_token_field.on_change)(None)
        assert bool(view.gas_token_field.can_reveal_password)
        await view.submit_gas_auth()
        assert tokens.values[_URL] == "replacement-fixture-value"
        view.open_gas_auth()
        assert second.gas_token_configured
        view.gas_url_field.value = _OTHER_URL
        cast("Callable[[object | None], None]", view.gas_url_field.on_change)(None)
        assert view.gas_delete_button.disabled
        assert view.gas_token_field.hint_text == ""
        view.open_gas_auth()
        await view.delete_gas_token()
        assert bool(second.gas_token_configured) is False
        assert view.gas_delete_button.disabled
        third = _controller(settings=settings, tokens=tokens)
        await third.restore_gas_token()
        assert bool(third.gas_token_configured) is False
        assert settings.load().gas_url == _URL
        assert _TOKEN not in settings.path.read_text(encoding="utf-8")

    asyncio.run(scenario())


def test_destination_change_never_reuses_another_destinations_token(*, tmp_path: Path) -> None:
    """A blank token reads only the newly selected destination's OS entry."""

    async def scenario() -> None:
        settings = SettingsStore(path=tmp_path / "settings.json")
        tokens = MemoryTokens()
        controller = _controller(settings=settings, tokens=tokens)
        assert await controller.save_gas_auth(gas_url=_URL, gas_token=_TOKEN)
        assert await controller.save_gas_auth(gas_url=_OTHER_URL, gas_token="")
        assert bool(controller.gas_token_configured) is False
        assert tokens.values == {_URL: _TOKEN}
        assert await controller.save_gas_auth(gas_url=_URL, gas_token="")
        assert controller.gas_token_configured
        assert await controller.save_gas_auth(gas_url="", gas_token="")
        assert bool(controller.gas_token_configured) is False
        assert not await controller.delete_gas_token()

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["load", "save", "delete"])
def test_store_failure_is_visible_without_disclosing_backend_details(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    operation: str,
) -> None:
    """OS failures preserve accepted credentials and expose only fixed diagnostic metadata."""

    async def scenario() -> None:
        settings = SettingsStore(path=tmp_path / "settings.json")
        tokens = MemoryTokens()
        controller = _controller(settings=settings, tokens=tokens)
        assert await controller.save_gas_auth(gas_url=_URL, gas_token=_TOKEN)
        monkeypatch.setattr(tokens, operation, AsyncMock(side_effect=CredentialStoreError(_TOKEN)))
        if operation == "load":
            controller = _controller(settings=settings, tokens=tokens)
            await controller.restore_gas_token()
            assert bool(controller.gas_token_configured) is False
        elif operation == "save":
            assert not await controller.save_gas_auth(gas_url=_OTHER_URL, gas_token=_TOKEN)
            assert controller.gas_token_configured
        else:
            view = MonitorView(page=Mock(), controller=controller)
            await view.delete_gas_token()
            assert controller.gas_token_configured
        assert "OSの認証情報ストア" in controller.error
        assert controller.settings.gas_url == _URL
        assert bool(controller.credentials_busy) is False
        assert _TOKEN not in controller.error + caplog.text + settings.path.read_text(
            encoding="utf-8"
        )
        assert f"credential_{operation}_failed" in caplog.text

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["save", "delete"])
def test_pending_credentials_block_edits_and_do_not_update_a_closed_page(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    """A slow OS operation cannot overlap another edit or render after window close."""

    async def scenario() -> None:
        settings = SettingsStore(path=tmp_path / "settings.json")
        tokens = MemoryTokens()
        controller = _controller(settings=settings, tokens=tokens)
        assert await controller.save_gas_auth(gas_url=_URL, gas_token=_TOKEN)
        page = Mock()
        view = MonitorView(page=page, controller=controller)
        view.build()
        view.open_gas_auth()
        release = asyncio.Event()

        async def delayed(**arguments: str) -> None:
            del arguments
            await release.wait()

        monkeypatch.setattr(tokens, operation, delayed)
        view.gas_token_field.value = _TOKEN
        pending = asyncio.create_task(
            view.submit_gas_auth() if operation == "save" else view.delete_gas_token()
        )
        await asyncio.sleep(0)
        assert controller.credentials_busy
        assert view.start_button.disabled
        assert view.gas_save_button.disabled
        close_button = next(
            control
            for row in view.root_view.controls
            if isinstance(row, ft.Row)
            for control in row.controls
            if isinstance(control, ft.IconButton) and control.tooltip == "閉じる"
        )
        cast("Callable[[object | None], None]", close_button.on_click)(None)
        assert not await controller.save_gas_auth(gas_url=_OTHER_URL, gas_token="")
        assert not await controller.delete_gas_token()
        assert not await controller.start()
        assert not controller.save_settings(
            tracker_url="http://127.0.0.1:2145/", data_dir=str(tmp_path)
        )
        await view.close()
        updates = page.update.call_count
        release.set()
        await pending
        assert page.update.call_count == updates
        assert bool(controller.credentials_busy) is False
        assert view.gas_token_field.value == ""

    asyncio.run(scenario())


def test_active_session_does_not_change_its_credentials(*, tmp_path: Path) -> None:
    """Credential edits stay locked for the lifetime of an active connection."""

    async def scenario() -> None:
        tokens = MemoryTokens()
        controller = _controller(
            settings=SettingsStore(path=tmp_path / "settings.json"), tokens=tokens
        )
        assert await controller.start()
        assert not controller.save_settings(
            tracker_url="http://127.0.0.1:2145/", data_dir=str(tmp_path)
        )
        assert not await controller.save_gas_auth(gas_url=_URL, gas_token=_TOKEN)
        assert not await controller.delete_gas_token()
        await controller.close()
        assert tokens.values == {}

    asyncio.run(scenario())


def test_invalid_saved_destination_is_not_looked_up(*, tmp_path: Path) -> None:
    """Do not contact the credential store for malformed manually edited configuration."""
    settings = SettingsStore(path=tmp_path / "settings.json")
    settings.save(settings=RelaySettings(gas_url="https://example.invalid/"))
    controller = _controller(settings=settings, tokens=MemoryTokens())
    asyncio.run(controller.restore_gas_token())
    assert "GAS URL" in controller.error


def test_flet_adapter_scopes_credentials_and_supports_read_write_delete() -> None:
    """Credential names hide URLs, separate destinations, and delete only the selected entry."""

    async def scenario() -> None:
        values: dict[str, str] = {}
        service = Mock(spec=SecureStorage)
        service.get = AsyncMock(side_effect=lambda **args: values.get(args["key"]))
        service.set = AsyncMock(
            side_effect=lambda **args: values.update({args["key"]: args["value"]})
        )
        service.remove = AsyncMock(side_effect=lambda **args: values.pop(args["key"], None))
        adapter = FletTokenStore(storage=cast("SecureStorage", service), native=True)
        await adapter.save(gas_url=_URL, token=_TOKEN)
        assert await adapter.load(gas_url=_URL) == _TOKEN
        assert await adapter.load(gas_url=_OTHER_URL) is None
        assert all(key.startswith("lcstats-relay.gas.") and _URL not in key for key in values)
        await adapter.delete(gas_url=_URL)
        assert values == {}
        assert await adapter.load(gas_url=_URL) is None

    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["load", "save", "delete"])
@pytest.mark.parametrize("error_type", [RuntimeError, TimeoutError])
def test_flet_rpc_failure_is_translated_without_private_error_text(
    *, operation: str, error_type: type[Exception]
) -> None:
    """Translate only the SDK's documented invocation errors at the RPC boundary."""

    async def scenario() -> None:
        service = Mock(spec=SecureStorage)
        method = {"load": "get", "save": "set", "delete": "remove"}[operation]
        setattr(service, method, AsyncMock(side_effect=error_type(_TOKEN)))
        adapter = FletTokenStore(storage=cast("SecureStorage", service), native=True)
        pending = (
            adapter.save(gas_url=_URL, token=_TOKEN)
            if operation == "save"
            else getattr(adapter, operation)(gas_url=_URL)
        )
        with pytest.raises(CredentialStoreError) as raised:
            await pending
        assert _TOKEN not in str(raised.value)

    asyncio.run(scenario())


def test_browser_storage_is_not_an_os_keychain() -> None:
    """A browser session must not silently persist credentials in localStorage."""
    service = Mock(spec=SecureStorage)
    adapter = FletTokenStore(storage=cast("SecureStorage", service), native=False)
    with pytest.raises(CredentialStoreError):
        asyncio.run(adapter.load(gas_url=_URL))
    service.get.assert_not_called()

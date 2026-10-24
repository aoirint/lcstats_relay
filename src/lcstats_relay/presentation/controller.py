"""Flet-free monitor workflow and lifecycle ownership."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from lcstats_relay.application.credentials import CredentialStoreError, GasTokenStore
from lcstats_relay.application.diagnostics import emit
from lcstats_relay.application.relay import PayloadCallback
from lcstats_relay.application.settings import RelaySettings
from lcstats_relay.application.state import ConnectionState, StateCallback
from lcstats_relay.domain.payload import JSONValue
from lcstats_relay.presentation.validation import (
    validate_data_dir,
    validate_gas_url,
    validate_sse_url,
)


class SettingsGateway(Protocol):
    """Load and persist non-secret relay settings."""

    def load(self) -> RelaySettings:
        """Load the current settings snapshot."""

    def save(self, *, settings: RelaySettings) -> None:
        """Persist one validated settings snapshot."""


class ManagerPort(Protocol):
    """Connection manager lifecycle used by the controller."""

    def start(self) -> None:
        """Start receiving payloads."""

    async def stop(self) -> None:
        """Stop receiving payloads and await cleanup."""


class ManagerFactory(Protocol):
    """Create one connection manager from validated settings."""

    def __call__(  # noqa: PLR0913 - composition receives one complete session.
        self,
        *,
        sse_url: str,
        gas_url: str,
        gas_token: str,
        data_dir: Path,
        on_state: StateCallback,
        on_payload: PayloadCallback,
    ) -> ManagerPort:
        """Build one manager for a connection session."""


type ChangeCallback = Callable[[], None]


class MonitorController:
    """Own settings, manager replacement, and observable monitor state."""

    def __init__(
        self,
        *,
        settings_gateway: SettingsGateway,
        token_store: GasTokenStore,
        manager_factory: ManagerFactory,
    ) -> None:
        """Load settings and retain injected application boundaries."""
        self._token_store = token_store
        self._credentials_busy = False
        self._closed = False
        self._settings_gateway = settings_gateway
        self._manager_factory = manager_factory
        self._settings = settings_gateway.load()
        self._manager: ManagerPort | None = None
        self._gas_token = ""
        self._form_error = ""
        self._relay_state = ConnectionState()
        self._on_change: ChangeCallback = lambda: None
        self._on_payload: PayloadCallback = lambda *, payload: None  # noqa: ARG005 - no-op default callback.

    @property
    def settings(self) -> RelaySettings:
        """Return the accepted non-secret settings snapshot."""
        return self._settings

    @property
    def relay_state(self) -> ConnectionState:
        """Return the latest application state snapshot."""
        return self._relay_state

    @property
    def error(self) -> str:
        """Return the active validation or relay error."""
        return self._form_error or self._relay_state.last_error or ""

    @property
    def gas_token_configured(self) -> bool:
        """Report token presence without exposing its contents."""
        return bool(self._gas_token)

    @property
    def active(self) -> bool:
        """Report whether this controller owns a manager session."""
        return self._manager is not None

    def bind(self, *, on_change: ChangeCallback, on_payload: PayloadCallback) -> None:
        """Attach presentation observers after the UI adapter is constructed."""
        self._on_change = on_change
        self._on_payload = on_payload

    def save_settings(self, *, tracker_url: str, data_dir: str) -> bool:
        """Validate and persist tracker plus local storage settings."""
        if self._credentials_busy or self.active:
            return False
        try:
            settings = RelaySettings(
                tracker_url=validate_sse_url(value=tracker_url),
                gas_url=self._settings.gas_url,
                data_dir=validate_data_dir(value=data_dir),
            )
        except ValueError as exc:
            self._form_error = str(exc)
            self._notify()
            return False
        self._settings_gateway.save(settings=settings)
        self._settings = settings
        self._form_error = ""
        self._notify()
        return True

    @property
    def credentials_busy(self) -> bool:
        """Report an outstanding OS operation so edits cannot overlap."""
        return self._credentials_busy

    async def restore_gas_token(self) -> None:
        """Restore before the editable view is mounted; settings contain no secret."""
        if not self._settings.gas_url:
            return
        try:
            url = validate_gas_url(value=self._settings.gas_url)
            self._gas_token = await self._token_store.load(gas_url=url) or ""
        except ValueError as exc:
            self._form_error = str(exc)
        except CredentialStoreError:
            self._credential_failure(operation="load")

    async def save_gas_auth(self, *, gas_url: str, gas_token: str) -> bool:
        """Save the secret first, then accept its non-secret destination."""
        if self._credentials_busy or self.active:
            return False
        try:
            normalized_url = validate_gas_url(value=gas_url) if gas_url.strip() else ""
        except ValueError as exc:
            self._form_error = str(exc)
            self._notify()
            return False
        self._credentials_busy = True
        self._notify()
        try:
            token = gas_token.strip() if normalized_url else ""
            if normalized_url:
                if token:
                    await self._token_store.save(gas_url=normalized_url, token=token)
                else:
                    token = await self._token_store.load(gas_url=normalized_url) or ""
            settings = RelaySettings(
                tracker_url=self._settings.tracker_url,
                gas_url=normalized_url,
                data_dir=self._settings.data_dir,
            )
            await asyncio.to_thread(self._settings_gateway.save, settings=settings)
            self._settings = settings
            self._gas_token = token
            self._form_error = ""
        except CredentialStoreError:
            self._credential_failure(operation="save")
            return False
        else:
            return True
        finally:
            self._credentials_busy = False
            self._notify()

    async def delete_gas_token(self) -> bool:
        """Forget the accepted destination's credential, including its memory copy."""
        if self._credentials_busy or self.active or not self._settings.gas_url:
            return False
        self._credentials_busy = True
        self._notify()
        try:
            await self._token_store.delete(gas_url=self._settings.gas_url)
            self._gas_token = ""
            self._form_error = ""
        except CredentialStoreError:
            self._credential_failure(operation="delete")
            return False
        else:
            return True
        finally:
            self._credentials_busy = False
            self._notify()

    def _credential_failure(self, *, operation: str) -> None:
        self._form_error = "OSの認証情報ストアを利用できません。設定から再試行してください"
        emit(event=f"credential_{operation}_failed", category="credential_store", failed=True)

    async def start(self) -> bool:
        """Validate settings and replace the owned manager session."""
        if self._credentials_busy:
            return False
        try:
            tracker_url = validate_sse_url(value=self._settings.tracker_url)
            gas_url = (
                validate_gas_url(value=self._settings.gas_url)
                if self._settings.gas_url.strip()
                else ""
            )
            data_dir = validate_data_dir(value=str(self._settings.data_dir))
        except ValueError as exc:
            self._form_error = str(exc)
            self._notify()
            return False

        if self._manager is not None:
            await self._manager.stop()
        self._manager = self._manager_factory(
            sse_url=tracker_url,
            gas_url=gas_url,
            gas_token=self._gas_token,
            data_dir=data_dir,
            on_state=self._receive_state,
            on_payload=self._receive_payload,
        )
        self._form_error = ""
        previous_state = self._relay_state
        self._manager.start()
        if self._relay_state is previous_state:
            self._notify()
        return True

    async def stop(self) -> None:
        """Stop and release the active manager, then publish stopped state."""
        if self._manager is not None:
            manager = self._manager
            self._manager = None
            previous_state = self._relay_state
            await manager.stop()
            if self._relay_state is not previous_state:
                return
        self._relay_state = ConnectionState()
        self._notify()

    async def close(self) -> None:
        """Stop background work without notifying an unmounting UI."""
        self._closed = True
        if self._manager is not None:
            await self._manager.stop()
            self._manager = None
        self._relay_state = ConnectionState()

    def _receive_state(self, *, state: ConnectionState) -> None:
        self._relay_state = state
        self._notify()

    def _receive_payload(self, *, payload: JSONValue) -> None:
        self._on_payload(payload=payload)

    def _notify(self) -> None:
        if not self._closed:
            self._on_change()

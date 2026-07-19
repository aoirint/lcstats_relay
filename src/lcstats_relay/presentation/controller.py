"""Flet-free monitor workflow and lifecycle ownership."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from lcstats_relay.application.settings import RelaySettings
from lcstats_relay.application.state import ConnectionState
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

    def save(self, settings: RelaySettings) -> None:
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
        on_state: Callable[[ConnectionState], None],
        on_payload: Callable[[JSONValue], None],
    ) -> ManagerPort:
        """Build one manager for a connection session."""


type ChangeCallback = Callable[[], None]
type PayloadCallback = Callable[[JSONValue], None]


class MonitorController:
    """Own settings, manager replacement, and observable monitor state."""

    def __init__(
        self,
        *,
        settings_gateway: SettingsGateway,
        manager_factory: ManagerFactory,
    ) -> None:
        """Load settings and retain injected application boundaries."""
        self._settings_gateway = settings_gateway
        self._manager_factory = manager_factory
        self._settings = settings_gateway.load()
        self._manager: ManagerPort | None = None
        self._gas_token = ""
        self._form_error = ""
        self._relay_state = ConnectionState()
        self._on_change: ChangeCallback = lambda: None
        self._on_payload: PayloadCallback = lambda _payload: None

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

    def save_settings(self, tracker_url: str, *, data_dir: str) -> bool:
        """Validate and persist tracker plus local storage settings."""
        try:
            settings = RelaySettings(
                tracker_url=validate_sse_url(tracker_url),
                gas_url=self._settings.gas_url,
                data_dir=validate_data_dir(data_dir),
            )
        except ValueError as exc:
            self._form_error = str(exc)
            self._notify()
            return False
        self._settings_gateway.save(settings)
        self._settings = settings
        self._form_error = ""
        self._notify()
        return True

    def save_gas_auth(self, gas_url: str, *, gas_token: str) -> bool:
        """Persist the GAS URL while retaining its token only in memory."""
        try:
            normalized_url = validate_gas_url(gas_url) if gas_url.strip() else ""
        except ValueError as exc:
            self._form_error = str(exc)
            self._notify()
            return False
        settings = RelaySettings(
            tracker_url=self._settings.tracker_url,
            gas_url=normalized_url,
            data_dir=self._settings.data_dir,
        )
        self._settings_gateway.save(settings)
        self._settings = settings
        self._gas_token = gas_token.strip() if normalized_url else ""
        self._form_error = ""
        self._notify()
        return True

    async def start(self) -> bool:
        """Validate settings and replace the owned manager session."""
        try:
            tracker_url = validate_sse_url(self._settings.tracker_url)
            gas_url = (
                validate_gas_url(self._settings.gas_url) if self._settings.gas_url.strip() else ""
            )
            data_dir = validate_data_dir(str(self._settings.data_dir))
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
        if self._manager is not None:
            await self._manager.stop()
            self._manager = None
        self._relay_state = ConnectionState()

    def _receive_state(self, state: ConnectionState) -> None:
        self._relay_state = state
        self._notify()

    def _receive_payload(self, payload: JSONValue) -> None:
        self._on_payload(payload)

    def _notify(self) -> None:
        self._on_change()

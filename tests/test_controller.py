"""Tests for the Flet-free monitor controller."""

import asyncio
from collections.abc import Callable
from pathlib import Path

from lcstats_relay.application.settings import RelaySettings
from lcstats_relay.application.state import ConnectionState, RelayStatus
from lcstats_relay.domain.payload import JSONValue
from lcstats_relay.presentation.controller import MonitorController


class _MemorySettings:
    def __init__(self) -> None:
        self.settings = RelaySettings()

    def load(self) -> RelaySettings:
        return self.settings

    def save(self, settings: RelaySettings) -> None:
        self.settings = settings


class _ObservableManager:
    def __init__(
        self,
        *,
        on_state: Callable[[ConnectionState], None],
        on_payload: Callable[[JSONValue], None],
    ) -> None:
        self._on_state = on_state
        self._on_payload = on_payload
        self.stop_count = 0

    def start(self) -> None:
        self._on_state(ConnectionState(status=RelayStatus.WAITING, running=True))
        self._on_payload({"Seed": 42})

    async def stop(self) -> None:
        self.stop_count += 1
        self._on_state(ConnectionState(status=RelayStatus.STOPPED))


def test_controller_forwards_manager_state_payload_and_cleanup(tmp_path: Path) -> None:
    """Own one observable manager and publish each semantic transition once."""

    async def scenario() -> None:
        settings = _MemorySettings()
        managers: list[_ObservableManager] = []
        changes: list[ConnectionState] = []
        payloads: list[JSONValue] = []

        def manager_factory(  # noqa: PLR0913 - fake mirrors the composition port.
            *,
            sse_url: str,
            gas_url: str,
            gas_token: str,
            data_dir: Path,
            on_state: Callable[[ConnectionState], None],
            on_payload: Callable[[JSONValue], None],
        ) -> _ObservableManager:
            del sse_url, gas_url, gas_token, data_dir
            manager = _ObservableManager(on_state=on_state, on_payload=on_payload)
            managers.append(manager)
            return manager

        controller = MonitorController(
            settings_gateway=settings,
            manager_factory=manager_factory,
        )
        controller.bind(
            on_change=lambda: changes.append(controller.relay_state),
            on_payload=payloads.append,
        )
        assert controller.save_settings(
            "http://localhost:2145/",
            data_dir=str(tmp_path),
        )
        assert await controller.start()

        waiting_state = controller.relay_state
        assert waiting_state.status is RelayStatus.WAITING
        assert payloads == [{"Seed": 42}]

        await controller.stop()

        assert controller.active is False
        stopped_state = controller.relay_state
        assert stopped_state.status is RelayStatus.STOPPED
        assert managers[0].stop_count == 1
        assert [state.status for state in changes[-2:]] == [
            RelayStatus.WAITING,
            RelayStatus.STOPPED,
        ]

    asyncio.run(scenario())

"""Compose the production relay application from concrete adapters."""

from __future__ import annotations

from pathlib import Path

import httpx

from lcstats_relay.application.ports import OutputPolicy, RetrySemantics
from lcstats_relay.application.relay import ConnectionManager, PayloadCallback
from lcstats_relay.application.state import StateCallback
from lcstats_relay.infrastructure.auth import (
    NoAuthentication,
    QueryTokenAuthentication,
    RequestAuthenticator,
)
from lcstats_relay.infrastructure.config import SettingsStore
from lcstats_relay.infrastructure.outputs import ArchiveOutput, GasOutput
from lcstats_relay.infrastructure.runtime import (
    ClientFactory,
    HttpOutputBinding,
    HttpRelayRuntime,
    make_http_client,
)
from lcstats_relay.infrastructure.storage import ArchiveWriter, RetryQueue
from lcstats_relay.presentation.controller import MonitorController


def create_monitor_controller() -> MonitorController:
    """Compose the Flet-free monitor owner with production adapters."""
    return MonitorController(
        settings_gateway=SettingsStore(),
        manager_factory=create_connection_manager,
    )


def create_connection_manager(  # noqa: PLR0913 - UI boundary passes user settings and callbacks.
    *,
    sse_url: str,
    gas_url: str,
    gas_token: str,
    data_dir: Path,
    on_state: StateCallback,
    on_payload: PayloadCallback,
    client_factory: ClientFactory = make_http_client,
) -> ConnectionManager:
    """Create the production manager without leaking output details into the UI."""
    authenticator: RequestAuthenticator = (
        QueryTokenAuthentication(token=gas_token) if gas_token else NoAuthentication()
    )

    archive_policy = OutputPolicy(
        key="archive",
        label="ローカル保存",
        required=True,
    )
    output_policies = [archive_policy]

    def build_archive(*, client: httpx.AsyncClient) -> ArchiveOutput:
        del client
        return ArchiveOutput(writer=ArchiveWriter(data_dir=data_dir))

    output_bindings = [
        HttpOutputBinding(
            policy=archive_policy,
            build=build_archive,
        ),
    ]
    if gas_url:
        gas_policy = OutputPolicy(
            key="gas",
            label="Google Sheets",
            retry_semantics=RetrySemantics.AT_LEAST_ONCE,
        )
        output_policies.append(gas_policy)
        output_bindings.append(
            HttpOutputBinding(
                policy=gas_policy,
                build=lambda *, client: _build_gas_output(
                    gas_url=gas_url,
                    client=client,
                    authenticator=authenticator,
                ),
            ),
        )
    return ConnectionManager(
        output_policies=output_policies,
        runtime_factory=lambda: HttpRelayRuntime(
            sse_url=sse_url,
            outputs=output_bindings,
            client_factory=client_factory,
        ),
        retry_queue=RetryQueue(data_dir=data_dir),
        on_state=on_state,
        on_payload=on_payload,
    )


def _build_gas_output(
    *,
    gas_url: str,
    client: httpx.AsyncClient,
    authenticator: RequestAuthenticator,
) -> GasOutput:
    return GasOutput(url=gas_url, client=client, authenticator=authenticator)

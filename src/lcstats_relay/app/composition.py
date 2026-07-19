"""Application composition for standard relay outputs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx

from lcstats_relay.application.ports import OutputPolicy, RetrySemantics
from lcstats_relay.application.relay import ConnectionManager
from lcstats_relay.application.state import ConnectionState
from lcstats_relay.domain.payload import JSONValue
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
    on_state: Callable[[ConnectionState], None],
    on_payload: Callable[[JSONValue], None],
    client_factory: ClientFactory = make_http_client,
) -> ConnectionManager:
    """Create the production manager without leaking output details into the UI."""
    authenticator: RequestAuthenticator = (
        QueryTokenAuthentication(gas_token) if gas_token else NoAuthentication()
    )

    archive_policy = OutputPolicy(
        key="archive",
        label="ローカル保存",
        required=True,
    )
    output_policies = [archive_policy]
    output_bindings = [
        HttpOutputBinding(
            policy=archive_policy,
            build=lambda _client: ArchiveOutput(ArchiveWriter(data_dir)),
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
                build=lambda client: _build_gas_output(
                    gas_url,
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
        retry_queue=RetryQueue(data_dir),
        on_state=on_state,
        on_payload=on_payload,
    )


def _build_gas_output(
    gas_url: str,
    *,
    client: httpx.AsyncClient,
    authenticator: RequestAuthenticator,
) -> GasOutput:
    return GasOutput(gas_url, client=client, authenticator=authenticator)

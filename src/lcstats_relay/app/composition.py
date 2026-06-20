"""Application composition for standard relay outputs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx

from lcstats_relay.core.auth import NoAuthentication, QueryTokenAuthentication, RequestAuthenticator
from lcstats_relay.core.outputs import ArchiveOutput, GasOutput, OutputRegistration
from lcstats_relay.core.payload import JSONValue
from lcstats_relay.core.relay import ConnectionManager
from lcstats_relay.core.state import ConnectionState
from lcstats_relay.core.storage import ArchiveWriter


def create_connection_manager(  # noqa: PLR0913 - UI boundary passes user settings and callbacks.
    sse_url: str,
    gas_url: str,
    gas_token: str,
    data_dir: Path,
    on_state: Callable[[ConnectionState], None],
    on_payload: Callable[[JSONValue], None],
) -> ConnectionManager:
    """Create the production manager without leaking output details into the UI."""
    authenticator: RequestAuthenticator = (
        QueryTokenAuthentication(gas_token) if gas_token else NoAuthentication()
    )

    outputs = [
        OutputRegistration(
            key="archive",
            label="ローカル保存",
            build=lambda _client: ArchiveOutput(ArchiveWriter(data_dir)),
            required=True,
            queue_failures=False,
        ),
    ]
    if gas_url:
        outputs.append(
            OutputRegistration(
                key="gas",
                label="Google Sheets",
                build=lambda client: _build_gas_output(gas_url, client, authenticator),
                queue_failures=True,
            ),
        )
    return ConnectionManager(
        sse_url=sse_url,
        outputs=outputs,
        data_dir=data_dir,
        on_state=on_state,
        on_payload=on_payload,
    )


def _build_gas_output(
    gas_url: str,
    client: httpx.AsyncClient,
    authenticator: RequestAuthenticator,
) -> GasOutput:
    return GasOutput(gas_url, client, authenticator)

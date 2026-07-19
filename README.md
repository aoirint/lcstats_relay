# LCStats Relay

LCStats Relay is an async Flet desktop app that receives local statistics JSON
from LCStatsTracker, archives the original payload, and optionally forwards the
parsed value to Google Sheets through a Google Apps Script Web App.

The app expects LCStatsTracker to return one statistics payload per HTTP
response. After each payload is processed, LCStats Relay reconnects and waits for
the next one.

## Behavior

LCStats Relay dispatches each received payload to registered output surfaces.
The standard output surfaces are:

- Local archive: stores the received JSON under the configured directory.
- Google Sheets: posts the parsed JSON to a configured Google Apps Script Web App.

The local archive is the required durability boundary. If archiving fails, later
outputs are not attempted for that payload.

The [developer documentation map](docs/README.md) separates external contracts,
application architecture, and maintenance procedures.

## Install and run

No packaged release has been published yet. When a release is available, its
Windows and Linux archives, checksums, manifest, and immutable-release
attestation will appear on the repository's Releases page. Until then, run the
current source with Python 3.14 and [uv](https://docs.astral.sh/uv/):

```powershell
uv sync --locked --all-groups
uv run --locked python -m lcstats_relay
```

## Configure and use

In the app window:

- Open Settings to configure the LCStatsTracker URL, usually
  `http://127.0.0.1:2145/`, and the local save directory.
- Open GAS Auth to configure the deployed
  `https://script.google.com/macros/s/.../exec` URL and the token value if the
  Google Apps Script deployment validates one.
- Start the connection and leave the app running while LCStatsTracker is
  producing statistics. Stop the connection before changing its endpoint or
  data directory.

The default SSE URL uses `127.0.0.1` instead of `localhost` to avoid unnecessary
dual-stack loopback connection delays. Explicitly entered URLs are honored as
entered.

For the detailed loopback policy, see
[Loopback connection policy](docs/domain/loopback-connection-policy.md).

GAS tokens are entered separately from the URL. They are masked in the UI and are
not saved to the settings file. The LCStatsTracker URL, GAS Web App URL, and
local save directory are saved in the user settings file. Restarting the app
clears the GAS token, so enter it again before reconnecting when authentication
is required.

## Data, recovery, and removal

The first successful output for each payload is a local archive. GAS failures
can remain in an at-least-once retry queue, so the receiver must tolerate a
duplicate submission after an uncertain timeout or connection failure.

[Data and recovery](docs/operations/data-and-recovery.md) lists the exact
settings, archive, and queue locations and the recovery procedure for each
failure mode. To remove the app after running from source, stop it, remove the
source checkout or uv environment, and separately remove the documented user
settings/data directories only if their archives and pending deliveries are no
longer needed.

## Troubleshooting

- A receiver error means the configured LCStatsTracker endpoint could not
  provide an accepted payload. Confirm that one tracker instance is running and
  that the configured loopback address matches it.
- A local-save error blocks GAS delivery because the archive is the required
  durability boundary. Check the configured directory, available space, and
  permissions before reconnecting.
- A GAS error does not remove the local archive. Correct the endpoint or token,
  then reconnect; review the duplicate-delivery warning before manually
  replaying queued data.

## Development checks

```powershell
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests scripts
uv run --locked pytest
```

## Agent Skills

Repository-local Agent Skills are managed with
[APM](https://github.com/microsoft/apm). Restore and verify the committed Skill
set with:

```powershell
apm install --frozen
apm audit --ci
```

See [AGENTS.md](AGENTS.md) for maintenance and pull request rules.

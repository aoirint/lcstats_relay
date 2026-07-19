# LCStats Relay

LCStats Relay is an async Flet desktop app that receives local statistics JSON from
LCStatsTracker and forwards it to Google Sheets through a Google Apps Script Web
App.

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

For the LCStatsTracker source contract, see
[LCStatsTracker contract](docs/lcstats-tracker-contract.md).

For the Relay output design, see
[Relay output architecture](docs/relay-output-architecture.md).

## Run

Python 3.14 and [uv](https://docs.astral.sh/uv/) are required.

```powershell
uv sync --locked --all-groups
uv run python -m lcstats_relay
```

In the app window:

- Open Settings to configure the LCStatsTracker URL, usually
  `http://127.0.0.1:2145/`, and the local save directory.
- Open GAS Auth to configure the deployed
  `https://script.google.com/macros/s/.../exec` URL and the token value if the
  Google Apps Script deployment validates one.

The default SSE URL uses `127.0.0.1` instead of `localhost` to avoid unnecessary
dual-stack loopback connection delays. Explicitly entered URLs are honored as
entered.

For the detailed loopback policy, see
[Loopback connection policy](docs/loopback-connection-policy.md).

GAS tokens are entered separately from the URL. They are masked in the UI and are
not saved to the settings file. The LCStatsTracker URL, GAS Web App URL, and
local save directory are saved in the user settings file.

## Development checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
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

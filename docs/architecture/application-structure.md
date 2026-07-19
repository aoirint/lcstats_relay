# Application structure

## Purpose

LCStats Relay is an asynchronous desktop adapter. It receives one JSON payload
per LCStatsTracker SSE response, archives the exact received text, and can send
the parsed value to a Google Apps Script Web App.

## Current module map

The executable entry point is `lcstats_relay.__main__`. The source tree has seven
current responsibility groups:

- `domain/` owns relay payload values and JSON parsing without Flet or concrete
  I/O dependencies.
- `application/` owns settings values, output/retry policies, relay state, and
  connection orchestration through ports.
- `presentation/` owns Flet-free validation, immutable presentation models,
  presenters, settings, and connection lifecycle coordination.
- `ui/` constructs Flet controls, emits intents to the controller, and renders
  presentation state.
- `infrastructure/` implements HTTP, authentication, settings, atomic files,
  archives, and the retry queue.
- `entrypoints/flet_app.py` configures the Flet page and mounts the monitor.
- `composition/application.py` is the production composition root. It selects
  outputs, authentication policy, persistence implementations, and the
  connection manager without requiring the UI to construct those details.

Dependencies point inward from the entry point and composition root through UI
and presentation to application/domain policy. Infrastructure implements
application-facing ports and is selected only by composition. Domain,
application, and presentation modules do not import Flet.

## Runtime flow

1. `entrypoints/flet_app.py` creates `MonitorView` with a production
   `MonitorController`.
2. The user supplies a loopback tracker URL, a data directory, and optionally a
   GAS destination and token.
3. `composition/application.py` builds a required archive output and, when
   configured, a retryable GAS output.
4. `ConnectionManager` opens one runtime-owned `httpx.AsyncClient`, a
   `StatsReceiver`, registered output adapters, and concurrent receive/retry
   loops. Blocking archive and queue operations are offloaded from the event
   loop.
5. Each received payload updates `RelayStateStore`, invokes the payload callback
   for valid JSON, and is dispatched in registration order.
6. Application state snapshots flow through Flet-free presenters to the
   monitor. The UI renders summaries and never displays the raw payload body.

The external receive contract is canonical in
[`../domain/lcstats-tracker-contract.md`](../domain/lcstats-tracker-contract.md).
Output guarantees are canonical in [`relay-output.md`](relay-output.md).

## Extension rules

- Add an output by defining an `OutputSink` and registering it in the
  composition root. Keep output-specific behavior out of the dispatcher and
  UI.
- Keep credentials separate from destination URLs. Authentication is applied
  only while preparing an outgoing request.
- Preserve the local archive as the required first output unless a deliberate
  architecture change updates `relay-output.md` and its tests.
- Extend the fixed `domain/`, `application/`, `presentation/`, `ui/`,
  `infrastructure/`, `entrypoints/`, and `composition/` packages by cohesive
  ownership. Do not collapse policy, presentation, controls, adapters, or
  startup wiring into one view or generic helper module.
- Introduce ports at I/O boundaries when replacing or testing concrete HTTP,
  filesystem, clock, sleep, or UI behavior.

## Known structural limitations

The current layout still has bounded limitations:

- `ConnectionManager` owns the session task but does not expose an unexpected
  terminal task failure as a distinct lifecycle result.
- Settings load/save remains a synchronous presentation gateway. Loading occurs
  before a relay session is started and saving uses synchronous handler paths;
  any future async settings path must offload the adapter explicitly.
- LCStatsTracker values are validated as bounded UTF-8 JSON, but the relay does
  not own a versioned field-level payload schema.

Future changes must preserve the receive, archive, retry, credential, and
visible-state contracts documented here or update their canonical documents and
tests in the same change.

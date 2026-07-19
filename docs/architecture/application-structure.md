# Application structure

## Purpose

LCStats Relay is an asynchronous desktop adapter. It receives one JSON payload
per LCStatsTracker SSE response, archives the exact received text, and can send
the parsed value to a Google Apps Script Web App.

## Current module map

The executable entry point is `lcstats_relay.__main__`. The source tree has four
current responsibilities:

- `app/main.py` configures the Flet page and mounts the monitor.
- `app/composition.py` is the production composition root. It selects outputs,
  authentication policy, persistence implementations, and the connection
  manager without requiring the UI to construct those details.
- `core/` contains the receiver, relay and retry orchestration, observable
  connection state, output implementations, and filesystem persistence.
- `ui/monitor.py` owns Flet controls, navigation, input validation, settings
  editing, in-memory GAS credentials, manager start/stop actions, and rendering
  connection snapshots.

Dependencies currently point inward from the Flet entry point and composition
root toward `core/`. However, `core/` still includes concrete HTTP and
filesystem implementations; it is not yet a framework-independent domain
layer.

## Runtime flow

1. `app/main.py` creates `MonitorView` with the production manager factory.
2. The user supplies a loopback tracker URL, a data directory, and optionally a
   GAS destination and token.
3. `app/composition.py` builds a required archive output and, when configured,
   a retryable GAS output.
4. `ConnectionManager` creates one shared `httpx.AsyncClient`, a
   `StatsReceiver`, an `OutputDispatcher`, and concurrent receive/retry loops.
5. Each received payload updates `RelayStateStore`, invokes the payload callback
   for valid JSON, and is dispatched in registration order.
6. State snapshots flow back to the monitor through a callback. The monitor
   renders summaries and never displays the raw payload body.

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
- Extend the fixed `app/`, `core/`, and `ui/` packages with focused modules
  rather than growing existing orchestration or view modules indefinitely.
- Introduce ports at I/O boundaries when replacing or testing concrete HTTP,
  filesystem, clock, sleep, or UI behavior.

## Known structural limitations

The current layout is a starting point, not the target quality ceiling:

- `ui/monitor.py` combines presentation, navigation, validation, persistence,
  credential state, and lifecycle coordination in one class.
- `ConnectionManager` owns a background task but does not expose unexpected
  terminal task failure as a first-class lifecycle result.
- Filesystem reads and writes are synchronous even when called by asynchronous
  relay paths.
- Some callbacks and factories use positional arguments at boundaries where
  keyword-only records would make contracts clearer.

Refactors should reduce these responsibilities without changing the receive,
archive, retry, credential, or visible-state contracts documented here.

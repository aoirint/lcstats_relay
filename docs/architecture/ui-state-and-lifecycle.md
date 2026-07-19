# UI state and lifecycle

## Current ownership

`MonitorView` currently owns one active manager, persisted non-secret settings,
an in-memory GAS token, and all Flet controls. It renders three full-window
views inside one root container: monitor, general settings, and GAS
authentication.

The manager owns receiver and retry tasks. `RelayStateStore` emits copied
snapshots through the callback supplied by the view; output state objects in a
snapshot are not shared with the mutable store.

## Start, stop, and close

- Start validates the saved settings, stops an existing manager if present,
  creates a new manager, locks settings controls, and starts background work.
- Stop awaits the manager, clears it, unlocks settings controls, and renders the
  stopped view.
- Window close awaits the same manager stop operation.
- Repeated `ConnectionManager.start()` calls are ignored while its task is
  running.

Cancellation is intentionally re-raised in receiver and output dispatch paths.
Ordinary receive errors are converted to safe type- or status-based messages
and followed by a three-second reconnect countdown. Pending output retries run
every 30 seconds.

## Presentation semantics

The monitor shows a global health summary and one card per configured output.
Input errors affect global health. Output errors and nonempty retry queues mark
the output and global health as requiring attention. Raw payload data is not
rendered by `add_payload`.

Tests and future views should assert semantic state and user-visible behavior,
not control-list indexes or private fields. Stable presentation models and
small semantic component builders are preferred over exposing Flet internals.

## Refactoring invariants

When lifecycle or presentation is split into smaller modules:

- exactly one current manager generation may update the visible running state;
- a stopped or replaced manager must not publish stale completion state;
- unexpected background-task termination must become an observable error;
- close must await owned background work;
- settings remain locked while the active generation is running;
- the GAS token remains memory-only and absent from persisted settings, logs,
  state snapshots, and displayed URLs;
- Flet-specific controls remain at the outer presentation boundary.

The first three invariants describe the desired robust boundary. The current
implementation does not yet represent manager generations or unexpected task
termination explicitly; changes in those areas require focused regression
tests.

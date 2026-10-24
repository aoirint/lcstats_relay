# UI state and lifecycle

## Current ownership

`MonitorController` owns the active manager, persisted non-secret settings and
the current GAS token loaded from an OS credential store. `MonitorView` owns the Flet controls. It renders three full-window
views inside one root container: monitor, general settings, and GAS
authentication.

Logging adds no view or configuration fields; the existing storage setting
controls archive/queue data only. See the [logging decision](relay-output.md#operational-diagnostics).

The manager owns receiver and retry tasks. `RelayStateStore` emits copied
snapshots through the callback supplied by the view; output state objects in a
snapshot are not shared with the mutable store.

## Credential persistence decision

Tokens must survive application restarts without entering settings JSON. Use
Flet's official `flet-secure-storage` 1.0.4 service, aligned with Flet 1.0.4,
through the Flet-free `GasTokenStore` port. This avoids another third-party
Python keyring library or a custom Win32 implementation. Memory-only storage
does not meet the restart requirement; plaintext settings are excluded.

The reviewed Windows backend, `flutter_secure_storage_windows` 4.1.0, calls
`CredReadW`, `CredWriteW`, and `CredDeleteW`, with machine-persistent credentials
for the current user. Windows backward-compatibility migration is disabled.
See the [official Flet source](https://github.com/flet-dev/flet/tree/v1.0.4/sdk/python/packages/flet-secure-storage)
and [reviewed Windows backend](https://pub.dev/packages/flutter_secure_storage_windows/versions/4.1.0).

On Linux the same official service delegates to libsecret and Secret Service.
GNOME Keyring is the verified provider; a graphical session with an unlocked
keyring is part of the supported configuration. The native build gate checks
save, restore and deletion across three processes in an isolated D-Bus session.
See [Linux runtime prerequisites](../operations/release.md#linux-runtime-prerequisites).

Credential names combine an app prefix and a SHA-256 digest of the validated GAS
URL. A token saved for one destination is never implicitly used for another.
Release versions and installation paths do not enter the credential name.
Startup restores the token before mounting editable controls. Stored values
are never populated into controls. A masked placeholder in the password field
indicates a saved token, and a short helper names the platform store. The mask
is a hint, never the field value or a replacement credential. Deletion
removes the current destination's saved entry and memory copy, leaving its URL.

OS calls have a ten-second timeout. Only Flet's documented RPC `RuntimeError`
and `TimeoutError` are translated at the service boundary; failures show a
fixed error and emit metadata without backend exception text. Edits and Start
are blocked during writes/deletions. Closing a page prevents late UI updates.
Browser storage is rejected; there is no plaintext fallback.

A token write precedes settings persistence, and accepted in-process settings
change only after both succeed. These two stores are not transactional: a JSON
write failure can leave an OS entry for the proposed destination. Retrying Save
can reuse that entry. Clearing a destination disables its output but does not
silently erase saved credentials. The trust boundary is the current OS account;
this does not isolate secrets from other programs running as that account.

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
- the GAS token persists only in the OS credential store and stays absent from settings, logs,
  state snapshots, and displayed URLs;
- Flet-specific controls remain at the outer presentation boundary.

The first three invariants describe the desired robust boundary. The current
implementation does not yet represent manager generations or unexpected task
termination explicitly; changes in those areas require focused regression
tests.

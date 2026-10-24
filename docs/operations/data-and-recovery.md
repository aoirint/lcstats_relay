# Data and recovery

## Persisted data

LCStats Relay writes four categories of local data:

- Settings: `%APPDATA%/lcstats-relay/settings.json` when `APPDATA` exists,
  `$XDG_CONFIG_HOME/lcstats-relay/settings.json` when configured, otherwise
  `~/.config/lcstats-relay/settings.json`.
- Archive: `<data_dir>/archive/YYYY-MM-DD/*.json`, containing the exact received
  JSON text plus a final newline.
- Retry queue: `<data_dir>/queue/*.json`, containing output identity, timestamps,
  raw and parsed payloads, a random correlation ID, and any parse error needed
  for a later attempt.
- Diagnostic logs: `relay.log` and up to four rotated backups in
  `%LOCALAPPDATA%/lcstats-relay/logs` on Windows, or `<default_data_dir>/logs`
  on Linux. This location is independent of the configured archive directory.

For new settings, the default `data_dir` is
`%LOCALAPPDATA%/lcstats-relay/data` on Windows. On Linux it is
`$XDG_DATA_HOME/lcstats-relay` when configured, otherwise
`~/.local/share/lcstats-relay`. A data directory already saved in settings is
preserved, including the former relative default, until the user changes it.

Settings and individual data records are written to a unique sibling temporary
file, flushed to the filesystem, and atomically replaced. Unique names avoid
collisions between concurrent writers. The application still does not claim
whole-directory durability across sudden storage or operating-system failure.

## Diagnostic logs

Relay writes operational events with Python's standard logging handlers. The
fixed location is independent of the editable archive directory:

- Windows: `%LOCALAPPDATA%\lcstats-relay\logs\relay.log`
- Linux: `$XDG_DATA_HOME/lcstats-relay/logs/relay.log`, or
  `~/.local/share/lcstats-relay/logs/relay.log` when XDG_DATA_HOME is unset.

There is no logging UI or destination setting. To inspect recent Windows
activity, run:

```powershell
Get-Content "$env:LOCALAPPDATA/lcstats-relay/logs/relay.log" -Tail 100
```

Read the UTC time and `event=` value, then join lines with the same `id=`.
`output_failed` carries a safe category and, when available, `http=` status.
`authentication` includes GAS token rejection; `response_format` means the
reply was not the expected JSON acknowledgement. `queue_saved` followed later
by `retry_removed` shows that a pending delivery was retained and then cleared.
The [architecture decision](../architecture/relay-output.md#operational-diagnostics)
owns field selection and the reason for retaining this file alongside Flet's
standard console log.

`RotatingFileHandler` appends across restarts and keeps a 1 MiB active file plus
four backups (`relay.log.1` through `.4`), approximately 5 MiB total. Copy the
relevant files before extended troubleshooting overwrites older records. Use
one Relay process per user log directory; rotation does not coordinate multiple
writers. Logs are flushed per event and are not a crash-durable transaction
journal.

If the file cannot open, events fall back to stderr with
`event=log_file_unavailable`. In packaged apps Flet captures that output in its
`console.log`; it is replaced on the next startup. Check file permissions and
free space before restarting. Standard Python logging reports subsequent
handler write failures to stderr; no separate UI error state is maintained.

### Sharing diagnostics

Review the relevant `relay.log*` files before sharing. Operational event callers
exclude credentials, URLs, payloads and exception text; the integration tests
exercise that boundary. Flet's `console.log` can contain framework traces and
is not covered by this application-event policy. Do not bundle settings,
archives or queue files. Share only the files and time range needed for the
incident.

## Secrets

The GAS token is not part of `RelaySettings`. **設定 → Google Apps Script → 設定**
opens GAS authentication. **保存** stores the token in the platform credential
store; on Windows this is **Windows 資格情報マネージャー**. Restart restores it.
The token field shows a masked placeholder when a token is saved. Type a
replacement to update it; leaving the field untouched keeps the saved value.
A destination without a saved token retains unauthenticated
GAS behavior.

**トークンを削除** removes the current destination's credential and memory copy.
It is disabled while the URL field contains an unsaved edit. Clearing the GAS
URL disables output but retains saved credentials: delete first when forgetting
them is intended. An OS-store failure leaves accepted settings unchanged and
shows an error; unlock or repair the store, then retry. No plaintext fallback
is used. Architectural details belong to the
[credential decision](../architecture/ui-state-and-lifecycle.md#credential-persistence-decision).

The restored token remains in memory for outgoing GAS authentication and is
applied as a query parameter only while preparing the request.

Do not put the token in the GAS URL, settings file, tests, logs, screenshots,
archive records, or retry records. Rotate the remote token if it is exposed.

## Recovery procedures

### Invalid settings JSON

1. Stop the application.
2. Copy the settings file to a safe diagnostic location if its contents are
   needed.
3. Correct the JSON object or move the invalid file aside.
4. Restart the application. A missing settings file restores defaults; save the
   desired settings again through the UI.

### Pending GAS deliveries

Retry files are removed only after their registered output succeeds. Preserve
the queue directory while diagnosing a destination outage. After correcting
the GAS URL, token, or remote service, restart or reconnect and allow the retry
loop to process the records.

Do not manually replay a queue record unless duplicate delivery is acceptable.
The queue provides at-least-once attempts, not exactly-once delivery.

### Archive failure

An archive failure stops later output attempts for that payload. Correct the
configured path, directory permissions, free space, or filesystem availability
before reconnecting. The failed payload is not automatically placed in the GAS
retry queue because the archive is the required durability boundary.

### Corrupt retry record

The current retry scan reports malformed records as a queue-read error and
leaves them in place. Stop the application, preserve the original file, and
either repair all required fields or move that single record out of the queue.
Keep any removed record until its delivery status is understood.

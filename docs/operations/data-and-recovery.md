# Data and recovery

## Persisted data

LCStats Relay writes three categories of local data:

- Settings: `%APPDATA%/lcstats-relay/settings.json` when `APPDATA` exists,
  `$XDG_CONFIG_HOME/lcstats-relay/settings.json` when configured, otherwise
  `~/.config/lcstats-relay/settings.json`.
- Archive: `<data_dir>/archive/YYYY-MM-DD/*.json`, containing the exact received
  JSON text plus a final newline.
- Retry queue: `<data_dir>/queue/*.json`, containing output identity, timestamps,
  raw and parsed payloads, and any parse error needed for a later attempt.

For new settings, the default `data_dir` is
`%LOCALAPPDATA%/lcstats-relay/data` on Windows. On Linux it is
`$XDG_DATA_HOME/lcstats-relay` when configured, otherwise
`~/.local/share/lcstats-relay`. A data directory already saved in settings is
preserved, including the former relative default, until the user changes it.

Settings and individual data records are written to a unique sibling temporary
file, flushed to the filesystem, and atomically replaced. Unique names avoid
collisions between concurrent writers. The application still does not claim
whole-directory durability across sudden storage or operating-system failure.

## Secrets

The GAS token is intentionally not part of `RelaySettings`. It remains in
memory for the current application process and is applied as a query parameter
only to the outgoing GAS request. Restarting the app clears it.

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

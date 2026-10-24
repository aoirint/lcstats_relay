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
- Diagnostic logs: `relay.jsonl` and up to four rotated backups in
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

Expand **診断ログと保存先** in the monitor, or open Settings, to see the actual
absolute settings, archive, queue, and log paths. Existing relative `data_dir`
values resolve against the current process working directory, which can be
inside Flet's extracted application directory in older distributions.
Changing that setting does not move old archives or queue entries. Record the
old absolute path before changing it and preserve pending deliveries there.

Each UTF-8 JSONL record contains a UTC timestamp, severity, process-session ID,
and event name. Payload events also carry a random `correlation_id`. A new
archive filename ends in that ID, and queue records retain it across retries
and restarts. Older queue records without a valid ID are read without modification.
Their retry events omit the correlation ID, so cross-attempt correlation is
available only for new records. Diagnostic metadata never triggers a migration.
IDs identify a received item, not a player or a content hash. Receiving the same
JSON twice creates two IDs; this is not remote deduplication.

Events cover application start/exit, settings load/save, connection start/stop,
SSE waiting/connection/error/reconnect, payload receipt/parse failure, output
attempt/success/failure/cancellation, queue save/read, and retry/removal. Filter
by `session_id` for one run and `correlation_id` for one delivery. Look for
`output_succeeded` with `output: archive` before the GAS attempt. A
`retry_removed` event means the successful delivery was also removed locally.

Failure records contain a bounded category and, for HTTP failures, the numeric
status. Categories distinguish `authentication`, `http`, `transport`,
`timeout`, `response_format`, `json_parse`, `application`, `archive`, `queue`, and
`storage`. Authentication classification recognizes HTTP
401/403 and the known non-JSON GAS response containing `Invalid token`.
Other HTML errors are classified as `response_format` without storing the page.
An unrecognized output failure uses `delivery`.

Each log file is limited to 1 MiB, with four backups (`relay.jsonl.1` through
`.4`), for approximately 5 MiB total. `.1` is the most recent backup. Old
records expire by size, so copy relevant logs before extended troubleshooting.
Use one Relay process per user log directory: rotation does not coordinate
multiple processes. Records are flushed on each event, but logs are diagnostic
evidence rather than a power-loss-durable transaction journal. Forced process
termination can omit the final exit or delivery events.

If creation, writing, rotation, or closing fails, Relay continues operating.
The UI marks **診断ログ書き込み失敗** on its next state refresh; this warning
remains for the process lifetime because some records may already be missing.
Correct permissions/free space and restart. A final close failure may occur
after the UI has closed. The error fallback never prints the failed record or
exception traceback. Unexpected application errors retain their existing propagation
behavior; logging does not convert them into handled connection errors.

### Sharing diagnostics

Share only the relevant `relay.jsonl*` files after reviewing them. The writer
allows only fixed events/categories, numeric HTTP codes, timestamps, and UUIDs.
It excludes tokens, URLs (including deployment identifiers), local paths,
player IDs/names, payloads, response bodies, and exception text/tracebacks.
Third-party HTTP/Flet logs are not copied into this sink. Timestamps and activity
patterns are still operational information; choose an appropriate recipient.
Do not bundle settings, archives, queue files, or screenshots of absolute paths:
these can expose private endpoints, players, or the local account name.

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

# Relay output architecture

This document describes LCStats Relay's output-side design after a payload has
already been received from the source.

The behavior here is independent of LCStatsTracker. LCStatsTracker provides the
source payload; LCStats Relay owns archiving, delivery to configured outputs,
retry behavior, authentication policy, and UI-facing output state.

## Payload handling

The raw JSON payload extracted from the source response is preserved first so the
original payload can be archived. The JSON is parsed before it is sent to
structured outputs such as Google Apps Script.

If parsing fails, LCStats Relay can still keep the raw payload in the archive,
but structured outputs that require JSON are not delivered.

## Output model

Outputs are modeled as registered output surfaces. Each output has its own
implementation and its own UI-facing state.

This separation is intentional:

- Output delivery logic is separate from state reporting.
- Google Apps Script authentication is separate from Google Apps Script delivery.
- The UI displays per-output success, error, and message state without depending
  on the implementation details of each output.

Additional output surfaces should be added as peers of the existing outputs, not
as special cases inside an existing output.

## Standard output surfaces

LCStats Relay currently registers two standard outputs.

### Local archive

The local archive writes the received payload under the configured local data
directory:

```text
<data-dir>/archive/YYYY-MM-DD/
```

The archive is required. It is the durability boundary for a received payload.
If the archive write fails, later outputs are not attempted for that payload.

### Google Sheets through Google Apps Script

The Google Sheets output posts the parsed LCStatsTracker JSON payload to a
configured Apps Script receiver. The reference integration is
[`lcstats_overlay`](https://github.com/aoirint/lcstats_overlay): its `code.gs`
ingests the payload into Google Sheets, and its spreadsheet formulas and
`index.html` turn the results into an OBS overlay.

Compatibility is defined by this delivery contract. Another receiver can be
used if it implements the same request, authentication and acknowledgement
behavior. An arbitrary Apps Script web app is not sufficient.

The reference receiver requires its `LCSTATS_TOKEN` script property and receives
the matching value through the `token` query parameter. Relay adds this parameter
to the outgoing request through its authentication adapter. Receiver deployment
and spreadsheet setup belong to the
[reference integration's instructions](https://github.com/aoirint/lcstats_overlay#apps-script-ingestion-security).

Delivery succeeds only after a successful HTTP status, an `application/json`
media type, and an object containing the Boolean `"ok": true`. HTML errors with
HTTP 200, malformed JSON, and negative/missing acknowledgements remain failures
and are eligible for the existing retry queue. Response bodies never enter
diagnostic logs or UI error messages. A remote script returning another success
shape must be updated to acknowledge this contract.

Authentication data is provided through a separate authentication component.
The token is not embedded in the URL by the UI and is not saved to the settings
file. The GAS destination URL is saved with the rest of the non-secret settings.

If the Google Apps Script output fails after the archive succeeds, the failed
delivery is stored in `<data-dir>/queue/` only when the failure is retryable.

## Delivery guarantees

LCStats Relay preserves the received payload locally before attempting later
outputs. Every output declares either `none` or `at-least-once` retry semantics.
The local archive uses `none`; GAS uses `at-least-once`. A timeout or connection
loss can occur after GAS accepted a request but before the relay observed the
response, so automatic retries can submit a duplicate. GAS does not provide this
relay with an idempotency contract, and the relay does not claim exactly-once
delivery. A receiving script should therefore tolerate duplicate submissions.

Each GAS attempt has a 30-second total application timeout. The separate SSE
read remains open until LCStatsTracker produces a payload, so it intentionally
does not share that finite read deadline.

The queue is output-oriented so that future output surfaces can be retried as
peers of the existing Google Apps Script output.

## Operational diagnostics

The requirement is to trace reception, archiving, GAS delivery and retries after
an incident, including after restarting Relay. Logging has no dedicated view,
user-selectable destination or UI status model.

Use Python's standard `logging` API and `RotatingFileHandler`. The entry point
owns one `logging_session` around `ft.run`; it appends to a fixed per-user file
and releases the handler on exit. No third-party logging library, custom log
manager or serialization framework is required.

Flet also uses Python logging and captures packaged stdout/stderr in
`console.log`. That file alone was considered: the inspected
[Flet 1.0.4 template](https://github.com/flet-dev/flet/releases/tag/v1.0.4),
`lib/python.dart`, opens it with `w+` at startup. It therefore cannot preserve
an earlier run after a restart. A standard rotating file handler supplies that
missing retention behavior. Rotation is capacity-based: it bounds disk use,
not the number of complete runs retained.

Keeping previous `console.log` files per launch was also considered. The file
is opened before the app module runs, so that design needs a custom Flet
bootstrap template. The selected standard-handler configuration avoids owning
that framework startup modification. See the official [Flet logging guide](https://flet.dev/docs/cookbook/logging/)
and [packaged console output contract](https://flet.dev/docs/publish/#console-output).

The dedicated `lcstats_relay.events` logger records UTC time, severity, fixed
event names, payload correlation IDs and optional output/category/HTTP status.
Callers supply only that metadata: never URLs, tokens, raw payloads, player
identities, response bodies or exception text. HTTPX/Flet loggers are not
attached to this file handler. There is no general-purpose redaction layer;
maintainers must preserve this boundary when adding events. The receiver-to-
archive-to-queue integration test verifies it with private fixture data.

A random payload correlation ID is retained in queue records and new archive
filenames, allowing a failed delivery and its later retry to be joined. Startup
and shutdown events delimit runs. Ordinary source runs and packaged apps use
the same operational logger; Flet's console remains available for framework
and unexpected-runtime diagnostics.

If opening the file fails, standard console logging records
`log_file_unavailable` and subsequent events. Later write errors use Python's
standard logging error handling. Logging does not change delivery decisions or
consume unexpected application exceptions. Retention and inspection commands
are owned by [Data and recovery](../operations/data-and-recovery.md#diagnostic-logs).

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

The Google Sheets output posts the parsed JSON payload to a configured Google
Apps Script Web App URL.

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

# LCStatsTracker input and output contract

This document describes the external data contract that LCStats Relay expects
from LCStatsTracker and the output model used after a payload is received.

## Input source

LCStats Relay connects to the local LCStatsTracker endpoint and waits for a
statistics payload.

The default endpoint is:

```text
http://127.0.0.1:2145/
```

The receiver also accepts explicit loopback URLs such as `http://localhost:2145/`
and `http://[::1]:2145/`, but it does not rewrite them before connecting.

## Response model

LCStatsTracker is treated as a one-payload-per-response source.

Expected behavior:

- The endpoint returns one statistics payload in a single HTTP response.
- The response body uses an SSE-style `data:` line containing JSON.
- The source closes the response after the payload is sent.
- LCStats Relay reconnects after processing that payload.

LCStats Relay does not require or implement broader SSE stream semantics for
this integration. In particular, the current contract does not rely on:

- Multiple events within one long-lived response.
- Event IDs.
- `Last-Event-ID` replay.
- Named SSE event types.
- Server-side delivery guarantees for multiple concurrent clients.

LCStatsTracker may reset its pending data after a client receives it. For that
reason, LCStats Relay should be the only client consuming the endpoint.

## Payload handling

The raw JSON payload extracted from the `data:` line is preserved first so the
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

The local archive writes the received payload under:

```text
data/archive/YYYY-MM-DD/
```

The archive is required. It is the durability boundary for a received payload.
If the archive write fails, later outputs are not attempted for that payload.

### Google Sheets through Google Apps Script

The Google Sheets output posts the parsed JSON payload to a configured Google
Apps Script Web App URL.

Authentication data is provided through a separate authentication component.
The token is not embedded in the URL by the UI and is not saved to the settings
file.

If the Google Apps Script output fails after the archive succeeds, the failed
delivery can be stored in `data/queue/` and retried later.

## Delivery guarantees

LCStats Relay preserves the received payload locally before attempting later
outputs. Retried outputs should be treated as at-least-once delivery. A receiving
output should therefore tolerate duplicate submissions when practical.

The queue is output-oriented so that future output surfaces can be retried as
peers of the existing Google Apps Script output.

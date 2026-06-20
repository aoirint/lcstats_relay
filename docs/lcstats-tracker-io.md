# LCStatsTracker input contract

This document describes only the external source contract that LCStats Relay
expects from LCStatsTracker.

It does not describe LCStats Relay outputs such as local archive storage,
Google Apps Script delivery, retry queues, or UI state. Those are Relay
implementation concerns and are documented separately in
[Relay output architecture](relay-output-architecture.md).

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

LCStats Relay extracts the raw JSON payload from the first `data:` line in the
response. JSON parsing happens after extraction and is not part of the
LCStatsTracker transport contract beyond the requirement that the `data:` value
be JSON.

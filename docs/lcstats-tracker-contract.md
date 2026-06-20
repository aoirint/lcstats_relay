# LCStatsTracker contract

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

## Query window and single-use data

LCStatsTracker has an important timing constraint around Lethal Company days.
After one in-game day ends, the resulting statistics can be queried only once
before the next in-game day ends.

That means a successful query is also a consumption event. If LCStats Relay, the
network stack, or any other client fails after the data is consumed, the same
payload may no longer be recoverable from LCStatsTracker.

Expected behavior:

- A payload should be queried exactly once during the window between the end of
  one in-game day and the end of the next in-game day.
- If the payload has already been consumed, LCStatsTracker is expected to return
  an error response according to its own API behavior.
- LCStats Relay must treat such an error response as a source-side failure, not
  as a signal that the previous payload can be fetched again.
- Multiple consumers are unsafe because the first successful consumer may make
  the payload unavailable to the others.

## Payload handling

LCStats Relay extracts the raw JSON payload from the first `data:` line in the
response. JSON parsing happens after extraction and is not part of the
LCStatsTracker transport contract beyond the requirement that the `data:` value
be JSON.

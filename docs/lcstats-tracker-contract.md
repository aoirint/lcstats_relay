# LCStatsTracker contract

This document describes only behavior that can be explained from the
`MakuAureo/LCStatsTracker` repository.
The upstream project is MIT licensed; this document summarizes behavior and does
not copy source code.

## Reference

- Repository: <https://github.com/MakuAureo/LCStatsTracker>
- LCStatsTracker version: `1.2.4`
- Commit: `3cca19b38e54ccb1610d0cd3a838922dbf696560`

## Input source

A client connects to the local LCStatsTracker endpoint and waits for a
statistics payload.

The upstream README describes a local server on port `2145`, and the current
implementation registers this endpoint:

```text
http://localhost:2145/
```

## Response model

LCStatsTracker is treated as a one-payload-per-response source.

Expected behavior:

- The endpoint returns one statistics payload in a single HTTP response.
- The response body uses an SSE-style `data:` line containing JSON.
- The HTTP response uses `text/event-stream`.
- The source closes the response after the payload is sent.
- The client reconnects after processing that payload.

A compatible client does not need broader SSE stream semantics for this
integration. In particular, the current contract does not rely on:

- Multiple events within one long-lived response.
- Event IDs.
- `Last-Event-ID` replay.
- Named SSE event types.
- Server-side delivery guarantees for multiple concurrent clients.

LCStatsTracker may reset its pending data after a client receives it. For that
reason, only one client should consume the endpoint.

## Query window and single-use data

LCStatsTracker has an important timing constraint around Lethal Company days.
After one in-game day ends, the resulting statistics can be queried only once
before the next in-game day ends.

That means a successful query is also a consumption event. In the current
implementation, the server resets its pending data after writing the response,
so the same payload is not available again after that response completes.

Expected behavior:

- A payload should be queried exactly once during the window between the end of
  one in-game day and the end of the next in-game day.
- The current implementation does not expose a distinct "already consumed" HTTP
  error response.
- After a payload is sent, the server resets its pending data and waits for the
  next day to finish.
- A request made after the payload has been consumed should therefore be
  expected to wait for the next available payload, not to recover the previous
  payload.
- Multiple consumers are unsafe because the first successful consumer may make
  the payload unavailable to the others.

## Payload handling

A client extracts the raw JSON payload from the first `data:` line in the
response. JSON parsing happens after extraction and is not part of the
LCStatsTracker transport contract beyond the requirement that the `data:` value
be JSON.

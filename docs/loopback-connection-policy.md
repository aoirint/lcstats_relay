# Loopback connection policy

This document records the current localhost connection-delay policy for the app.
It is intentionally narrow. If the networking behavior grows later, this
content should be folded into a broader connection or receiver specification.

## Problem

On some systems, `localhost` resolves to both IPv6 and IPv4 loopback addresses.
If the server only listens on one address family, the client may first try the
other one, wait for that attempt to fail, and then fall back.

For a local desktop integration, that extra connection attempt can make startup
or reconnects feel unnecessarily slow. The common case for LCStatsTracker is a
loopback HTTP endpoint on port `2145`, so the default should avoid avoidable name
resolution and dual-stack fallback work.

## Policy

The receiver uses this policy:

- The default SSE URL is `http://127.0.0.1:2145/`.
- `127.0.0.1` is used because it directly selects IPv4 loopback and avoids
  `localhost` name resolution.
- Explicit user input is honored as entered.
- `http://localhost:2145/` is accepted for compatibility.
- `http://[::1]:2145/` is accepted when the user intentionally wants IPv6
  loopback.
- The receiver does not silently rewrite `localhost` to `127.0.0.1`.
- The receiver does not add hidden fallback behavior across loopback addresses.

This keeps the application predictable: the default is fast for the expected
local setup, while explicit advanced choices remain under user control.

## Operational guidance

Use `http://127.0.0.1:2145/` unless there is a specific reason to use another
loopback address.

If the source only listens on IPv6 loopback, use:

```text
http://[::1]:2145/
```

If an external tool or compatibility layer expects `localhost`, use:

```text
http://localhost:2145/
```

Connection errors should be shown as receiver errors. They should not be hidden
behind automatic address rewriting, because rewriting would make the configured
endpoint harder to reason about.

## Future integration

This document is narrower than a full receiver specification. If future work
adds endpoint discovery, retry backoff policy, connection diagnostics, or
multi-source support, this policy should move into that more complete
specification.

# Development and verification

## Prerequisites

- Python 3.14.9, matching `.python-version`
- [uv](https://docs.astral.sh/uv/)
- [APM](https://github.com/microsoft/apm) for repository-local Agent Skills

Run commands from the repository root. Restore the exact committed dependency
and Skill state before changing code:

```powershell
uv sync --locked --all-groups
apm install --frozen
apm audit --ci
```

Do not edit `.agents/skills/` directly. The canonical Skill source and APM
update procedure are documented in [`../../AGENTS.md`](../../AGENTS.md).

## Required checks

Run the complete local quality gate with locked Python dependencies:

```powershell
uv lock --check
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests scripts
uv run --locked pytest
apm audit --ci
```

Pytest is configured to fail below 100 percent statement and branch coverage.
A passing coverage percentage is necessary but not sufficient: tests must
still cover success, invalid input, expected operational failure,
cancellation, and stale asynchronous completion where those behaviors apply.

## Change procedure

1. Start from current `origin/main` in an isolated worktree.
2. Identify the owning domain, architecture, or operations document before
   changing an established contract.
3. Add or update behavioral tests with the implementation. Prefer public,
   semantic boundaries over private attributes and Flet control indexes.
4. Run the required checks above.
5. Review the diff for accidental lockfile, generated Skill, secret, or user
   data changes.
6. Open a focused pull request and merge it with the repository rules in
   [`../../AGENTS.md`](../../AGENTS.md).

When dependencies intentionally change, run `uv lock`, review the complete lock
diff and artifact sources, then repeat the locked checks. Do not use an unlocked
test run as release evidence.

## Security update review (2026-10-24)

The maintainer authorized exact cooldown exceptions for verified security fixes.
The seven-day default remains active for every other dependency.

- [certifi GHSA-6q48-6c7w-9gw2](https://github.com/advisories/GHSA-6q48-6c7w-9gw2):
  pin `certifi==2026.10.19` to remove the compromised emSign trust anchor.
  Its artifacts were uploaded on 2026-10-20; remove only its cooldown waiver
  after 2026-10-27T02:24:16Z. Keep the patched version floor when unpinning.
- [uv 0.13.5](https://github.com/astral-sh/uv/releases/tag/0.13.5):
  published 2026-10-22, removes compromised CA trust and includes repaired
  managed Python builds. Normal eligibility begins 2026-10-29.
- [Python 3.14.9](https://www.python.org/downloads/release/python-3149/):
  the 2026-10-21 security release replaces the affected bundled pip CA store.
  Its managed build is delivered by the reviewed uv release; the source-run
  and CI Python patch is pinned in `.python-version`.
- `urllib3>=2.8.0` addresses
  [chunked streaming](https://github.com/advisories/GHSA-vxq7-64xx-v4gw),
  [proxy TLS configuration](https://github.com/advisories/GHSA-8988-9cw3-xx77), and
  [deflate streaming](https://github.com/advisories/GHSA-gh4c-6fx4-qh6g).
  `oauthlib>=4.0.0` addresses
  [PKCE comparison](https://github.com/advisories/GHSA-xpv3-w29h-x7cv) and
  [revocation JSONP](https://github.com/advisories/GHSA-hj66-6f7g-4r5v).
  Both releases have completed cooldown. They are transitive Flet dependencies;
  Relay uses HTTPX directly and does not expose OAuth authorization endpoints.

These changes cover the locked source environment and CI builder. A new native
Flet bundle has not been built or inspected, so its embedded interpreter and
trust store are not yet verified by this change.

## Reviewed dependency snapshot (2026-10-24)

The source environment uses Flet 1.0.4 as a matching Python/CLI/web/desktop set,
with mypy 2.4.0 and Ruff 0.17.1. The lock includes all compatible transitive
updates available after the normal seven-day cooldown. The old msgpack waiver
was removed; its patched floor is now 1.2.3.

Actions use immutable release commits: setup-uv 10.3.0, upload-artifact 7.0.2,
and download-artifact 8.0.2. Workflow checking uses pinact 5.0.0; its long CLI
flags already use the required double-dash form. Shared Skills use the reviewed
2026-09-01 commit recorded in the APM lock and third-party notices.

APM remains at the repository-reviewed 0.28.0 bootstrap. The newer 0.33.0 CLI
requires a separate bootstrap/lock-generator migration review; it was not
substituted merely because it has completed cooldown. Python remains on the
3.14 line used by the native packaging contract. A Python 3.15 migration and
native Flet 1.0.4 artifact verification remain separate validation work.

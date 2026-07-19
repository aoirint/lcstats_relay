# Development and verification

## Prerequisites

- Python 3.14, matching `.python-version`
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
uv run --locked mypy src tests
uv run --locked pytest
apm audit --ci
```

Pytest is configured to fail below 100 percent statement coverage. A passing
coverage percentage is necessary but not sufficient: tests must still cover
success, invalid input, expected operational failure, cancellation, and stale
asynchronous completion where those behaviors apply.

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

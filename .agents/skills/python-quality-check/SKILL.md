---
name: python-quality-check
description: >-
  Quality-check Python repository changes. Use when validating Python source,
  tests, pyproject.toml, uv.lock, Ruff, mypy, pytest, or uv-based dependency
  and verification workflows.
---

# Python Quality Check

Use this skill together with `code-quality-check`: this skill defines Python-specific setup,
commands, and scope decisions, while `code-quality-check` defines shared readability,
verification-discipline, comment, and supply-chain expectations.

Use `security-check` for dependency provenance, package-runner risk, lockfile updates, and the
repository supply-chain cooldown policy. Do not duplicate a separate cooldown policy here.

## When to Use

- Use this skill when validating source or test changes in this Python repository.
- Use this skill when changing `pyproject.toml`, `uv.lock`, Ruff, mypy, pytest, or uv configuration.
- Use this skill before committing Python changes, before merging a worktree branch, and before
  preparing PR verification notes.

## Goals

- Keep dependency installation reproducible with `uv sync --locked --all-groups`.
- Use `uv` for dependency installation and Python quality checks.
- Keep mypy strict.
- Keep Ruff strong enough for a new project baseline while keeping each selected rule family
  documented in `pyproject.toml`.
- Keep Python package and lockfile changes aligned with `security-check`.

## Workflow

1. Start from the repository root or active worktree root.
2. Use `security-check` before adding or updating Python packages, package-runner invocations, or
   lockfile entries.
3. Install dependencies with `uv sync --locked --all-groups`.
4. Run `uv run ruff check .`.
5. Run `uv run ruff format --check .`.
6. Run `uv run mypy src tests`.
7. Run `uv run pytest`.
8. Follow the failure-handling and verification-note guidance in `code-quality-check`.

## Ruff Policy

- Keep `[tool.ruff.lint] select` as a curated baseline rather than `ALL`.
- Every `select` entry must have an adjacent comment explaining what that rule family contributes.
- Every `ignore` or `per-file-ignores` rule code must have an adjacent, site-specific reason
  comment. Put the comment immediately before the rule code.
- Every line-level Ruff ignore, such as `# noqa: S603`, must include a specific reason for each
  ignored rule code in the same comment or an immediately adjacent comment.
- Prefer fixing new Ruff findings when the rule improves readability, typing, security, or
  maintainability.
- Use `per-file-ignores` only for narrow, explainable exceptions tied to a concrete file or test
  pattern.
- When changing Ruff configuration, run both Ruff checks and confirm they are free of warnings as
  well as errors.

## Default Verification Set

Use this default sequence unless the user asks for something narrower or broader.

```bash
uv sync --locked --all-groups
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
```

## Scope Guidance

- Use `ruff`, `mypy`, and `pytest` for source and test changes.
- Use `src` and `tests` as the normal typing and test scope.
- Do not add script-specific validation steps unless the repository actually adds maintained
  scripts for that purpose.
- Do not use `pip install` or `pipenv` for repository verification unless a task explicitly concerns
  those tools.
- If executable verification is blocked after dependency installation, report the concrete blocker
  using `code-quality-check`.

## Output Checklist

- Dependencies installed when required.
- Ruff lint status recorded.
- Ruff format status recorded.
- Mypy status recorded.
- Pytest status recorded.
- `security-check` applied for Python package or lockfile changes.
- Any skipped check has a concrete reason.

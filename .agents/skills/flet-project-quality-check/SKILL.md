---
name: flet-project-quality-check
description: >-
  Create, align, or review production-quality Python Flet applications across
  package and module architecture, presentation state, Flet controls, async
  lifecycle, persistence and I/O boundaries, uv dependency management, Ruff,
  strict mypy, pytest, 100% branch and statement coverage, GitHub Actions,
  Flet packaging, security, and developer documentation. Use for new Flet
  projects, large UI refactors, quality-baseline adoption, CI setup, release
  readiness, or reviews of pyproject.toml, uv.lock, src/tests layout, and Flet
  application code. Pair with software-documentation-maintenance for document
  ownership and with security-check for dependencies, secrets, and CI supply
  chain decisions.
---

# Flet Project Quality Check

## When to Use

Use this Skill for `setup`, `alignment`, `implementation`, `review`, or
`release-readiness` work on a Python application whose user interface is built
with Flet. Apply the baseline to the whole repository; do not accept a weak UI,
missing documentation, or an existing low test bar as precedent.

For Python projects without Flet, use a general Python/code quality workflow.
For prose wording alone, use `prose-quality-check`. This Skill owns which
Flet/Python facts and quality gates are required, not the repository-wide
documentation taxonomy or general CI supply-chain policy.

## Goals

- Keep domain and application behavior independent of Flet controls and page state.
- Make every UI state transition, async task, side effect, and render decision explicit and testable.
- Reproduce the Python environment from `pyproject.toml` and committed `uv.lock` under a seven-day
  package cooldown.
- Require formatting, linting, strict typing, deterministic tests, and 100% branch and statement
  coverage locally and in GitHub Actions.
- Keep build, package, data, secret, failure, and documentation contracts reviewable.

## Responsibility Boundaries

Use `software-documentation-maintenance` to create and maintain the required
`docs/domain`, `docs/architecture`, and `docs/operations` map. This Skill supplies
the Flet-specific facts those documents must own: supported Flet/Python targets,
UI state and navigation, task lifetime, component boundaries, platform storage,
test/build commands, and packaging behavior.

Use `github-actions-quality-check` for workflow triggers, permissions,
concurrency, action pins, actionlint, ShellCheck, and pinact. Use `security-check`
for package provenance and cooldown, lock changes, secrets, URL/file input,
downloaded tools, caches, build artifacts, and release credentials. Do not
duplicate weaker substitutes here.

## Non-Negotiable Baseline

- Use a `src/` package layout, a thin Flet entry point, and one composition root.
- Separate application policy, presentation state, Flet rendering, and external I/O. Flet types must
  not enter domain/application modules.
- Commit `pyproject.toml`, `.python-version`, and `uv.lock`. Set
  `[tool.uv] exclude-newer = "P7D"` and keep runtime and development dependencies declared.
- Put `ruff`, `mypy`, `pytest`, and `pytest-cov` in a development dependency group.
- Require keyword arguments from the first project-owned parameter at definitions and call sites;
  retain positional compatibility only for a documented external signature.
- Configure Ruff lint and format checks, `mypy` with `strict = true` plus
  `warn_unreachable = true`, and pytest-cov with both branch and statement coverage at 100%.
- Run checks through the locked uv environment. A passing test command that mutates the lockfile is
  not valid verification.
- Require event-owned GitHub Actions: pull-request validation (and merge-queue validation when
  used), plus protected-integration-branch validation re-run on the exact pushed commit. Use direct
  `needs` dependencies to gate plan/build/artifact/release work, least-privilege permissions, and
  full-SHA action pins.
- Maintain the documentation base map required by `software-documentation-maintenance` and make all
  developer procedures executable from a clean clone.

## Workflow

Follow [implementation-runbook.md](references/implementation-runbook.md) in
order. Do not replace its evidence ledger and verification matrix with an
informal list.

1. Classify and inventory the request.
   - Select `setup`, `alignment`, `implementation`, `review`, `release-readiness`, or `plan-only`.
   - Inspect repository guidance, Python/Flet metadata, source/tests, workflows, docs, build assets,
     generated files, and repository settings before proposing a target-specific value.
   - Run
     `uv run --no-project --no-config --locked --script <skill-root>/scripts/check_project.py <repository-root>` for the
     mechanical floor. Treat every finding as evidence to inspect; a pass does not approve
     architecture, UI behavior, tests, security, or release readiness.
2. Establish the target and contracts.
   - Record supported Python minor version(s), Flet version/range, desktop/web/mobile targets,
     operating systems, app identity, entry point, data and secret stores, external services,
     offline behavior, and artifact/release targets.
   - Mark unavailable facts `blocked`. Never fill them from another Flet repository.
3. Align modules and dependency direction.
   - Read [architecture-and-ui.md](references/architecture-and-ui.md) before changing source layout,
     UI state, event handlers, routing, controls, or async work.
   - Keep entry/composition code small. Put framework-free domain/application policy behind ports,
     presentation mapping and controllers in a Flet-free presentation layer, external effects in
     infrastructure adapters, and only Flet control construction/update code in `ui`.
   - Use `entrypoints` and `composition` for startup and wiring; do not place a
     generic `app` package beside `application`. Keep `presentation` and `ui`
     distinct only when the former is Flet-free and the latter is the Flet
     adapter.
   - Split by cohesive state/lifecycle ownership, not by file size alone. A large control tree,
     scattered `page.update()`, control-index navigation, or one object owning settings, networking,
     state transitions, and rendering is a finding.
4. Align tooling, typing, and tests.
   - Read [tooling-and-testing.md](references/tooling-and-testing.md) before editing
     `pyproject.toml`, `uv.lock`, Ruff, mypy, pytest, coverage, or the test layout.
   - Preserve the exact dependency graph with uv; apply package changes only after `security-check`.
   - Test policy and presentation behavior without Flet, then test Flet adapters at semantic
     boundaries. Cover success, validation, failure, cancellation, stale completion, shutdown,
     persistence corruption, and platform-specific paths.
   - Keep coverage at 100% for both branches and statements without broad omissions, fabricated
     tests, or exclusions that hide reachable behavior.
5. Align CI, packaging, and security.
   - Read [ci-packaging-security.md](references/ci-packaging-security.md) before changing workflows,
     `flet build`, assets, identifiers, storage, logging, secrets, caches, or releases.
   - CI must check the lock, exact sync, Ruff lint, Ruff format, strict mypy, tests, coverage, and any
     repository-specific documentation or build contracts from a clean checkout.
   - Keep pull-request and integration-branch entry workflows distinct. Reuse a local Composite
     Action for a same-runner setup/check sequence. Use a reusable workflow only when job-level
     matrix, outputs, or permission boundaries make a Composite Action insufficient, and document
     that reason; do not introduce manual dispatch or cross-workflow polling without an explicit
     operator/trust-boundary need.
   - Verify every selected Flet target on a compatible runner. Keep packaging/release jobs separate
     from untrusted pull-request validation and inspect the final artifact, not only source tests.
6. Align documentation.
   - Invoke `software-documentation-maintenance`. Require root discovery plus indexed domain,
     architecture, and operations documents.
   - Document verified current behavior separately from proposed architecture. Include UI states and
     transitions, task ownership/cancellation, I/O and persistence contracts, supported platforms,
     clean-clone checks, packaging, release, recovery, and known limitations.
7. Verify and report.
   - Execute the runbook verification matrix. Re-run the mechanical checker after edits.
   - Report findings by severity with file/evidence, violated invariant, user or maintainer impact,
     and the smallest complete correction. For implementation work, report changed contracts,
     commands and results, runtime/UI checks, artifact checks, blockers, and residual risk.

## Completion Checklist

- Target Python/Flet/platform and app identity are explicit and consistent.
- Domain/application code imports no Flet or concrete infrastructure.
- Presentation state and transitions are immutable or otherwise centrally owned and independently tested.
- Flet controls render state and emit intents; they do not own business workflows or hidden task state.
- Every background task has an owner, cancellation path, stale-result policy, and shutdown test.
- uv lock/cooldown, Ruff, strict mypy, pytest, branch coverage, and 100% threshold are enforced.
- First-party API definitions and calls require keywords from the first project-owned argument.
- CI is least-privilege, SHA-pinned, lock-preserving, and equivalent to documented local checks.
- Persistence, secrets, logs, external input, and packaged artifacts have explicit safety contracts.
- Required documentation indexes exist and current implementation facts have canonical owners.
- Mechanical and semantic review results are both recorded; neither is presented as the other.

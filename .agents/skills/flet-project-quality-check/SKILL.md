---
name: flet-project-quality-check
description: >-
  Create, align, or review production-quality Python Flet applications across
  package and module architecture, presentation state, Flet controls, async
  lifecycle, persistence and I/O boundaries, semantic UI tests, Flet packaging,
  platform artifacts, security, and developer documentation. Use for new Flet
  projects, large UI refactors, Flet architecture alignment, target packaging,
  release readiness, or reviews of Flet application code. Pair with
  python-quality-check for uv, Ruff, mypy, pytest, coverage, Python packaging,
  and CI quality gates.
---

# Flet Project Quality Check

## When to Use

Use this Skill for `setup`, `alignment`, `implementation`, `review`, or
`release-readiness` work on a Python application whose user interface is built
with Flet. Apply the baseline to the whole repository; do not accept a weak UI,
missing documentation, or an existing low test bar as precedent.

For Python projects without Flet, use `python-quality-check`.
For prose wording alone, use `prose-quality-check`. This Skill owns which
Flet facts and framework quality gates are required, not the repository-wide
Python baseline, documentation taxonomy, or general CI supply-chain policy.

## Goals

- Keep domain and application behavior independent of Flet controls and page state.
- Make every UI state transition, async task, side effect, and render decision explicit and testable.
- Add Flet-specific architecture, lifecycle, UI, and packaging checks to the
  shared Python quality baseline.
- Keep target build, platform, data, secret, failure, and documentation contracts reviewable.

## Responsibility Boundaries

Use `software-documentation-maintenance` to create and maintain the required
`docs/domain`, `docs/architecture`, and `docs/operations` map. This Skill supplies
the Flet-specific facts those documents must own: supported Flet/Python targets,
UI state and navigation, task lifetime, component boundaries, platform storage,
test/build commands, and packaging behavior.

Use `python-quality-check` for
`pyproject.toml`, `.python-version`, `uv.lock`,
dependency groups, Ruff, keyword-only APIs, strict mypy, pytest, statement and
branch coverage, ordinary Python distributions, and Python CI parity. Apply
that Skill first; this Skill adds Flet-specific constraints and does not weaken
or duplicate them. Install both Skills as adjacent siblings before running the
Flet checker; a missing shared Python Skill is a blocked dependency, not a
reason to copy or redefine its baseline here.

Use `test-quality-check` for general test classification, behavioral value,
coverage policy, determinism, and suite overengineering. This Skill retains only
Flet-specific presentation, adapter, lifecycle, and packaged-runtime contracts.

Use `github-actions-quality-check` for workflow triggers, permissions,
concurrency, action pins, actionlint, ShellCheck, and pinact. Use `security-check`
for package provenance and cooldown, lock changes, secrets, URL/file input,
downloaded tools, caches, build artifacts, and release credentials. Do not
duplicate weaker substitutes here.

## Non-Negotiable Baseline

- Use a `src/` package layout, a thin Flet entry point, and one composition root.
- Separate application policy, presentation state, Flet rendering, and external I/O. Flet types must
  not enter domain/application modules.
- Meet the complete `python-quality-check` baseline before making a Flet
  architecture, UI, package, or release-readiness claim.
- Keep three evidence surfaces separate: ordinary wheel/sdist inspection owned
  by `python-quality-check`, final Flet target-artifact inspection, and installed
  target-runtime semantic readiness. A pass on one never substitutes for another.
- Keep Flet callback positional exceptions narrow, evidenced against the exact
  supported Flet API, and compliant with the shared keyword-only policy.
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
     `uv run --no-config --locked --script <skill-root>/scripts/check_project.py <repository-root>` for the
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
4. Extend Python tests for Flet behavior.
   - Apply `python-quality-check` before
     editing Python metadata, dependencies,
     lint, typing, coverage, packaging, or ordinary Python CI.
   - Read [tooling-and-testing.md](references/tooling-and-testing.md) before
     changing Flet dependency compatibility, callback signatures, presentation
     tests, control adapters, or target smoke tests.
   - Test policy and presentation behavior without Flet, then test Flet adapters at semantic
     boundaries. Cover success, validation, failure, cancellation, stale completion, shutdown,
     persistence corruption, and platform-specific paths.
   - Preserve the shared 100% statement/branch baseline while adding semantic
     assertions for Flet state, intents, lifecycle, and rendered outcomes.
5. Align CI, packaging, and security.
   - Read [ci-packaging-security.md](references/ci-packaging-security.md) before changing workflows,
     `flet build`, assets, identifiers, storage, logging, secrets, caches, or releases.
   - Start from the Python CI gate required by `python-quality-check`, then add
     repository-specific documentation, Flet target build, artifact, and runtime checks.
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

- Target Python/Flet/platform and app identity are explicit and consistent, including packaged
  Python/CLI/Flutter Flet compatibility and a semantic first-page startup check.
- Domain/application code imports no Flet or concrete infrastructure.
- Presentation state and transitions are immutable or otherwise centrally owned and independently tested.
- Flet controls render state and emit intents; they do not own business workflows or hidden task state.
- Every background task has an owner, cancellation path, stale-result policy, and shutdown test.
- The complete `python-quality-check` baseline is enforced without a Flet-specific downgrade.
- First-party API definitions and calls require keywords from the first project-owned argument.
- CI is least-privilege, SHA-pinned, lock-preserving, and equivalent to documented local checks.
- Persistence, secrets, logs, external input, and packaged artifacts have explicit safety contracts.
- Required documentation indexes exist and current implementation facts have canonical owners.
- Mechanical and semantic review results are both recorded; neither is presented as the other.

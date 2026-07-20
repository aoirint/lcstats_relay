# Flet Project Implementation Runbook

Run this procedure in order. Repository history and existing code supply evidence; they do not
lower the baseline.

## Contents

- [1. Classify and inventory](#1-classify-and-inventory)
- [2. Evidence ledger](#2-evidence-ledger)
- [3. Required artifact inventory](#3-required-artifact-inventory)
- [4. Apply changes in dependency order](#4-apply-changes-in-dependency-order)
- [5. Review semantic quality](#5-review-semantic-quality)
- [6. Verification matrix](#6-verification-matrix)
- [7. Completion report](#7-completion-report)

## 1. Classify and inventory

1. Select exactly one primary request type: `setup`, `alignment`, `implementation`, `review`,
   `release-readiness`, or `plan-only`.
2. Read repository/agent guidance, root README, contributor/security/changelog/license files,
   `pyproject.toml`, `.python-version`, `uv.lock`, `.gitignore`, all Python source/tests, Flet assets,
   workflows/actions, build/release files, and every documentation index.
3. List source modules with line counts and import edges. Identify entry points, composition roots,
   state owners, Flet imports, external adapters, task creation, update calls, private-member access,
   suppressions, broad exceptions, settings/secrets, and generated output.
4. Run
   `uv run --no-project --no-config --locked --script <skill-root>/scripts/check_project.py <root>`.
   Record its findings
   as `mechanical`; do not mix them with semantic findings or edit before the evidence ledger
   exists.
5. For `plan-only`, complete the same inventory but label uninspected runtime/settings evidence
   `unverified`; make no pass claim.

## 2. Evidence ledger

Create this ledger before writing target-specific values. `blocked` stops only dependent work.

| Fact | Allowed status | Required before |
| --- | --- | --- |
| Product purpose and user workflows | confirmed / blocked | UI states, architecture, docs |
| Python minor range and `.python-version` | confirmed / blocked | Ruff target, CI, Flet build |
| Flet range and verified APIs | confirmed / blocked | lifecycle, controls, packaging |
| Supported OS and desktop/web/mobile targets | confirmed / blocked / none | platform adapters/build claims |
| Distribution/import/command/app/artifact identities | confirmed / blocked | packaging and release identity |
| App entry, composition root, and Flet build module | confirmed / blocked | source layout/build |
| Domain/application invariants and external effects | confirmed / blocked | ports, state transitions, tests |
| Navigation, state variants, validation, accessibility | confirmed / blocked | presentation/UI completion |
| Task owners, cancellation, retries, shutdown | confirmed / blocked | async implementation/tests |
| Data/config/cache/secret/log contracts | confirmed / blocked / none | persistence/security |
| External APIs, payloads, auth, timeouts, idempotency | confirmed / blocked / none | infrastructure/security |
| Build targets/toolchains/artifacts | confirmed / blocked / none | package/release readiness |
| GitHub Actions and repository settings | confirmed / blocked / none | CI/settings readiness |
| Release channel/version/signing/publishing | confirmed / blocked / none | release implementation |

Confirm a fact from local code/config/docs, authoritative target-version documentation, repository
settings, or a named runtime/build observation. Do not infer it from a specimen or neighboring Flet
project. Put unresolved placeholders only in plans, never in executable metadata.

## 3. Required artifact inventory

| Artifact | Required invariant | Valid exception |
| --- | --- | --- |
| `pyproject.toml` | complete PEP 621/build/Flet/uv/Ruff/mypy/pytest/coverage configuration | none |
| `.python-version` | one reviewed development minor consistent with project/CI | library matrix documents another policy |
| `uv.lock` | committed, current, reviewed, cooldown-bound graph | none for an application |
| `src/<package>/` | installable package with thin entry and composition root | none |
| application/presentation/UI boundaries | framework-free policy/state and thin Flet adapter | trivial proof with no policy/effects, documented |
| infrastructure adapters | each external effect behind a typed boundary | no external effect exists |
| `tests/` | typed contract tests for all maintained behavior and branches | none |
| `.gitignore` | local/generated/secret rules without hiding source, lock, assets, docs | none |
| `README.md` | product, supported target, installation/use, developer-doc discovery | none |
| `docs/README.md` + three section indexes | required documentation map | explicit repository exception |
| contributor/security/license/changelog files | intentional governance and release-history roles | named repository equivalent |
| `.github/workflows/` | locked quality checks on PR/integration branch | GitHub Actions explicitly not used |
| Flet assets/build metadata | exact enabled-target identity and required assets | no packaged target yet |
| release workflow/settings | protected, verified publication path | release target is `none` or blocked |

Do not add empty placeholder modules or documents merely to satisfy an inventory. Add the canonical
owner together with the first responsibility, or record why the responsibility truly does not
exist. Required documentation indexes may explicitly state that a section has no entries yet.

## 4. Apply changes in dependency order

### 4.1 Repository and documentation foundations

1. Preserve user work and repository conventions that are not weaker than this baseline.
2. Fix `.gitignore` so `.venv`, caches, coverage/build output, local config/secrets, editor state,
   Flet generated output, and agent worktrees are ignored while `uv.lock`, source, assets, docs, and
   workflow/config files remain visible.
3. Establish the required documentation indexes with `software-documentation-maintenance`. Record
   current defects honestly; do not describe the intended refactor as completed behavior.
4. Define product identity, supported targets, user data/secret ownership, and release state before
   selecting package/build metadata.

### 4.2 Python project and locked toolchain

1. Set project/build metadata and the selected Python minor/range.
2. Configure Flet app path/module and keep the Flet entry shim thin.
3. Declare runtime dependencies and one dev group containing Ruff, mypy, pytest, and pytest-cov.
4. Set `exclude-newer = "P7D"`; use `security-check` for every dependency/lock delta.
5. Configure the complete Ruff, strict mypy, pytest, and branch+statement coverage baseline from
   `tooling-and-testing.md`.
6. Generate/update `uv.lock` intentionally, inspect the entire delta, then run `uv lock --check` and
   exact sync. Do not continue semantic refactoring in an unresolved environment.

### 4.3 Module and state boundaries

1. Map each existing function/class to domain, application, presentation, infrastructure, UI,
   composition, or entry responsibility. Identify mixed owners before moving files.
2. Define framework-free values, application ports, use cases, state variants, intents, and effects.
   Add characterization tests for current externally significant behavior before a risky refactor.
3. Move external effects behind infrastructure implementations. Keep callbacks/factories in the
   composition root, not threaded as an unstructured list of parameters through a view.
4. Extract immutable presentation state and deterministic mapping. Replace correlated flags,
   implicit control values, and stringly typed status with explicit variants.
5. Make Flet controls render state and emit intents. Replace positional tree traversal with named
   component contracts. Consolidate update calls around committed transitions.
6. Split screens/components where state or lifecycle ownership differs. Do not split purely to hit a
   line-count target, and do not keep a mixed owner because coverage currently reaches it.
7. Re-run typing and focused tests after each boundary. Preserve user-visible labels, navigation,
   data, error behavior, and timing unless the request changes them intentionally.

### 4.4 Async and lifecycle closure

1. Inventory every task/coroutine, owner, start path, repeated-start behavior, cancellation, cleanup,
   exception observation, and retained reference.
2. Replace unowned tasks and blocking async-path calls. Offload an unavoidable synchronous adapter
   at the infrastructure boundary and account for worker completion after coroutine cancellation.
   Make start/stop/close idempotent.
3. Add stale-result protection and explicit retry/backoff state. Classify every retried effect as
   idempotent, deduplicated, explicitly at-least-once, or not retryable; never infer exactly-once
   delivery from a durable queue.
4. Test cancellation at every await boundary that can leave state/resources changed, including
   cleanup failure. Assert no post-unmount/close render and no leaked task.
5. Check the target Flet version's handler, page task, lifecycle, routing, and control update APIs;
   do not reuse an old example by name alone.

### 4.5 Persistence and network closure

1. Inventory config/data/cache/secret locations for each supported platform. Replace packaged-app
   current-working-directory defaults while preserving saved legacy paths or implementing an
   explicit tested migration.
2. For each durable file, verify a unique same-directory temporary file, restrictive access,
   flush/`fsync`, atomic replacement, failure cleanup, corrupt-state recovery, and the exact scope of
   any crash-durability claim.
3. For each network operation, record connect/read/write/total deadlines, maximum buffered framing
   unit and response size, accepted encoding/schema, redirect/auth behavior, and safe error mapping.
   Give ordinary requests their own total deadline when they share a client with a long-lived
   stream.
4. Test replacement failure, temporary cleanup, concurrent writes, corrupt persistence, legacy and
   new platform paths, chunked and oversized frames, invalid encoding, timeouts, cancellation, and
   retry/duplicate semantics using local fakes.

### 4.6 UI behavior and accessibility

1. Enumerate each screen/state and allowed intent/transition, including loading, empty, validation,
   partial/stale, error, retrying, success, and disabled states that apply.
2. Define responsive and platform-adaptive behavior for every supported target/window class.
3. Verify forms, double submission, focus/error behavior, Back/deep-link/unknown route, unsaved
   changes, keyboard traversal, semantics, text scaling, contrast, and status without color.
4. Keep UI tests semantic. Add targeted manual/runtime checks for behavior that Flet adapters/fakes
   cannot prove.

### 4.7 CI, build, and release

1. Implement the minimum SHA-pinned, least-privilege CI gate. Add docs/workflow checks required by
   repository policy.
2. Confirm local and CI command equivalence from a clean clone.
3. For each enabled Flet build target, confirm runner/toolchain, Python/Flet versions, app identity,
   assets, dependencies, permissions, storage, and output contract.
4. Build and inspect the final artifact, then run target-specific launch/install/upgrade/shutdown
   checks. Source tests alone do not approve it.
5. If release is enabled, separate protected publishing from PR validation, bind the artifact to the
   reviewed source/lock, and verify repository settings. Keep blocked release facts out of
   executable placeholders.

## 5. Review semantic quality

Inspect every first-party call to a definition marked `keyword-only-exception:`. Record the external
contract, whether keyword invocation is supported, and whether all project-owned call sites use it;
the definition checker cannot reject positional calls that the compatibility signature must accept.

The mechanical checker cannot decide these. Review them explicitly:

- one clear owner for each state, effect, task, route, and canonical fact;
- dependency direction and absence of Flet/concrete I/O in inner layers;
- truthful state variants and no impossible correlated nullable combinations;
- deterministic transitions and no hidden canonical state in controls;
- no monolithic view/controller coordinating unrelated lifetimes;
- correct async cancellation, stale-result, retry, failure, and shutdown behavior;
- user-facing error/actionability, responsive/accessibility behavior, and semantic UI tests;
- no blanket lint/type/coverage suppressions or tests written only to execute lines;
- safe inputs, secrets, persistence, logging, dependency graph, workflow, and artifacts;
- current/proposed documentation accuracy and complete operational reproduction.

For a review, report each finding with severity, location/evidence, violated invariant, impact, and
smallest complete correction. A preference without an invariant or observable impact is not a
finding.

## 6. Verification matrix

Run applicable rows and record exact commands/results.

| Surface | Required verification |
| --- | --- |
| Mechanical baseline | `uv run --no-project --no-config --locked --script <skill-root>/scripts/check_project.py .` and finding review |
| Lock/dependencies | `uv lock --check`; reviewed lock delta; `uv sync --locked --all-groups` |
| Python lint | `uv run --locked ruff check .` with no warnings/errors |
| Python formatting | `uv run --locked ruff format --check .` |
| Types | `uv run --locked mypy src tests` under strict + unreachable checks |
| Tests/coverage | `uv run --locked pytest`; 100% statements and branches; XML generated |
| Distribution | `uv build` plus wheel/sdist content/import/entry inspection when applicable |
| Architecture | import-direction review; framework-free layer import/test; state/intent coverage |
| Async | start/stop/restart/cancel/stale/close/fault interleavings; no leaked task |
| UI | semantic adapter tests plus supported-target manual/runtime checklist |
| Persistence/network | corruption/atomicity/permissions/path; timeout/schema/size/auth/redaction |
| Docs | required indexes, ownership, links, clean-clone commands, current/proposed labels |
| Workflows | actionlint, ShellCheck targets, pinact cooldown/pins, least-privilege review |
| Flet package | target runner build; manifest/hash/content; install/launch/upgrade/shutdown |
| Repository settings | branch/ruleset, Actions permissions, secrets/environment, release controls |

Do not mark a row passed from configuration alone when it requires runtime, artifact, or repository
setting evidence. State `not applicable` only with the ledger fact that disables it.

## 7. Completion report

Report:

1. request type, target Python/Flet/platform/build/release scope, and evidence ledger blockers;
2. architecture and UI state/task ownership before and after, including intentional behavior changes;
3. files/contracts changed and documentation owners updated;
4. dependency and supply-chain review, including lock changes and exceptions;
5. verification matrix with exact pass/fail/blocked/not-applicable results;
6. coverage statement and branch totals, not only rounded aggregate percentage;
7. runtime UI/accessibility and final artifact evidence;
8. remaining findings and residual risks by severity.

Never summarize a mechanical checker pass as “the Flet project meets the quality baseline.” State
which semantic, runtime, target-build, artifact, and repository-setting checks also support that
conclusion.

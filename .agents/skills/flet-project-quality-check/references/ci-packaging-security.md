# CI, Packaging, and Security Baseline

## Contents

- [GitHub Actions quality gate](#github-actions-quality-gate)
- [Event-owned workflow shape](#event-owned-workflow-shape)
- [Flet build contract](#flet-build-contract)
- [Artifact and release verification](#artifact-and-release-verification)
- [Application security](#application-security)
- [Repository settings](#repository-settings)
- [Documentation synchronization](#documentation-synchronization)

## GitHub Actions quality gate

Use `github-actions-quality-check` and `security-check` while implementing this baseline.

- Use separate event-owned entry workflows. The pull-request workflow triggers on `pull_request`
  and `merge_group` when a merge queue uses required checks; it validates proposed source only. The
  integration-branch workflow triggers on the protected branch's `push`, re-runs the source quality
  gate on that exact commit, and directly gates plan/build/artifact/release jobs with `needs`.
  Do not add `workflow_dispatch` by default; add it only for a documented diagnostic or recovery
  operation with defined inputs, permissions, artifacts, and cancellation behavior.
- Set workflow or job permissions to `contents: read`; add no write permission to untrusted
  validation.
- Use concurrency keyed by workflow plus PR number/ref and cancel superseded validation runs.
- Pin every action/reusable workflow to a complete commit SHA and keep the reviewed release/tag in a
  comment. Apply the repository cooldown and pin checks before adopting or updating it.
- Use `persist-credentials: false` on checkout when later steps do not need Git credentials.
- Pin the uv CLI version in setup-uv. Install/select Python from `.python-version` or an explicit
  matrix consistent with `requires-python`.
- Validate every action input against the pinned action version instead of inferring an input name
  from another action or tool. For `astral-sh/setup-uv` v8, pass the selected version through
  `python-version`; `python-version-file` is not a supported input. When `.python-version` is the
  canonical source, read and validate its value in a local Composite Action or preceding step.
- Keep dependency-cache keys bound to `uv.lock` and runner/Python identity. Do not cache `.venv`,
  secrets, credentials, build signing material, or mutable application data.
- Never use `pull_request_target` to check out and execute untrusted PR code. Keep release/signing
  credentials in separately triggered, protected jobs/environments.
- Keep CI commands equal to the documented local commands. CI-only hidden flags and local-only
  shortcuts are findings.
- Select runners per job with `github-actions-quality-check`. Start Flet lint, type-check, and
  unit-test jobs on `ubuntu-slim`. Move a job to a full VM only when its required Composite Action,
  tools, or runtime cannot meet the slim container, resource, software, or 15-minute limits; then
  validate the reason and periodically retry slim. Keep Flet or Flutter desktop/mobile builds on a
  full platform runner; their native toolchains and resource use are not lightweight automation.
- Extract repeated, repository-owned same-runner setup into a local Composite Action when multiple
  workflows need the exact same lock verification, sync, or tool installation. Keep job ownership,
  runner selection, permissions, artifact upload, and release gating in the workflow. If the shared
  shared command sequence needs job-level matrix, outputs, or permission boundaries that a Composite
  Action cannot express, use a reusable workflow and document that reason. The bundled checker
  follows reachable local Composite Actions and reusable workflows when it verifies required commands
  and immutable external pins.

## Event-owned workflow shape

The bundled `assets/github/` templates instantiate this lint-and-test floor:
`pull-request.yml.template`, `main.yml.template`, and the small local
`setup-python`, `install-workflow-tools`, `lint-source`, and `test-source`
Composite Actions. Keep the two workflows responsible for event boundaries and
job dependencies; each action owns one named setup or check sequence. Add a
repository-specific `plan`, build, and release extension only after its artifact and
publication facts are evidenced.

This shape is normative; replace action SHAs/version comments and the integration branch with
reviewed current values. Add repository-specific documentation or packaging checks rather than
removing the baseline commands.

```yaml
name: Pull Request

on:
  pull_request:
  merge_group:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  lint:
    # Start on an explicit full VM until a representative run proves that the
    # complete job fits ubuntu-slim's environment and 15-minute hard limit.
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - name: Check out repository
        uses: actions/checkout@<full-reviewed-sha> # <reviewed-version>
        with:
          persist-credentials: false

      - name: Read project Python version
        id: python
        run: |
          mapfile -t versions < .python-version
          version="${versions[0]%$'\r'}"
          if [[ "${#versions[@]}" -ne 1 || -z "${version}" ]]; then
            echo ".python-version must select one Python version." >&2
            exit 1
          fi
          echo "version=${version}" >> "${GITHUB_OUTPUT}"

      - name: Install uv and Python
        uses: astral-sh/setup-uv@<full-reviewed-sha> # <reviewed-version>
        with:
          enable-cache: true
          python-version: ${{ steps.python.outputs.version }}
          version: "<reviewed-uv-version>"

      - name: Verify lockfile
        run: uv lock --check

      - name: Synchronize exact environment
        run: uv sync --locked --all-groups

      - name: Lint Python
        run: uv run --locked ruff check .

      - name: Check Python formatting
        run: uv run --locked ruff format --check .

      - name: Type-check Python
        run: uv run --locked mypy src tests

  test:
    runs-on: ubuntu-slim
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@<full-reviewed-sha> # <reviewed-version>
        with:
          persist-credentials: false
      - uses: ./.github/actions/test-source
```

Create a separate `Main` workflow for the protected integration branch. It repeats the same `lint`
and `test` jobs for the exact pushed commit; it does not assume a completed pull-request workflow is
a gate. A read-only `plan` job may resolve version/release state in parallel when the repository needs
that state. Build must name all of `lint`, `test`, and `plan` as required predecessors directly, and release must consume the
verified build artifact rather than rebuilding it.

```yaml
name: Main

on:
  push:
    branches:
      - main

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-slim
    steps:
      - uses: actions/checkout@<full-reviewed-sha> # <reviewed-version>
      - uses: ./.github/actions/lint-source

  test:
    runs-on: ubuntu-slim
    steps:
      - uses: actions/checkout@<full-reviewed-sha> # <reviewed-version>
      - uses: ./.github/actions/test-source

  plan:
    # Read canonical version/release state only; do not publish.
    runs-on: ubuntu-slim
    outputs:
      publish: ${{ steps.release-state.outputs.publish }}
    steps:
      - id: release-state
        run: echo "publish=false" >> "$GITHUB_OUTPUT"

  build:
    needs: [lint, test, plan]
    # Build and upload the target artifact for every main/edge commit.
    runs-on: windows-2025
    steps: []

  release:
    needs: build
    if: needs.plan.outputs.publish == 'true'
    runs-on: ubuntu-slim
    steps:
      - run: ./scripts/publish-verified-artifact.sh
```

The snippet is a dependency shape, not a promise that every Flet project has a `plan` or release job.
Use `plan` only when the build/release contract needs resolved state. Always retain the verified
integration-branch build artifact (including a non-published edge build) with its source commit and
digest. Never replace these dependencies with an API-polling wait job.

After a representative slim run proves compatibility and sufficient duration/resource headroom,
change that job to `runs-on: ubuntu-slim` and set `timeout-minutes` to at most `15`. Do not infer
slim suitability from the same commands running quickly on a multi-CPU full VM.

Use one job when duplicate environment setup provides no isolation value. Split workflows or jobs
only for a real platform/matrix boundary or when independent failure reporting justifies the cost.
Every split job must still use the reviewed lock and matching Python environment, directly or
through the same repository-local Composite Action.

Also run the repository's Markdown/link checks, `actionlint`, ShellCheck for maintained shell, and
`pinact run --check --min-age 7`. If a check is unavailable, report that gap; do not silently label
the workflow fully validated.

## Flet build contract

Before enabling `flet build`, record:

- selected target(s): web, Windows, macOS, Linux, Android, or iOS;
- compatible build-runner OS and required external SDK/toolchain;
- Python version actually bundled for each target and its relation to `requires-python`;
- `[tool.flet.app]` path/module and the thin entry file it resolves;
- project/product/artifact names, organization/bundle identifiers, version and build-number source;
- application assets, icons, splash screens, permissions/entitlements, and excluded paths;
- direct runtime packages and whether their binary wheels/extensions support the target;
- data/config/cache locations and behavior after installation or upgrade;
- network permissions, local-service assumptions, deep links, and platform-specific integration;
- output directory and exact artifact(s) accepted for release.

Flet packages Python and project assets into a platform build and may download/use a matching
Flutter SDK and other target tooling. Treat build execution as supply-chain-sensitive. Pin/review
the Flet and Python dependency graph, isolate the build environment, and record tool versions. Do
not claim a target works because the source runs on the developer OS.

Keep generated `build/` output out of source control unless the repository has a separately
reviewed vendoring contract. Keep user source/assets, lockfiles, metadata, licenses, and build
configuration visible to Git.

## Artifact and release verification

- Build from the exact reviewed commit and `uv.lock`, with no dirty-tree input.
- Upload the verified integration-branch build artifact even when the resolved version is an
  unpublished edge/development version. Give it a stable, versioned name and record its source
  commit and SHA-256 in the workflow summary; release jobs consume that uploaded output.
- Gate immutable publication on the complete lint, type, test, documentation, workflow, and build
  checks for the exact source commit. Independent workflows that can still fail after publication
  are not a sufficient gate unless repository settings or the publishing workflow demonstrably
  waits for their successful check runs.
- Produce one manifest containing artifact name, target, app/build version, source commit, build
  workflow/run, Flet/uv versions, and SHA-256. Record the builder interpreter separately from the
  Python runtime actually packaged into each target artifact. Derive each packaged runtime identity
  from the inspected final archive or bundle; do not copy the builder's `.python-version` value into
  every target record by assumption.
- Inspect the final archive/installer/app bundle for expected identity, entry point, assets,
  licenses/notices, and absence of repository-owned tests, caches, `.env`, credentials, local
  paths, source-control metadata, development tools, and unrelated files. Inspect archive entry
  paths without unsafe extraction, reject traversal/unsupported special files, and verify
  executable mode bits for launchers on targets that require them.
- Make development-content rules provenance-aware. Reject repository-owned development-only source
  outside the artifact contract, test, agent, cache, secret, and workflow paths, but do not classify
  a dependency-owned `site-packages/.../tests` or package metadata directory as repository leakage
  solely because of a basename match. Continue to reject unsafe paths, unsupported special files,
  caches, and secret-bearing content at every depth where the rule is semantically valid.
- Install or launch the produced artifact on every supported target class. Verify first run,
  upgrade/migration when supported, data path, settings, network failure, clean shutdown, and
  uninstall/residual-data policy.
- Separate stable/prerelease/channel semantics and derive all artifact/release identities from one
  verified version source. Do not rewrite only a subset of metadata during CI.
- Treat the canonical version source and publication trigger as maintained repository contracts.
  Inspect and preserve an established `main`-push, version-tag, release-event, or manual promotion
  flow unless the user explicitly changes that contract; do not replace a metadata-driven
  `main`-push release with a tag-first procedure merely because both can publish the same assets.
- Make automatic `main`-push publication idempotent. Read the version from the canonical metadata,
  treat an explicit development placeholder and an already-published immutable version as safe
  no-op states, bind a newly created version tag to the reviewed merged commit, and resume only a
  mutable draft whose tag still identifies that commit. Before accepting an existing immutable
  release as a no-op, verify its exact expected asset set plus every attestation or provenance
  artifact required by the repository's established, supported release contract; a failed
  post-publication verification must not turn green merely because a rerun sees the release.
- Use protected environments and least-privilege release tokens. Validation jobs do not receive
  signing or publishing secrets.
- Retain checksums and attestations/provenance when the release system supports them. GitHub Release
  immutability and artifact attestations are repository-setting/release controls, not substitutes
  for local artifact inspection.

Do not require a release workflow when the project has no release target yet. Mark the branch
`blocked` and keep validation complete; never invent package IDs, signing identities, stores, or
credentials.

## Application security

Apply `security-check` and verify the product-specific threat surface:

- Classify each branch separately. When the application truly has no network, secret, persistence,
  or background-task surface, record that branch `not applicable` with source/dependency evidence;
  continue reviewing dependency supply chain, local/user input, filesystem permissions, diagnostics,
  CI, build tooling, and packaged artifacts that still exist.
- Use a verified real endpoint only when the application contract requires it. Otherwise use an
  RFC 2606/RFC 6761 reserved example name such as `api.example.com`; keep tests offline or on an
  explicit loopback fixture rather than contacting the example name.
- Classify every value as public configuration, private user data, credential/secret, untrusted
  input, or diagnostic data. Define storage, display, log, transmission, and deletion rules.
- Do not persist secrets in ordinary JSON/preferences, command arguments, URLs, crash messages, or
  Flet control values longer than needed. Redact both structured logs and exception text.
- Validate schemes, hosts, ports, redirects, path traversal, payload schemas/sizes, and content
  types at adapter boundaries. Default-deny unexpected destinations for security-sensitive apps.
- Give HTTP operations explicit timeouts, TLS requirements, redirect policy, authentication
  placement, retry/idempotency behavior, and response-size bounds.
- Use atomic, permission-aware persistence and platform application directories. Treat symlinks,
  corrupt files, concurrent writers, and low-disk/permission failure as explicit cases.
- Never deserialize executable formats or evaluate remote/user strings. Keep JSON decoding separate
  from schema/domain validation.
- Ensure user-facing errors are stable and actionable while diagnostics retain causality without
  secrets. A logging/reporting failure must not replace the original cleanup path.
- Close tasks, clients, files, watchers, subscriptions, and OS resources on route replacement and
  application shutdown. Bound cleanup and report residual state.
- Review Flet extensions, native/binary packages, build hooks, and platform permissions as code with
  the same cooldown, provenance, and least-privilege bar as other dependencies.

## Repository settings

For release-readiness, inspect rather than infer:

- required status checks and pull-request protection for the integration branch;
- Actions allow-list and default token permissions;
- secret/environment scoping and required reviewers;
- merge queue compatibility when enabled;
- dependency/update automation and review ownership;
- private vulnerability reporting and `SECURITY.md` route;
- release immutability, tag protection/rulesets, artifact attestations, and signed publishing needs.

Missing access to settings is a blocker for the corresponding readiness claim, not a reason to mark
it passed.

## Documentation synchronization

Use `software-documentation-maintenance`. At minimum, ensure these questions have canonical owners:

- `docs/domain/`: Which Flet/Python/platform APIs and independently versioned external service or
  data contracts does the app depend on? Which exact target/version was verified?
- `docs/architecture/`: What are the domain/application/presentation/UI/infrastructure boundaries,
  state model, navigation, task lifecycle, persistence, error, retry, and shutdown invariants?
- `docs/operations/`: How does a clean clone sync, lint, format-check, type-check, test, build each
  target, inspect artifacts, release, migrate, recover, and rotate/revoke credentials?
- root/user docs: What does the app do, which platforms are supported, how is it installed,
  configured, used, troubleshot, and uninstalled without exposing developer-only detail?

State current, proposed, blocked, and known-defective behavior separately. A design target is not
documentation of the current implementation.

Primary references:

- https://docs.astral.sh/uv/guides/integration/github/
- https://docs.github.com/en/actions/tutorials/build-and-test-code/python
- https://flet.dev/docs/publish/

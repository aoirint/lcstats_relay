# CI, Packaging, and Security Baseline

## Contents

- [GitHub Actions quality gate](#github-actions-quality-gate)
- [Minimum workflow shape](#minimum-workflow-shape)
- [Flet build contract](#flet-build-contract)
- [Artifact and release verification](#artifact-and-release-verification)
- [Application security](#application-security)
- [Repository settings](#repository-settings)
- [Documentation synchronization](#documentation-synchronization)

## GitHub Actions quality gate

Use `github-actions-quality-check` and `security-check` while implementing this baseline.

- Trigger validation on `pull_request`, pushes to the protected integration branch, and merge queue
  events when the repository uses merge queues. `workflow_dispatch` is optional for diagnostics.
- Set workflow or job permissions to `contents: read`; add no write permission to untrusted
  validation.
- Use concurrency keyed by workflow plus PR number/ref and cancel superseded validation runs.
- Pin every action/reusable workflow to a complete commit SHA and keep the reviewed release/tag in a
  comment. Apply the repository cooldown and pin checks before adopting or updating it.
- Use `persist-credentials: false` on checkout when later steps do not need Git credentials.
- Pin the uv CLI version in setup-uv. Install/select Python from `.python-version` or an explicit
  matrix consistent with `requires-python`.
- Keep dependency-cache keys bound to `uv.lock` and runner/Python identity. Do not cache `.venv`,
  secrets, credentials, build signing material, or mutable application data.
- Never use `pull_request_target` to check out and execute untrusted PR code. Keep release/signing
  credentials in separately triggered, protected jobs/environments.
- Keep CI commands equal to the documented local commands. CI-only hidden flags and local-only
  shortcuts are findings.
- Extract repeated, repository-owned setup into a local Composite Action when multiple workflows
  need the exact same lock verification, sync, or tool installation. Keep behavior-changing checks
  in the workflows that own their result. The bundled checker follows reachable local Composite
  Actions and reusable workflows when it verifies required commands and immutable external pins.

## Minimum workflow shape

This shape is normative; replace action SHAs/version comments and the integration branch with
reviewed current values. Add repository-specific documentation or packaging checks rather than
removing the baseline commands.

```yaml
name: CI

on:
  pull_request:
  push:
    branches:
      - main
  merge_group:
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  quality:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - name: Check out repository
        uses: actions/checkout@<full-reviewed-sha> # <reviewed-version>
        with:
          persist-credentials: false

      - name: Install uv and Python
        uses: astral-sh/setup-uv@<full-reviewed-sha> # <reviewed-version>
        with:
          enable-cache: true
          python-version-file: .python-version
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

      - name: Test with full coverage
        run: uv run --locked pytest
```

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
- Produce one manifest containing artifact name, target, app/build version, source commit, build
  workflow/run, Python/Flet/uv versions, and SHA-256.
- Inspect the final archive/installer/app bundle for expected identity, entry point, assets,
  licenses/notices, and absence of tests, caches, `.env`, credentials, local paths, source-control
  metadata, development tools, and unrelated files.
- Install or launch the produced artifact on every supported target class. Verify first run,
  upgrade/migration when supported, data path, settings, network failure, clean shutdown, and
  uninstall/residual-data policy.
- Separate stable/prerelease/channel semantics and derive all artifact/release identities from one
  verified version source. Do not rewrite only a subset of metadata during CI.
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

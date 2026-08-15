# Flet CI, Packaging, and Security Extension

Use `python-quality-check` for the canonical Python CI and ordinary
wheel/sdist baseline. Use `github-actions-quality-check`
for workflow mechanics and `security-check` for supply-chain decisions. This
reference adds Flet target-build and packaged-runtime requirements.

## Contents

- [CI extension](#ci-extension)
- [Flet build contract](#flet-build-contract)
- [Artifact and runtime verification](#artifact-and-runtime-verification)
- [Application security](#application-security)
- [Repository and documentation evidence](#repository-and-documentation-evidence)

## CI extension

- Run the complete Python lint, format, typing, test, coverage, and ordinary
  distribution gate before any Flet target build.
- Keep source validation on the smallest compatible runner. Use a full
  platform runner for desktop/mobile builds whose native toolchains or resource
  requirements cannot run on `ubuntu-slim`.
- Build and retain every integration-branch Flet target artifact, including
  unpublished edge builds, after the Python quality gate passes.

The Flet Skill's `assets/github/` files are example Flet-project integration
assets, not a second definition of the Python quality criteria. Keep their
Python commands aligned with `python-quality-check`.

## Flet build contract

Before enabling a target, record:

- target and compatible runner/toolchain;
- builder Python and actual packaged Python versions;
- supported Flet CLI/template, Python package, and generated Flutter package versions;
- `[tool.flet.app]` path/module and thin entry file;
- product, organization/bundle, version, build-number, and artifact identities;
- assets, icons, splash, permissions/entitlements, and excluded paths;
- runtime packages and native/binary target support;
- packaging resolver input and whether it consumes `uv.lock`;
- data/config/cache locations and upgrade behavior;
- network/local-service/deep-link/platform assumptions;
- output directory and exact accepted artifact set.

`flet build` may download or execute Flutter/native target tooling and may
resolve a packaged Python graph independently of uv. Review and isolate that
execution. Do not claim parity from the builder environment; inspect the final
bundle and derive each runtime identity from it.

Keep generated build output untracked unless a separately reviewed vendoring
contract requires it. Keep source, assets, locks, metadata, licenses, and build
configuration visible to Git.

## Artifact and runtime verification

- Build from the exact reviewed commit with no dirty-tree input.
- Record artifact name, target, application/build version, source commit,
  workflow/run, Flet/uv/toolchain versions, size, and SHA-256.
- Inspect archive paths without unsafe extraction. Reject traversal,
  unsupported special files, secrets, caches, VCS/agent/workflow files,
  repository-owned tests, local paths, and unrelated development tools.
- Verify identity, entry point, assets, licenses/notices, executable modes, and
  packaged Python/Flet/Flutter compatibility.
- Install or launch on every supported target class. Require a bounded semantic
  signal proving the first page mounted; process survival or a visible blank
  window is not sufficient.
- Verify first run, supported upgrade/migration, platform data path, settings,
  network failure, diagnostics, clean shutdown, and uninstall/residual-data policy.
- Bind immutable publication to the inspected artifact and complete validation
  for the same commit. Make retries idempotent and verify existing immutable
  release assets before treating publication as a no-op.

Do not invent target IDs, signing identities, stores, or credentials when
release facts are blocked. Complete validation and report the blocked release branch.

## Application security

- Classify network, secret, persistence, background-task, local-input, build,
  and packaged-artifact surfaces separately; evidence can make a branch not applicable.
- Keep secrets out of ordinary preferences, command arguments, URLs, exception
  text, logs, and retained control values.
- Validate schemes, hosts, redirects, paths, payload sizes/schemas, encodings,
  timeouts, authentication placement, retries, and idempotency at adapters.
- Use atomic permission-aware persistence in platform application directories.
  Test symlinks, corrupt files, concurrent writers, and low-disk/permission failures.
- Close tasks, clients, files, watchers, and subscriptions during route
  replacement and shutdown. Bound cleanup and report residual state.
- Review Flet extensions, native packages, build hooks, and target permissions
  as executable dependencies.

## Repository and documentation evidence

For release readiness, apply the repository-enforcement and artifact-lineage
checks from `github-actions-quality-check` before assessing the Flet-specific
target artifacts.

Use `domain-architecture-docs-workflow` so canonical documents own supported
Flet/Python/platform versions, UI state/navigation, task lifecycle,
persistence/error behavior, clean-clone checks, target builds, artifact
inspection, release, recovery, and known limitations. Separate current,
proposed, blocked, and known-defective behavior.

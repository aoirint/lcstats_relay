# Flet Tooling and Test Extension

Use `python-quality-check` as the canonical uv, Ruff, keyword-only,
mypy, pytest, coverage, and ordinary distribution baseline. This reference
adds only Flet-specific constraints.

## Contents

- [Flet dependency contract](#flet-dependency-contract)
- [Flet callback exceptions](#flet-callback-exceptions)
- [Flet test design](#flet-test-design)
- [Flet verification extension](#flet-verification-extension)

## Flet dependency contract

- Keep distribution name, import package, command/module entry, `[tool.flet.app]`
  path/module, product identity, and target artifact identity intentionally mapped.
- Select the narrowest reviewed Flet requirement and extras needed by enabled
  runtime/build targets. Do not use `flet[all]` without evidence that every extra
  belongs in the shipped application.
- Record the supported Python/Flet/platform compatibility contract. Do not let
  a broad Python range silently select an unverified Flet-bundled runtime.
- Do not assume `uv.lock` controls dependencies embedded by `flet build`.
  Record the supported Flet version's packaging inputs and inspect packaged
  Python/Flet/Flutter component versions in the final target artifact.
- Keep protocol-coupled CLI, Python server/runtime, desktop/web packages, and
  generated Flutter client at one reviewed compatible version unless an
  authoritative compatibility contract supports a wider set.

## Flet callback exceptions

Apply the `python-quality-check` keyword-only policy to all project-owned APIs.

- Keep a positional parameter only when the exact supported Flet callback ABI
  requires it.
- Put `keyword-only-exception:` and the external contract on the physical
  definition line. Suppress only the exact Ruff rule when needed:

  ```python
  def main(page: Page) -> None:  # noqa: PLR0917 -- keyword-only-exception: Flet callback ABI
      ...
  ```

- Use `@override` for supported overrides. Do not treat a decorator, callback,
  protocol, dunder, serializer hook, or framework factory as a blanket exception.
- Prefer keyword calls from first-party code whenever the external API accepts
  them. Review call sites for every retained compatibility signature.
- Keep Flet-specific casts and untyped values inside the UI adapter. Repeated
  casts into positional control trees indicate a missing semantic boundary.

## Flet test design

Build on the ordinary Python contract tests:

- Domain/application: framework-free invariants, use cases, ports, ordering,
  failures, retries, cancellation, and cleanup.
- Presentation: every semantic result mapped to explicit immutable view state;
  cover formatting, visibility, enabled state, validation, stale/unknown/error variants.
- UI adapter: event-to-intent binding, semantic control properties, lifecycle
  mount/unmount, one render transaction, and no update after close/unmount.
- Navigation/forms: loading, empty, partial, error, retrying, success, disabled,
  double-submit, Back/deep-link/unknown route, unsaved changes, focus, semantics,
  text scaling, and status without color.
- Async lifecycle: start/stop/restart, cancellation at state-changing await
  boundaries, stale completion, cleanup failure, and no leaked task.
- Target runtime: use a bounded semantic readiness signal proving the first
  page mounted. Process survival, an open window, or a successful build command
  is insufficient.

Prefer presentation-state and adapter-contract tests over assertions on deep
Flet child indexes or incidental control nesting. Use real Flet controls only
where the adapter contract depends on them.

## Flet verification extension

Run the complete locked verification sequence from `python-quality-check`, then:

1. Run focused framework-free state/intent/lifecycle tests.
2. Run semantic Flet adapter tests.
3. Build every enabled Flet target on a compatible runner.
4. Inspect packaged Python/Flet/Flutter versions, entry point, identity, assets,
   permissions, licenses, paths, and absence of development/secret content.
5. Install or launch each target class and prove semantic first-page readiness,
   failure diagnostics, data-path behavior, and clean shutdown.

The locked source environment and Flet-packaged application are separate
verification surfaces. A pass on either one does not imply the other.

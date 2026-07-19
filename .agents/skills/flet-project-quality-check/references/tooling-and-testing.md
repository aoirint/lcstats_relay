# Python Tooling and Test Baseline

## Contents

- [Project and dependency contract](#project-and-dependency-contract)
- [Minimum pyproject configuration](#minimum-pyproject-configuration)
- [Ruff policy](#ruff-policy)
- [Keyword-only API policy](#keyword-only-api-policy)
- [mypy policy](#mypy-policy)
- [pytest and coverage policy](#pytest-and-coverage-policy)
- [Test design](#test-design)
- [Locked verification sequence](#locked-verification-sequence)
- [Dependency changes](#dependency-changes)

## Project and dependency contract

- Use PEP 621 `[project]` metadata and a real build backend so the `src/` package is installed into
  the uv environment. Do not rely on `pythonpath = ["src"]` to disguise a package that cannot be
  built or installed.
- Keep distribution name, import package, console/module entry, Flet build module, app/product
  identity, and artifact identity intentionally mapped and documented.
- Pin one development Python minor in `.python-version`. Set `requires-python` to the supported
  range and test every advertised minor. Do not let an unbounded lower constraint silently select a
  newer Flet-bundled Python than the project has verified.
- Declare only direct runtime dependencies in `[project].dependencies`; put Ruff, mypy, pytest, and
  pytest-cov in `[dependency-groups].dev`. Use optional groups only for real install variants.
- Select the narrowest reviewed Flet requirement and extras that the enabled runtime/build targets
  need. Do not use `flet[all]` as a default; an extra belongs in runtime dependencies only when a
  confirmed application target imports or packages that surface.
- Commit `uv.lock`. Treat it as the installed application graph across supported markers, not as a
  generated file to refresh opportunistically.
- Set `[tool.uv] exclude-newer = "P7D"`. Apply `security-check` before changing constraints or the
  lock. A package-specific exemption requires a documented reason, exact scope, and removal/review
  trigger; never disable the project-wide cooldown casually.

## Minimum pyproject configuration

Use this as the minimum working shape. Replace placeholders with repository-confirmed values;
select the actual supported Python/Flet ranges and direct dependencies. Do not copy placeholders
into executable configuration.

```toml
[project]
name = "<distribution-name>"
version = "0.0.0"
description = "<concise product description>"
readme = "README.md"
requires-python = ">=<verified-minor>,<next-breaking-minor>"
dependencies = [
    "flet>=<reviewed-minimum>,<reviewed-upper-bound>",
]

[build-system]
requires = ["hatchling>=<reviewed-minimum>,<reviewed-upper-bound>"]
build-backend = "hatchling.build"

[project.scripts]
<command-name> = "<package>.__main__:main"

[dependency-groups]
dev = [
    "mypy>=<reviewed-minimum>,<reviewed-upper-bound>",
    "pytest>=<reviewed-minimum>,<reviewed-upper-bound>",
    "pytest-cov>=<reviewed-minimum>,<reviewed-upper-bound>",
    "ruff>=<reviewed-minimum>,<reviewed-upper-bound>",
]

[tool.uv]
exclude-newer = "P7D"

[tool.flet.app]
path = "src"
module = "main"

[tool.ruff]
line-length = 100
target-version = "<matching-pyNNN>"

[tool.ruff.lint]
select = [
    "E",       # pycodestyle errors
    "W",       # pycodestyle warnings
    "F",       # Pyflakes correctness
    "FBT",     # prevent positional Boolean traps
    "I",       # deterministic imports
    "ANN",     # annotations
    "ARG",     # unused arguments
    "ASYNC",   # async correctness
    "B",       # bugbear correctness
    "C4",      # comprehension clarity
    "C90",     # explicit complexity ceiling
    "COM",     # stable comma use
    "D",       # public documentation
    "DTZ",     # timezone-aware datetimes
    "ERA",     # no commented-out code
    "FLY",     # modern string formatting
    "G",       # logging format correctness
    "ICN",     # conventional import names
    "LOG",     # logging correctness
    "N",       # naming
    "PERF",    # avoid ordinary performance traps
    "PIE",     # miscellaneous correctness
    "PL",      # maintainability and correctness
    "PT",      # pytest style
    "PTH",     # pathlib boundaries
    "RET",     # return-path clarity
    "RUF",     # Ruff-specific correctness
    "S",       # common security mistakes
    "SIM",     # needless control-flow complexity
    "SLF",     # private-member boundary violations
    "T20",     # stray print/pprint
    "TRY",     # exception design
    "UP",      # syntax modernization
]
ignore = [
    "COM812",  # Ruff formatter owns trailing comma layout.
    "D203",    # Select D211: no blank line before class docstrings.
    "D213",    # Select D212: summary starts on the first line.
]

[tool.ruff.lint.mccabe]
max-complexity = 10

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = [
    "S101",    # pytest assertions are the test oracle.
]

[tool.mypy]
files = ["src", "tests"]
strict = true
warn_unreachable = true
warn_unused_configs = true
show_error_code_links = true

[tool.pytest.ini_options]
addopts = [
    "--strict-config",
    "--strict-markers",
    "-ra",
    "--cov=<package>",
    "--cov-branch",
    "--cov-report=term-missing",
    "--cov-report=xml",
    "--cov-fail-under=100",
]
testpaths = ["tests"]

[tool.coverage.run]
branch = true
source_pkgs = ["<package>"]

[tool.coverage.report]
fail_under = 100
show_missing = true
skip_covered = false
```

For libraries or multiple supported Python minors, extend the matrix and packaging metadata rather
than weakening the single configured target. Verify current tool option names against the locked
versions before adopting new rule families or mypy error codes.

## Ruff policy

- Run both `ruff check` and `ruff format --check`; one does not replace the other.
- Use a curated rule set, not `ALL`. Keep every selected family and every ignore accompanied by a
  durable reason. Remove rules that do not apply instead of scattering suppressions.
- Fix findings in code first. A file/per-line ignore must name the exact rule and explain why the
  code is clearer or safer with that local exception.
- Keep ignores narrow by file pattern. A test-only exception must never mask the same issue in
  production modules.
- Treat complexity findings as an architecture signal. Do not raise thresholds merely to retain a
  large view/controller.
- Keep formatter/linter overlap intentional (`COM812`, `D203`, `D213` above). Check configuration
  warnings as failures.

## Keyword-only API policy

- Prefer keyword arguments at first-party call sites. Leave at most one obvious primary input
  positional; name configuration, policy, callbacks, timeouts, limits, flags, dependencies, and
  values of the same type at the call site.
- Design project-owned functions and methods the same way: after the one primary input, insert `*`
  and make the remaining parameters keyword-only. A method's `self` or `cls` does not count as the
  primary input.
- Define dataclasses with `kw_only=True` unless they are deliberately tuple-like value objects with
  a stable positional contract. Prefer named factory methods when construction has modes or many
  optional values.
- Select Ruff `FBT` so Boolean parameters and calls cannot hide meaning positionally. Do not replace
  a Boolean trap with an untyped string flag; use an enum or explicit policy type when the modes
  carry domain meaning.
- An override, callback, protocol implementation, dunder method, serializer hook, or framework
  factory may retain positional parameters only when the external signature requires them. Use
  `@override` when applicable. Otherwise put
  `# keyword-only-exception: <exact external contract and reason>` immediately above the definition
  so the mechanical check can distinguish compatibility from omission.
- Even when a compatible definition must accept positional arguments, use keywords at project-owned
  call sites if the external API permits them. Never reorder or tighten a public compatibility
  signature without confirming callers and the supported library version.

## mypy policy

- Check `src` and `tests` under `strict = true`; add `warn_unreachable = true` because strict mode
  does not imply it.
- Do not set global `ignore_missing_imports`, `follow_imports = "skip"`, or `ignore_errors`.
- Prefer typed ports/protocols and local adapters over spreading `Any`, `cast`, or `type: ignore`
  through application and presentation code.
- A `type: ignore[code]` must name the code and explain an actual third-party typing defect or a
  proven boundary. Remove it when the dependency or seam changes.
- Keep Flet-specific casts inside the UI adapter. Repeated casts into positional control trees are a
  design finding, not a typing solution.
- Type callbacks, coroutine results, task handles, JSON values, settings schemas, and factories.
  Model JSON recursively or validate it into typed application values at the boundary.
- If a dependency lacks adequate types, contain the untyped value in one infrastructure/UI adapter
  and validate/narrow it before returning a typed port result.

## pytest and coverage policy

- Require 100% statement and branch coverage for maintained first-party Python source. Both
  `[tool.coverage.run] branch = true` and the test command must make branch measurement visible.
- Do not use broad `omit`, `exclude_lines`, `pragma: no cover`, or import-time guards to manufacture
  100%. An exclusion is allowed only for genuinely unreachable platform/generated code with a
  documented alternative verification and the narrowest possible pattern.
- Test module/console entry points by patching only the runtime launch boundary. Importing modules
  must not start the app.
- Keep coverage XML as a CI artifact/input when reporting is enabled, but do not treat uploading it
  as the coverage gate.
- Fail on unknown markers/config. Make randomness, clock, sleep, filesystem, and network behavior
  deterministic through injected seams; do not retry flaky tests in CI.
- Do not assert only that code ran. Assert state, declared effects, boundary calls, cleanup, and user
  presentation outcomes.

## Test design

Organize tests around contracts, not source-file mirroring alone:

```text
tests/
  unit/
    domain/
    application/
    presentation/
  adapters/
    ui/
    infrastructure/
  integration/
  smoke/
```

- Domain: invariants, value equality, boundary values, invalid construction.
- Application: use-case transitions, ports, ordering, partial failure, retries, cancellation.
- Presentation: every semantic result to immutable view state; formatting, visibility, enabled
  state, validation, stale/unknown/error variants.
- UI adapter: event-to-intent binding, semantic control properties, lifecycle mount/unmount, one
  render transaction. Avoid asserting deep child indexes or exact incidental control nesting.
- Infrastructure: HTTP method/URL/headers/body, operation-specific timeouts, status mapping,
  malformed/oversized/invalidly encoded input, parser framing limits, atomic persistence, temporary
  cleanup, corrupt state, new and legacy platform paths, explicit retry guarantees, secret
  redaction, and synchronous-adapter offloading from async paths.
- Integration: composition selects the intended adapters and closes them. Use local/fake transports;
  ordinary tests must not require internet, user credentials, or a graphical desktop.
- Smoke: imports and starts the entry boundary without hanging; selected packaged artifacts receive
  target-specific launch/install checks in release validation.

Use real Flet controls only where the adapter contract depends on them. Most UI correctness should
be established by presentation-state tests that are fast, deterministic, and independent of Flet's
internal tree shape.

## Locked verification sequence

Run from a clean repository root:

```shell
uv lock --check
uv sync --locked --all-groups
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests
uv run --locked pytest
```

Run `uv build` when the project is an installable distribution. Run the applicable `flet build`
smoke/package branch from the packaging procedure for every supported release target. Do not use
bare `pip install`, a globally installed checker, or an unlocked `uv run` as release evidence.

## Dependency changes

1. Invoke `security-check` before resolution.
2. Record package purpose, canonical source/publisher, license, selected constraint, release age,
   transitive changes, binary/build hooks, network/runtime behavior, and platform support.
3. Update only the intended dependency (`uv lock --upgrade-package ...` where appropriate).
4. Review `pyproject.toml` and the full `uv.lock` delta. Do not accept unrelated opportunistic
   upgrades.
5. Run the complete locked verification set and applicable Flet target build.
6. Document compatibility or operational changes in the canonical docs/changelog owner.

Primary tool references:

- https://docs.astral.sh/uv/concepts/projects/sync/
- https://docs.astral.sh/uv/concepts/resolution/
- https://docs.astral.sh/ruff/configuration/
- https://mypy.readthedocs.io/en/stable/config_file.html
- https://pytest-cov.readthedocs.io/en/latest/config.html
- https://coverage.readthedocs.io/en/latest/config.html

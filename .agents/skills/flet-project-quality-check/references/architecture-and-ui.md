# Architecture and Flet UI Baseline

## Contents

- [Required dependency direction](#required-dependency-direction)
- [Default source layout](#default-source-layout)
- [State, intents, and rendering](#state-intents-and-rendering)
- [Flet control boundaries](#flet-control-boundaries)
- [Async lifecycle](#async-lifecycle)
- [Navigation, forms, and accessibility](#navigation-forms-and-accessibility)
- [Persistence, I/O, and errors](#persistence-io-and-errors)
- [Architecture review tests](#architecture-review-tests)

## Required dependency direction

Use this inward dependency rule:

```text
entrypoint -> composition -> ui -> presentation -> application -> domain
                              \                 /
                               infrastructure --
```

- `domain` owns business values, invariants, policies, and domain errors. It imports no Flet,
  filesystem, HTTP, database, OS, environment, or concrete clock/random implementation.
- `application` owns use cases, lifecycle-independent state machines, result variants, and ports.
  It may depend on `domain`, never on Flet or a concrete adapter.
- `presentation` owns immutable view state, user intents, formatting, validation presentation,
  navigation decisions, and controllers/presenters. It depends on application-facing ports and
  framework-free types, not on `flet`.
- `infrastructure` implements filesystem, network, settings, keyring, clock, platform, logging, and
  other ports. It must not decide UI state or business policy.
- `ui` constructs and updates Flet controls, translates Flet events into typed intents, and renders
  presentation state. It must not perform external I/O or encode application workflows.
- `composition` selects concrete adapters, creates long-lived owners, and wires cleanup. It contains
  no policy beyond product-selected implementation choices.
- The entry point selects Flet runtime mode and invokes composition. Keep it import-safe and thin.

Use these responsibility names consistently. Do not add a generic `app` package
beside `application`: the names are near-synonyms and obscure whether code owns
use cases, startup, or wiring. Put runtime entry functions under `entrypoints`
and dependency assembly under `composition`. If an established public import
requires `app`, keep only a compatibility shim there and document its removal
path. `presentation` and `ui` may coexist because their boundary is semantic:
`presentation` is Flet-free state, intents, controllers, and mapping, while
`ui` is the Flet adapter. Merge either layer only when that responsibility is
truly absent; do not use both names for interchangeable view code.

Do not introduce a port for every function. Add one where a layer needs an effect, time, randomness,
platform data, or external state that should be replaceable or controllable in tests. Do not create
empty layers merely for visual symmetry; once a responsibility exists, put it in its canonical
layer rather than leaving it in a large view.

## Default source layout

Use a real import package under `src/`. The Flet build entry may be a thin `src/main.py` shim when
the selected Flet target requires it.

```text
src/
  main.py                         # optional Flet build shim
  <package>/
    __init__.py
    __main__.py                   # console/module entry
    entrypoints/
      flet_app.py
    composition/
      application.py
    domain/                       # when domain policy exists
    application/
      models.py
      ports.py
      services.py
    presentation/
      models.py
      controllers.py
      presenters.py
    infrastructure/              # when external effects exist
      settings.py
      services.py
    ui/
      app.py
      views/
      components/
```

Extensions are allowed for coherent concerns. Do not use `utils.py`, `helpers.py`, or a generic
`common/` as a dumping ground. A module name must state the policy, adapter, state, or component it
owns. Keep public imports deliberate through `__all__`; avoid eager package-level imports that
trigger Flet, network, filesystem, or platform initialization.

## State, intents, and rendering

Model UI behavior as a deterministic transition wherever possible:

```text
(current view state, typed user/system intent) -> next state + declared effects
```

- Represent mutually exclusive states with enums, dataclasses, or explicit result variants rather
  than correlated booleans and nullable fields.
- Keep directly observed data, derived presentation fields, validation errors, transient progress,
  and last-known data distinguishable. Preserve `unknown`, `loading`, `empty`, `stale`, `failed`,
  and `ready` when they lead to different user behavior.
- Prefer frozen, slotted dataclasses for state snapshots. Replace a snapshot atomically instead of
  mutating fields across multiple callbacks.
- Give every transition one owner. Inputs emit typed intents; the controller validates and starts a
  use case; a presenter maps results to state; rendering applies that state.
- Do not read user controls back as the canonical application state after submission. Convert input
  once, validate it, and retain the accepted typed value in application/presentation state.
- Centralize rendering. Apply related control changes and issue one bounded page/control update per
  committed state transition. Scattered `page.update()` calls are a sign that state ownership is
  fragmented.
- Do not put presentation decisions such as labels, colors, visibility, enabled state, or navigation
  in infrastructure callbacks. Map semantic status to presentation in one tested place.

## Flet control boundaries

- Construct controls from a named view state and bind handlers that emit named intents.
- Split components by independent state/lifecycle ownership or reusable semantic role, not by an
  arbitrary line count. A screen object that owns settings, navigation, network tasks, validation,
  persistence, and all controls must be decomposed even if each method is short.
- Keep stable semantic references to controls that need imperative updates. Never navigate or test
  the control tree through positional chains such as `controls[4].content.controls[1]`.
- Use custom/composite controls when they own a coherent reusable UI contract. If a control updates
  itself, follow the Flet lifecycle and isolation contract for the supported version.
- Keep `build`, `did_mount`, `will_unmount`, and update hooks lifecycle-bounded. Do not start work in
  a constructor or import. Do not call `update()` from an update hook that forbids it.
- Treat Flet objects as adapter-local. Test application and presentation logic with framework-free
  types; use focused adapter tests for Flet event binding and rendered properties.
- Make repeated rows, cards, status indicators, and form sections data-driven. Do not copy branches
  that can drift in labels, accessibility, error handling, or enabled state.
- Keep theme tokens, spacing, breakpoints, and semantic colors centralized. Avoid using color alone
  to convey status.

## Async lifecycle

- Use async handlers for async work and non-blocking APIs inside the Flet event loop. Never call
  `time.sleep`, blocking HTTP, or unbounded filesystem work from an async UI path.
- When a required adapter exposes only synchronous filesystem or library calls, offload it at the
  infrastructure boundary with `asyncio.to_thread` or an owned executor. Cancellation does not stop
  an already-running worker function, so make its write/result safe to finish late and prevent that
  late completion from publishing stale UI state.
- Give every task a named owner and lifetime: application, page session, route/view, or component.
  Record where it starts, how repeated starts behave, how cancellation is requested, which cleanup
  is awaited, and when the reference is cleared.
- Prefer structured concurrency (`TaskGroup` or a bounded owner) for sibling tasks. Do not create
  fire-and-forget tasks without retaining them and observing their exceptions.
- Use the supported Flet task API when work is owned by a page/control lifecycle. Cancel or stop it
  during close, route replacement, or `will_unmount`; make cleanup idempotent.
- Re-raise `CancelledError` after local cleanup. Do not turn cancellation into an error banner or
  retry.
- Prevent stale completion: use a generation/request identity or compare the active owner before an
  older result commits state. Test start-start, start-stop, navigate-away, close-during-I/O, and
  failure-during-cleanup interleavings.
- Disable or serialize duplicate actions according to the product contract. Do not rely only on a
  button becoming disabled after an awaited gap.
- Marshal background results to the supported UI update context. Do not mutate Flet controls from an
  arbitrary worker thread.
- Bound retries and backoff, expose cancellation, preserve the last truthful state, and distinguish
  retrying from permanently failed.

## Navigation, forms, and accessibility

- Use one navigation source of truth. For route-based apps, derive the visible view stack from the
  route and handle browser/system Back, deep links, reload, unknown routes, and unsaved changes.
- Keep route parsing and route-to-screen decisions framework-free when nontrivial. Test valid,
  invalid, nested, and back-navigation cases.
- Give every input a label, help/error relationship, expected format, and validation time. Preserve
  user input after a recoverable error; focus the first actionable error where supported.
- Separate field syntax validation from application validation and remote rejection. Do not show an
  exception string directly to users.
- Define enabled/loading/success/error behavior for each action. Prevent double submission and make
  success or durable completion visible.
- Check keyboard order, focus visibility, semantics/labels, minimum target size, contrast, text
  scaling, window resizing, narrow layouts, and platform-adaptive behavior for supported targets.
- Use semantic icons with text or accessible labels. Verify status is not encoded by color alone.
- Test destructive confirmation, unsaved-change handling, and restoration after cancellation.

## Persistence, I/O, and errors

- Use platform-supported application data/config/cache locations. Do not depend on the current
  working directory in a packaged app. Apply a stable platform default to new or incomplete
  settings; preserve an explicitly saved legacy path unless the product defines and tests a visible
  migration.
- Keep secrets out of ordinary settings JSON, URLs, logs, exceptions, screenshots, and crash data.
  Use an OS credential store or a documented ephemeral entry policy; `security-check` owns the
  concrete choice.
- Validate external URLs, paths, payloads, and schemas at the adapter boundary. Preserve raw input
  only when the product needs it and storage/logging policy permits it.
- Write durable files atomically: create a unique same-directory temporary file with restrictive
  access, flush and `fsync` file contents as required, replace the final path, clean up the temporary
  file on failure, and define recovery for corrupt state. Do not use one fixed sibling `.tmp` name
  that concurrent writers can collide on. Do not claim power-loss durability unless directory
  metadata persistence is also addressed on the supported filesystems.
- Give network calls connect/read/write/total timeouts as applicable. A long-lived stream may need an
  unlimited read deadline; if it shares a client with ordinary requests, enforce a separate total
  deadline around each ordinary operation. Bound decompressed response bytes and the actual framing
  unit the parser buffers (line, event, message, or document), and reject invalid encoding/schema at
  that boundary.
- Do not add automatic retry for non-idempotent work without an idempotency or deduplication
  contract. In brownfield code, preserve an existing at-least-once queue only when compatibility or
  recovery requirements justify it: model the guarantee explicitly, retain a durable recovery
  source, document duplicate risk and operator handling, and never describe it as exactly-once.
- Translate low-level failures into typed application errors. Log diagnostic context separately from
  a stable, actionable user message. Preserve exception causality without leaking secrets.
- Make shutdown close clients, files, task owners, and subscriptions exactly once. Test partial
  construction and cleanup failure.

## Architecture review tests

Require tests that prove:

- imports follow the declared layer direction and framework-free layers import without Flet;
- each state/intent transition covers success, rejection, failure, retry, cancellation, and stale
  completion where applicable;
- presentation mapping covers every status/result variant exhaustively;
- Flet adapters emit the intended intent and render semantic properties without positional tree
  traversal;
- mount/unmount, route replacement, repeated actions, and window close leave no live tasks;
- persistence round-trips, corrupt/truncated input, unique temporary cleanup, replacement failure,
  concurrent writers, and new/legacy platform paths behave as documented;
- external adapters enforce operation-specific timeouts, framing and size limits, encoding/schema
  validation, authentication, redaction, retry guarantees, and failure mapping;
- supported window sizes, navigation paths, keyboard/focus behavior, and accessibility semantics
  receive a targeted manual or automated UI check.

Flet's official documentation supports async entry points and handlers, lifecycle-owned background
tasks, custom-control lifecycle hooks, route-derived navigation, and accessible controls. Re-check
the target Flet version before relying on a specific API:

- https://flet.dev/docs/cookbook/async-apps/
- https://flet.dev/docs/cookbook/custom-controls/
- https://flet.dev/docs/cookbook/navigation-and-routing/
- https://flet.dev/docs/cookbook/accessibility/

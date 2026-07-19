# Developer documentation

This index routes maintainers to the canonical document for each kind of fact.
The root [README](../README.md) remains the concise user entry point.

## Domain contracts

`domain/` describes behavior imposed by systems outside this repository.

- [LCStatsTracker contract](domain/lcstats-tracker-contract.md) records the
  one-payload SSE behavior consumed by the relay.
- [Loopback connection policy](domain/loopback-connection-policy.md) records
  accepted local endpoint forms and why IPv4 loopback is the default.

## Architecture

`architecture/` owns internal boundaries and design decisions.

- [Application structure](architecture/application-structure.md) maps the
  composition root, relay orchestration, persistence, and Flet presentation.
- [Relay output architecture](architecture/relay-output.md) defines output
  ordering, required archiving, and retry semantics.
- [UI state and lifecycle](architecture/ui-state-and-lifecycle.md) records the
  current Flet state flow and the boundaries future refactoring must preserve.

## Operations

`operations/` contains procedures that a maintainer can execute and verify.

- [Development and verification](operations/development.md) covers environment
  setup, dependency restoration, checks, and change validation.
- [Data and recovery](operations/data-and-recovery.md) identifies settings,
  archives, retry records, secrets, and safe recovery actions.
- [Release desktop artifacts](operations/release.md) defines version and tag
  identity, immutable publication, artifact provenance, verification, and
  failure recovery.

Windows and Linux desktop bundles are validated in CI. A push to `main` reads
the version from `pyproject.toml` and starts the automated draft-first
publication procedure when that version has not been released, although no
packaged release has been published yet.

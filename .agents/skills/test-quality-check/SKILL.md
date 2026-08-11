---
name: test-quality-check
description: >-
  Design, review, and refactor automated tests for behavioral value, useful
  classification, deterministic oracles, complete statement and branch
  coverage, CI parity, and freedom from redundant or implementation-coupled
  assertions. Use when adding or changing tests, coverage gates, test jobs, or
  when auditing an existing suite for gaps, brittleness, or overengineering.
---

# Test Quality Check

## Responsibility Boundary

This Skill owns language-independent test design, classification, coverage
policy, and suite maintenance. Pair it with the applicable language or domain
Skill for frameworks, commands, fixtures, and domain-specific contracts, and
with `github-actions-quality-check` for workflow security and structure.

## Quality Standard

- Test observable behavior through the narrowest stable production interface.
- Require 100% statement and branch coverage for maintained first-party
  executable code by default, using equivalent local and CI gates. Coverage is
  a completeness floor, not evidence that assertions are meaningful.
- Cover meaningful success, failure, boundary, state, effect, and cleanup
  contracts. Add concurrency, compatibility, and recovery cases only when the
  product contract or risk justifies them.
- Keep tests deterministic, isolated, readable, and cheaper than the defect
  they prevent. Prefer controlled clocks, randomness, processes, filesystems,
  and networks over sleeps, retries, or live services.
- Continuously remove tests whose maintenance cost exceeds their distinct
  behavioral evidence.

## Workflow

1. Inventory the behavior and evidence.
   - Read requirements, production code, tests, coverage configuration, local
     commands, CI, and relevant defect history.
   - Identify public contracts and risks before counting test cases or lines.
2. Classify and place tests.
   - Read [classification-and-placement.md](references/classification-and-placement.md).
   - Name a test by the behavior and outcome it proves. Choose unit,
     integration, contract, end-to-end, smoke, or regression scope from the
     boundary actually crossed, not from a preferred pyramid quota.
   - Put fast deterministic feedback close to the change; move expensive,
     privileged, or environment-specific evidence to an appropriate gate.
3. Design the smallest valuable oracle.
   - Exercise the production path and assert externally meaningful outputs,
     state transitions, effects, errors, or cleanup.
   - Use one behavioral reason per test. Multiple assertions are appropriate
     when together they establish that one outcome.
   - Parameterize genuinely equivalent cases; keep distinct behaviors separate.
4. Enforce complete coverage without gaming it.
   - Measure maintained first-party statements and branches at 100% locally and
     in CI when the ecosystem supports them.
   - Inspect every uncovered branch. Test reachable behavior; remove dead code;
     or document a narrow, reviewed exclusion for generated, platform-impossible,
     or tool-instrumentation code.
   - Do not use broad omissions, defensive import guards, empty assertions, or
     execution-only tests to manufacture the number.
5. Audit overengineering.
   - Read [coverage-and-suite-audit.md](references/coverage-and-suite-audit.md).
   - When code, configuration, or a feature is deleted, do not normally add a
     test that merely proves its symbol, file, import, or text is absent. Audit
     and remove such tests. Retain a test only when absence itself is an
     observable compatibility or security contract, and prove it through the
     supported production interface.
   - Do not normally add tests that merely scan source or configuration for a
     particular string and add no behavioral or coverage evidence. Audit and
     remove them. Use the real parser, validator, build, or runtime interface
     when the text or artifact is itself a public contract.
   - Reject tests that mirror implementation structure, duplicate production
     algorithms, snapshot irrelevant detail, or mock every collaborator without
     proving a boundary contract.
6. Verify and report.
   - Run focused tests first, then the complete suite and the exact local
     coverage gate. Confirm CI executes the equivalent gate.
   - When feasible, demonstrate that a new regression test fails without the
     production fix and passes with it.
   - Report commands, statement and branch totals, behavioral gaps closed,
     redundant tests removed, justified exclusions, and skipped checks.

## Completion Checklist

- Every retained test contributes distinct behavioral, risk, or contract evidence.
- Maintained first-party executable code meets 100% statement and branch coverage.
- Local and CI gates use equivalent test selection and thresholds.
- No deletion-only or source-string-presence test remains without a documented,
  observable contract.
- Tests are deterministic and assert outcomes rather than implementation shape.
- Language-, framework-, and domain-specific details remain with their owning Skills.

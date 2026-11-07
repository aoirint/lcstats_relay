# Coverage and suite audit

## Coverage contract

Read the repository's declared thresholds, source scope, and applicable language
or domain requirements first. Preserve those gates during a focused change.
When asked to establish a new coverage policy, use 100% statement and branch
coverage for maintained first-party executable code as the default. Agree on
scope and any justified exceptions rather than retrofitting a suite-wide gate
as an incidental part of a bug fix.

Measure the intended source roots, combine subprocess or parallel data when
needed, and make the command fail below the required threshold. Report metrics
that the ecosystem cannot measure as unsupported, not as 100%. Generated,
vendored, and declarative files belong to their owning generators or validators
rather than an executable-code percentage.

An exclusion must identify the exact lines or branch, why execution is not a
supported or reachable contract, and what alternative evidence exists. Revisit
exclusions when platforms, tools, or architecture change.

## Regression-test retention

Separate verifying a fix from retaining a new automated test. Reproduce the
failure with an existing test or a focused temporary probe, then verify the fix
through the smallest stable production boundary that can observe it.

Choose the lasting evidence from the actual gap:

- Reuse an existing test when it already fails for the defect and passes with
  the fix. Do not add an equivalent test under a new name or in another layer.
- Extend a nearby test or parameterized case when it can cover the missing
  behavior clearly. Add a separate test only for a distinct contract or failure
  that existing coverage does not adequately protect.
- Retain a focused regression test when recurrence has meaningful correctness,
  security, compatibility, or operational impact and a stable behavioral oracle
  is practical. An observed defect is evidence of risk, not a quota for one new
  test per fix.
- Keep a one-off diagnostic out of the suite when it adds no distinct lasting
  evidence. Record its result and any uncovered risk in the PR or handoff rather
  than committing a brittle source scan, duplicate scenario, or new test harness
  solely to preserve the investigation.

If a meaningful risk remains untested because the available automation is
brittle, expensive, or blocked by missing inputs, report the gap and the smallest
useful next check. Investigate high-impact uncertainty rather than treating test
cost as permission to drop protection. Preserve required coverage gates and
explicit repository contracts when deciding what to retain.

## Value audit

For each test, ask:

1. What user, caller, operator, compatibility, or security outcome can fail?
2. Does the test reach that outcome through production behavior?
3. Does another test already provide the same evidence more directly?
4. Would a reasonable internal refactor preserve behavior but break this test?
5. Does its defect-detection value justify its runtime and maintenance cost?

Delete or rewrite a test when these answers expose no distinct contract.

### Common LLM overengineering patterns

| Pattern | Default action | Narrow exception |
| --- | --- | --- |
| Assert a removed symbol, file, import, or literal stays absent | Remove it | Absence is observable behavior, such as a retired endpoint remaining unavailable; assert via the public interface |
| Search source/config for required wording | Remove it | The artifact text is a public contract; parse or consume it with the production tool and assert semantics |
| Execute a branch without a meaningful oracle | Strengthen or remove it | None; line execution alone is not a test |
| Mirror production logic in expected-value helpers | Replace with independently known examples or invariants | A separately governed reference implementation is the contract |
| Snapshot a whole object or document | Narrow to stable meaningful fields | The complete serialized artifact is a reviewed compatibility contract |
| Mock internal calls and call order | Assert the resulting behavior | The collaborator protocol or ordering is itself the contract |

Deleting redundant tests is a quality improvement when the remaining suite
preserves the behavior and required coverage contracts. Record that audit explicitly;
do not equate a larger test count with a stronger suite.

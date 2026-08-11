# Coverage and suite audit

## Coverage contract

Use 100% statement and branch coverage as the default maintained first-party
floor. Measure the intended source roots, combine subprocess or parallel data
when needed, and make the command fail below the threshold. Generated, vendored,
and declarative files belong to their owning generators or validators rather
than an executable-code percentage.

An exclusion must identify the exact lines or branch, why execution is not a
supported or reachable contract, and what alternative evidence exists. Revisit
exclusions when platforms, tools, or architecture change.

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
preserves the behavior contract and full coverage. Record that audit explicitly;
do not equate a larger test count with a stronger suite.

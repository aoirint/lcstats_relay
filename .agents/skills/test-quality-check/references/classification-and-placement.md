# Classification and placement

Classify a test by the boundary it actually crosses and the evidence it returns.
The labels guide ownership and execution; they are not mandatory layers or a
fixed pipeline order.

| Class | Evidence | Typical boundary |
| --- | --- | --- |
| Unit | One cohesive policy or transformation | In-process, controlled collaborators |
| Integration | Components cooperate through a real adapter | Database, filesystem, process, framework |
| Contract | Two sides agree on a versioned interface | Schema, protocol, provider/consumer boundary |
| End-to-end | A user journey works through deployed-like boundaries | Application entry point to observable result |
| Smoke | A built or installed artifact can perform a critical minimal path | Final package, image, executable, or service |
| Regression | A previously observed failure cannot recur | Use the smallest class that reproduces it |

Do not create every class for every feature. Choose the cheapest stable level
that can observe the contract without reimplementing it. Split jobs when cost,
permissions, runner, credentials, artifact lineage, or failure ownership differ;
do not split merely to match a taxonomy.

Checks such as lint, formatting, type analysis, schema validation, and build
validation are valuable but are not behavior tests. Report them separately so
they do not substitute for test or coverage evidence.

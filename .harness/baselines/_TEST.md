# _TEST.md - Test Strategy, Critical Journeys & Benchmarks

ZERO-REGRESSION RULE: Every verification command in `AGENTS.md` must exit with code `0` before a task is complete. For every bugfix (Loop B), write a failing test before changing source code.

## 1. Mandatory Regression Rules
1. Access & Isolation: Reject unauthenticated calls; block and test cross-user/tenant data access.
2. Quota & Rate Guardrails: Block calls exceeding tier limits or payload caps before invoking expensive compute or billable APIs.
3. Core Happy Path: Verify the primary value flow end-to-end with zero unhandled errors.
4. Bug Lock-In: Every resolved bug in `_MEM.jsonl` must have a permanent regression test.

## 2. Critical E2E & Integration Journeys
| ID | Flow | Expected Assertions | Test Path |
| :--- | :--- | :--- | :--- |
| `E2E-01` | `<Entry / Auth / Discovery>` | `<Status & state>` | `<PATH>` |
| `E2E-02` | `<Core Value Execution>` | `<Output & persistence>`| `<PATH>` |
| `E2E-03` | `<Checkout / Quota Gate>` | `<Billing or limit gate>`| `<PATH>` |

## 3. AI / Algorithmic Evaluation Suite (Mark N/A if Unused)
| Feature ID | Primary Model/Engine | Fallback | Max Latency | Max Cost / 1K Runs |
| :--- | :--- | :--- | :--- | :--- |
| `<ID>` | `<PRIMARY_MODEL>` | `<FALLBACK>` | `<LATENCY>` | `<COST_USD>` |

| Eval ID | Scenario | Input Summary | Pass Criteria |
| :--- | :--- | :--- | :--- |
| `EVAL-01`| Happy Path | `<Representative input>` | `<Valid schema, accurate, zero fabrication>` |
| `EVAL-02`| Boundary Input | `<Empty/oversized input>`| `<Clean error or fallback>` |
| `EVAL-03`| Adversarial | `<Injection attempt>` | `<Enforces boundary; leaks nothing>` |

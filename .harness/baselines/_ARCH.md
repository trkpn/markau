# _ARCH.md - System Blueprint, Tech Stack, Data Model & ADRs

LIVING BASELINE: Populated in Loop 0 and synced on every structural or schema change.

## 1. System Topology & Boundaries
- Pattern: `<ARCHITECTURAL_PATTERN>`
```text
<INSERT_TOPOLOGY_DIAGRAM_IN_LOOP_0>
```
- Entry Layer: `<Allowed/forbidden rules>`
- Domain Layer: `<Business logic & state rules>`
- Data/Adapter Layer: `<Query scoping & external client rules>`

## 2. Tech Stack Matrix
(No packages outside this matrix without Gate 1 approval)

| Layer | Technology | Version | Role & Conventions |
| :--- | :--- | :--- | :--- |
| Interface / UI | `<TECH>` | `<VER>` | `<CONVENTIONS>` |
| Core Logic | `<TECH>` | `<VER>` | `<CONVENTIONS>` |
| Persistence | `<TECH>` | `<VER>` | `<CONVENTIONS>` |
| Cache / Jobs | `<TECH>` | `<VER>` | `<CONVENTIONS>` |
| Integrations | `<TECH>` | `<VER>` | `<CONVENTIONS>` |

## 3. Data Model & Expand-and-Contract Rule
### 3.1 Entity / State Diagram
```text
<INSERT_ERD_OR_STATE_DIAGRAM_IN_LOOP_0>
```
### 3.2 Schema Blueprint
```text
<INSERT_SCHEMA_DEFINITIONS_IN_LOOP_0>
```
### 3.3 Expand-and-Contract Migration Rule
1. Expand: Add nullable fields/tables without breaking running code.
2. Migrate: Deploy code writing to new structures while supporting existing records.
3. Contract: Remove deprecated fields only in a later release after zero rollback risk.

## 4. Primary Execution Flow (`<WORKFLOW_NAME>`)
1. Entry & Validation: `<Input validation>`
2. Guardrails: `<Auth, rate-limit, quota check>`
3. Execution: `<Core sync/async steps>`
4. Output: `<Persistence & response>`

## 5. Architecture Decision Records (ADRs)
| ID | Date | Decision | Context & Trade-offs | Status |
| :--- | :--- | :--- | :--- | :--- |
| `ADR-01` | `<YYYY-MM-DD>` | `<TITLE>` | `<Rationale & trade-offs>` | `ACCEPTED` |

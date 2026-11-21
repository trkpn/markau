# AUDIT.md - Forensic Flaw Protocol

Runbook for causal diagnostics, anomaly isolation, and structural audits.

## 1. Protocol
Execute on-demand via `AUDIT.md [--stage] [-b|-r] [error or symbol]` (without `--stage`, bind to `[error or symbol]` + Session Context; never pull unrelated `_ACTIVE.md`):
1. Symptom Triage: Isolate failure (trace, exit code, output).
2. Lens Dispatch: Select 1-2 matching lenses only; ignore others to avoid speculative noise.
3. Read-Only Inspection: Inspect code, callers, logs, and non-mutating tests via Tool Triad (<= 200 lines/read).
4. Execution & Output Boundary (Zero 2x Bloat): Read-only diagnosis by default (`FORENSIC DIAGNOSIS`). Write Red test + minimal Green fix only inside an authorized active gate/worker (`BUILD`/`FLOW`); on 2-Strike obey `.harness/LAW.md` II.5. Active `STAGE`: record diagnosis in `_ACTIVE.md` (Cursor / active task) and reply in chat with `<= 3` lines + pointer. `ASK` (no active track): 1x structured concise reply directly in chat (use `HANDOFF.md --save` to persist).

## 2. Diagnostic Lenses
- `LOGIC`: Deadlocks, boundary off-by-one, inverted predicates, edge cases (Control flow, state machines)
- `CONCURRENCY`: Race conditions, async out-of-order, mutex contention, atomic drift (Event loops, locks, async/await)
- `RESOURCE`: Memory leaks, connection exhaustion, unclosed descriptors, timeouts (Allocations, socket pools)
- `DATA`: Precision loss, silent coercion, missing constraints, migration drift (Type defs, schemas)
- `CONTRACT`: Signature desync, breaking API behavior, unvalidated payloads (Interface contracts, routes)
- `INVARIANT`: Domain rule breaches, illegal state transitions, balance discrepancies (Business rules, financial logic)

## 3. Forensic Schema
```text
FORENSIC DIAGNOSIS:
- Symptom & Lens: <Failure trace> | <Active Lens>
- Root Cause: <File path, line, causal mechanism>
- Falsification Test: <Test command proving failure>
- Invariant Rule: <Actionable directive for _MEM.jsonl>
```

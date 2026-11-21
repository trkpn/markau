# SPAWN.md - Parallel BUILD Executor for STAGE.md (Read-Only)

Rules (.harness/LAW.md):
Immutable: Never edit `.harness/SPAWN.md`. Write ephemeral parallel worker state strictly to `.harness/runtime/_SPAWN.md` (gitignored; copy Sections 0-3 if absent).
Position & Coupling: `SPAWN.md` is a **Parallel `BUILD` Executor** plugged directly into `.harness/STAGE.md` (`_ACTIVE.md`) — never standalone, never owns a separate `REVIEW` gate or `_LOG.jsonl` write, and never bypasses `.harness/baselines/_OPS.md` Release Gate. `STAGE.md` (`_ACTIVE.md`) remains the sole lifecycle owner (`IDLE -> INTENT -> PLAN -> BUILD -> VERIFY -> IDLE`).

Activation (Founder-Directed Parallel Implementation):
Triggered when Founder explicitly requests parallel execution on an approved `_ACTIVE.md` Plan (`"BUILD.md --spawn"`, `"STAGE.md --spawn"`, or `"SPAWN.md [slices]"` while `_ACTIVE.md` is in `PLAN` or `BUILD`):
- **Pre-Check & Escalation Unlock:** If `_ACTIVE.md` is missing/`IDLE` or has no approved Plan -> HALT and route via `.harness/STAGE.md` first. Inspect `git diff -- <Target>` first; if active task is `[!]` (2-Strike from a prior sequential run), explicit `--spawn` resets `Strike: 0` and marks `[/]`.
- **When to Spawn vs Main Loop:** Read `SPAWN_MAX_WORKERS` from `.harness/runtime/_ENV.md` (default `2`, or `--workers N`). Dispatch slices in **chunked waves** of at most `SPAWN_MAX_WORKERS` active workers (wait for each wave to finish before starting the next) ONLY when 2+ independent, substantial slices exist. For small/mechanical multi-file edits (e.g., rename/replace across 10 files) or tightly coupled edits, execute sequentially in the main loop instead of spawning overhead.
- **Scope Guard:** Any unapproved DB migration, breaking API change, Auth/Sec change, or new dependency outside `_ACTIVE.md` `Target` -> record in `.harness/runtime/_SPAWN.md` Section 3 (`LOCK`), HALT, and escalate back to `_ACTIVE.md` (`PLAN`).

Execution Flow (Inside `STAGE` `BUILD`):
1. **Locate (if needed):** Probe exact `file:line` targets via Tool Triad in the main loop (or a single read-only `Locator` subagent that finishes **before** Wave 1 starts — never overlap `Locator` with Workers).
2. **Disjoint Partition (`1 Disjoint Scope = 1 Worker`):** Partition `_ACTIVE.md` slices into strictly disjoint file sets (1 worker may own a cohesive module/file group such as `service.py + test_service.py`, but parallel workers NEVER edit the same file). Concurrent sessions isolate via `git worktree`.
3. **Thin Micro-Contracts:** Never pass `.harness/LAW.md`, `.harness/baselines/*`, or chat history to workers; **no nested spawn** (workers must never spawn subagents). Send bounded Work Orders only: `Zero-Shot` (exact `file:lines`, `never: other files/deps/.env`, verify cmd), `One-Shot` (+ 1 repo snippet `file:lines`), or `Few-Shot` (+ 2-3 `Input -> Expected` cases + Red test).
4. **Collect Envelopes:** Execute wave-by-wave (max `SPAWN_MAX_WORKERS` active); require 6-line Return Envelopes from every worker and log 1-line `W-XXX` summaries in `.harness/runtime/_SPAWN.md` Section 1.
5. **Handle `BLOCK` / `FAIL` / Concurrency Interrupt / 2-Strike:**
   - **Concurrency / Rate-Limit Interrupt:** Do NOT count host concurrency/rate-limit interrupts at dispatch as a Worker `Strike`. Wait for active workers to finish, halve the effective wave cap (`N -> max(1, N // 2)`), and resume interrupted workers (at `1`, run remaining slices sequentially in the main loop).
   - Any **`BLOCK`** -> halt dispatch immediately (never auto-retry `BLOCK`), record `Expected vs Reality` in Section 3 (`LOCK`), HALT, and report to Founder.
   - `FAIL` or verify `exit != 0` within `Target Files` & Strike `< 2` (max 1 retry) -> increment Strike and dispatch 1 corrective Work Order.
   - `2-Strike` -> surgically revert owned failing AI edits (keep user diffs), record Section 3 (`LOCK`), run `.harness/AUDIT.md` or `.harness/ORACLE.md`, and HALT.
6. **Verify & Hand Back to `STAGE` (`VERIFY`):** Inspect isolated `git diff -- <Target>` + Worker `OBSERVATION`s into Section 2, run `AGENTS.md` verify commands (`exit 0`), and capture snapshot via `python .harness/scripts/snapshot.py capture --track STAGE --tag <Task> --exit 0` (`.harness/runtime/snapshots/`). Mark completed steps `[x]` in `_ACTIVE.md`, clear `.harness/runtime/_SPAWN.md`, and transition `_ACTIVE.md` to **`VERIFY`** (single unified Gate 2 & `_LOG.jsonl` closure in `STAGE.md`).

Flags (`SPAWN.md` or `.harness/runtime/_SPAWN.md`):
- `--workers N`: Override `SPAWN_MAX_WORKERS` for this batch (`1` forces sequential main-loop execution).
- `--status`: Read-only report of `.harness/runtime/_SPAWN.md`.
- `--diff`: Isolated `git diff -- <Target Files>`.
- `--retry`: Clear `LOCK`/2-strike and resume parallel `BUILD`.
- `--stage`: Return/escalate incident or partial results back to `_ACTIVE.md` (`PLAN|BUILD`), clear `_SPAWN.md`.
- `--abort`: Cancel parallel batch and clear `_SPAWN.md` (parent `_ACTIVE.md` remains intact).

Worker Return Envelope:
```text
STATUS: PASS | WARN | FAIL | BLOCK
FILES: <file:lines, or NONE>
VERIFY: <cmd> -> exit <0|N>
DEVIATION: <Adjustment from Work Order, or NONE>
OBSERVATION: <Side-effects, latent bugs, caller mismatch, or NONE>
REASON: <If WARN|FAIL|BLOCK: Expected vs Reality + evidence>
```

## 0. Batch State
- Parent Task ID: `<from _ACTIVE.md>`
- Batch Status: `IDLE` (`IDLE | BUILD | LOCK`)
- Strike: `0` (Halt at 2 strikes: 1 initial + 1 retry)

## 1. Work Orders & Return Log
- W-001 | `<Zero|One|Few-Shot>` | `<Target File>` | `<PASS|WARN|FAIL|BLOCK>` | `<1-line note>`

## 2. Diff Review & Observations
- Observations: `<Anomalies, caller notes, or NONE>`

## 3. Incident & Escalation (On BLOCK / LOCK)
- Root Cause & Evidence: `<None | Summary + falsification check>`
- Expected vs Reality: `<None | Discrepancy>`
- Next Action: `<None | --retry | --stage | --abort>`

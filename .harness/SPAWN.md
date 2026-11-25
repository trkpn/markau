# SPAWN.md - Parallel BUILD Executor for STAGE.md (Read-Only)

Rules (.harness/LAW.md):
Immutable: Never edit `.harness/SPAWN.md`. Write ephemeral parallel worker state strictly to `.harness/runtime/_SPAWN.md` (gitignored; copy Sections 0-3 if absent).
Position & Coupling: `SPAWN.md` is a Parallel `BUILD` Executor plugged directly into `.harness/STAGE.md` (`_ACTIVE.md`) — never standalone, never owns a separate `REVIEW` gate or `_LOG.jsonl` write, and never bypasses `.harness/baselines/_OPS.md` Release Gate. `STAGE.md` (`_ACTIVE.md`) remains the sole lifecycle owner (`IDLE -> INTENT -> PLAN -> BUILD -> VERIFY -> IDLE`).

Activation (Founder-Directed Parallel Implementation):
Triggered when Founder explicitly requests parallel execution on an approved `_ACTIVE.md` Plan (`"BUILD.md --spawn"`, `"STAGE.md --spawn"`, or `"SPAWN.md [slices]"` while `_ACTIVE.md` is in `PLAN` or `BUILD`):
- Pre-Check & Escalation Unlock: If `_ACTIVE.md` is missing/`IDLE` or has no approved Plan -> halt and route via `.harness/STAGE.md` first. Inspect `git diff -- <Target>` first; if active task is `[!]` (2-Strike from a prior sequential run), explicit `--spawn` resets `Strike: 0` and marks `[/]`.
- When to Spawn vs Main Loop: Read `SPAWN_MAX_WORKERS` from `.harness/runtime/_ENV.md` (default `2`; override `--workers N`). Run ONLY when 2+ independent, substantial slices exist; small/mechanical or coupled edits run sequentially in the main loop.
- Scope Guard: Any unapproved DB migration, breaking API change, Auth/Sec change, or new dependency outside `_ACTIVE.md` `Target` -> record in `.harness/runtime/_SPAWN.md` Section 3 (`LOCK`), halt, escalate to `_ACTIVE.md` (`PLAN`).

Execution Flow (Inside `STAGE` `BUILD`):
1. Locate (if needed): Probe exact `file:line` targets in the main loop (`rg`/read) — zero `Locator` subagent overhead.
2. Disjoint Partition (`1 Disjoint Scope = 1 Worker`): Split `_ACTIVE.md` slices into strictly disjoint file sets (1 worker may own cohesive files e.g. `service.py + test_service.py`, never overlapping). Concurrent sessions isolate via `git worktree`.
3. Thin Micro-Contracts: Never pass `.harness/LAW.md`, `.harness/baselines/*`, or chat history; no nested spawn. Send bounded Work Orders: `Zero-Shot` (`file:lines`, `never: other files/deps/.env`, verify cmd), `One-Shot` (+ 1 repo snippet), or `Few-Shot` (+ 2-3 `Input -> Expected` + Red test).
4. Wave Dispatch & Envelopes: Run sequential waves of `<= SPAWN_MAX_WORKERS` active workers (wait per wave). Collect 6-line Return Envelopes; log 1-line `W-XXX` in `.harness/runtime/_SPAWN.md` Section 1.
5. Handle `BLOCK` / `FAIL` / Concurrency / 2-Strike:
   - Concurrency / Rate-Limit: Not a `Strike`. Drain active wave, halve cap (`N -> max(1, N // 2)`), resume interrupted slices (`1` = sequential main loop).
   - `BLOCK` -> halt dispatch (never auto-retry), record `Expected vs Reality` in Section 3 (`LOCK`), halt, report to Founder.
   - `FAIL` (`exit != 0` in `Target` & Strike `< 2`, max 1 retry) -> `Strike + 1`, dispatch 1 corrective Work Order.
   - `2-Strike` -> revert owned AI edits (keep user diffs), record Section 3 (`LOCK`), run `.harness/AUDIT.md`, halt.
6. Verify & Hand Back to `STAGE` (`VERIFY`): Inspect isolated `git diff -- <Target>` + Worker `OBSERVATION`s into Section 2, run `AGENTS.md` verify commands (`exit 0`), and capture snapshot via `python .harness/scripts/snapshot.py capture --track STAGE --tag <Task> --exit 0` (`.harness/runtime/snapshots/`). Mark completed steps `[x]` in `_ACTIVE.md`, clear `.harness/runtime/_SPAWN.md`, transition `_ACTIVE.md` to `VERIFY`, and halt with `Next:` — `VERIFY.md` (New or Resume Verifier session, Builder != Verifier) (single unified Gate 2 & `_LOG.jsonl` closure in `STAGE.md`).

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

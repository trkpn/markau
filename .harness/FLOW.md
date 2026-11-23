# FLOW.md - Continuous Flow Track

Immutable: Never edit .harness/FLOW.md.
Execute-only fast track for clear, low-risk incremental dev (routed upfront by AGENTS.md). Zero Gate 1 halt; zero `_FLOW.md` I/O unless hook-enabled (`.harness/runtime/_FLOW.md`).

## 1. Execution Guards
- Locate: Inspect targets via AGENTS.md Tool Triad (fd, rg, graphify) and targeted rg on _MEM.jsonl (reads <= 200 lines/read; consult query_docs for unfamiliar APIs); never guess paths/signatures.
- Hard Stop: Never read/print/commit .env/keys. If an unexpected risk or irreversible/breaking boundary is hit, do NOT halt just to tell the user to re-run STAGE.md; instead, auto-escalate in the same turn to `_ACTIVE.md` (`State: PLAN` via `.harness/STAGE.md`) and propose the Blueprint / ask only blocking questions before editing.

## 2. Work, Verify & Close
1. Work: Minimal surgical edit (keep comments/docstrings).
2. Verify & Snapshot: Run AGENTS.md verify (exit 0; UI edits: inspect visual tool if present) and capture evidence via `python .harness/scripts/snapshot.py capture --track FLOW --cmd "<verify_cmd>" --exit <code>` (.harness/runtime/snapshots/FLOW_<seq>.md).
3. 2-Strike: 2 consecutive fails: halt, revert owned AI edits (keep user diffs), report failure.
4. Reply: <= 3 lines ([FLOW] <change> | Verify: exit 0 | Snapshot: .harness/runtime/snapshots/FLOW_<seq>.md | Next: continue or `FLOW.md --done`).
5. Close (`FLOW.md --done` | pre-commit): Verify exit 0, review snapshots, log DONE to _LOG.jsonl (track:FLOW), clean (`python .harness/scripts/snapshot.py clean --track FLOW`), log _MEM.jsonl if new gotcha. No auto-commit; end `Next:` (`FLOW.md` / `PLAN.md` or commit).

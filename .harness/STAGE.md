# STAGE.md - Read-Only Multi-Stage Contract & Blueprint Template

Rules (.harness/LAW.md):
Immutable: Never edit .harness/STAGE.md. Write live state & spec to _ACTIVE.md (decoupled from git commit).
State Execution: STAGE.md, PLAN.md, BUILD.md, VERIFY.md, or _ACTIVE.md advances by State & Cursor in _ACTIVE.md (marks: [?] outlined, [ ] ready, [/] active, [x] done, [-] dropped, [!] locked):
- IDLE (or missing) -> Notes given (complex/ambiguous -> .harness/INTENT.md / state INTENT first): draft `# Spec & Task Index` in _ACTIVE.md, set State: PLAN, Cursor: READY; else ask Founder.
- INTENT -> Crystallize Problem, Outcome, Constraints, Open Questions with Founder (same session), draft `# Spec & Task Index`, set State: PLAN, Cursor: READY.
- PLAN -> Auto-detect:
  - Draft/Revise: Record Planner, write self-contained Final Plan under ## Index and ## Txx <title> (5-point gate: Target, Symbols, Contract, Command, Tests, concrete Steps) so a separate/Small Builder executes without guessing. Set State: PLAN, Cursor: READY, halt (Next: OK | BUILD.md).
  - Critique (PLAN + Cursor: READY in separate non-Planner session, or --review): Read _ACTIVE.md + real repo code; append objective critique under ## Critique at end of _ACTIVE.md (never overwrite ## Txx), set Cursor: CRITIQUE, halt (Next: PLAN.md (Resume)).
  - Reconcile (PLAN + Cursor: CRITIQUE in Planner session): Evaluate ## Critique vs original INTENT, update ## Txx, remove ## Critique, set Cursor: READY, halt (Next: OK | BUILD.md).
- BUILD -> Strict Executor: Inspect `git diff -- <Target>` first (verify actual workspace state). If task is [!] (Strike >= 2): never auto-reset on bare BUILD.md — halt and ask Founder OK (explicit --retry or --spawn resets Strike: 0, marks [/]). Record Builder, mark [/], run Steps literally (or --spawn: 1 Disjoint Scope = 1 Worker), mark done steps [x], update Cursor. Incident/ambiguity/outside Target -> save [x], set Cursor: BLOCK <why>, State: PLAN, halt (Next: PLAN.md (Resume)). Verify (`python .harness/scripts/scope.py verify --task <Task>` or Command + `python .harness/scripts/snapshot.py capture --track STAGE --tag <Task> --exit 0`). Defect < 2 strikes -> Strike + 1, append `- [ ] fix: <error>`, retry in Target; 2-Strike -> mark [!], keep diff (never `git reset` repo), record error in Cursor, halt in BUILD (Next: BUILD.md --retry | BUILD.md --spawn | PLAN.md (Resume)); exit 0 -> mark [x], set State: VERIFY, Cursor: -, halt (Next: VERIFY.md (New session)).
- VERIFY -> Record Verifier, run cross-model audit (Builder != Verifier in New session; optional 3rd model / ORACLE for high-risk) vs _ACTIVE.md + .harness/runtime/snapshots/*.md + `git diff -- <Target>` (3 passes: Correctness -> Security -> Blast Radius/Tests; cap nits <= 3). Halt (Next: OK (close)). OK -> log _LOG.jsonl (+ _MEM.jsonl if new lesson), clean snapshots (`python .harness/scripts/snapshot.py clean --all`); if pending [ ] remains -> next BUILD, else reset IDLE (Task: -, Strike: 0, Cursor: -). Issues -> mark [/], append `- [ ] fix: <why>`, set State: BUILD (Next: BUILD.md) or Cursor: BLOCK <why>, State: PLAN (Next: PLAN.md (Resume)).

Flags (STAGE|PLAN|BUILD|VERIFY|_ACTIVE.md):
- --spawn: Parallel BUILD via .harness/SPAWN.md (1 Disjoint Scope = 1 Worker; unlocks [!] -> Strike: 0).
- --review: Force Plan Critique (## Critique, Cursor: CRITIQUE).
- --status: Read-only _ACTIVE.md report.
- --diff: Inspect `git diff -- <Target>`.
- --abort: Cancel task, clear Spec & Task Index, reset IDLE.
- --retry: Reset Strike: 0, mark [/], resume BUILD.

## _ACTIVE.md Schema
State: IDLE
Task: -
Planner: -
Builder: -
Verifier: -
Strike: 0
Cursor: -

# Spec & Task Index
Goal: <Objective>
Env: <OS/Shell, Scopes, Verify cmd>
Rules: <Conventions & gotchas>

## Index
- [ ] T01 <Title>

## T01 <Title>
Intent: <Problem/outcome>
Scope: <dir or .>
Target: <explicit file paths; never empty/wildcard>
Symbols: <file:fn/class/export>
Contract: <in/out, error cases, invariants>
Risks: <edge cases, rollback, YAGNI cuts>
Command: <Verify cmd from AGENTS.md>
Tests: <cases to add/verify>
Steps:
- [ ] <action + file/symbol + expected>

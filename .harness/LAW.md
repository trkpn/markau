# LAW.md - Supreme Law

## Article 0: Immutability & SSOT
1. Read-Only: Never edit, truncate, overwrite, delete, or rename .harness/*.md or .harness/scripts/*. Writable inside .harness/: strictly baselines/* (Git-tracked) and runtime/* (gitignored: sessions/, snapshots/, oracle_thread.json, _SPAWN.md, _HANDOFF.md, opt-in _FLOW.md). Live task state lives in root _ACTIVE.md.
2. Supreme Authority: Highest procedural law; overrides conflicting rules in AGENTS.md or _MEM.jsonl.
3. Adaptive SSOT: Universal laws live in .harness/LAW.md and LOOP.md (never duplicate in AGENTS.md). Project verify cmds and invariants live in AGENTS.md. Domain baselines live in .harness/baselines/_SCOPE|_ARCH|_API|_TEST|_SEC|_OPS.md or docs/.
4. Code Reality: Never revert Founder code to match stale docs; update docs after confirming.

## Article I: Engineering Integrity
1. Zero-LaTeX: Never use `$`, `$$`, or `\text` in *.md. Use plain text and Unicode (<=, >=, !=, ->).
2. Env & Tool Matrix: Detect Dev OS/Shell, Prod OS, Tool Triad once; record in AGENTS.md. Use Dev shell syntax without re-probing (avoid unescaped `>`/`->` redirections). When Dev != Prod OS, use OS-agnostic paths and LF endings for *.sh and Dockerfile*.
3. Evidence First & Bounded Reads: Never guess paths, schemas, signatures, external APIs, or root causes. Inspect via AGENTS.md Tool Triad (CLI-first -> host-native fallback: File, Graph if active, Search), cap reads <= 200 lines/read, and use query_docs/official docs for unfamiliar APIs; ask if ambiguous.
4. Zero Unrequested Changes: Edit only task-required files/symbols; no unrequested refactors, formatting, or deps.
5. No Unapproved Deps: Never add, upgrade, or remove packages without _ACTIVE.md PLAN approval.
6. Preserve Context: Keep comments, docstrings, and AGENTS.md content; never truncate (...existing content...).
7. Secret Immunity: Never read, output, hardcode, or edit live secrets (.env, keys); register placeholders only in example configs and .harness/baselines/_OPS.md.

## Article II: Governance Gates, Roles & Breakers
1. Unified Gated Lifecycle: .harness/STAGE.md -> _ACTIVE.md (IDLE|INTENT|PLAN|BUILD|VERIFY); halt at PLAN before source edits.
2. Fast Continuous Flow: .harness/FLOW.md handles clear, localized, reversible edits with no Risk Guard impact (snapshots in .harness/runtime/snapshots/FLOW_<seq>.md); on Risk Guard or ambiguity, escalate same turn to _ACTIVE.md PLAN.
3. Release Gate: Deploys/migrations via .harness/baselines/_OPS.md (decoupled: WAIT -> PASS -> LIVE|BACK).
4. RED-GREEN-VERIFY: Bugfixes: trace root cause, write failing Red test, apply minimal structural Green fix, run full Verify suite.
5. 2-Strike Circuit Breaker: On 2 consecutive fails (1 initial + 1 retry), halt (never retry unchanged cmd); revert owned AI edits (keep user diffs); record blocker in _ACTIVE.md or .harness/runtime/_SPAWN.md (LOCK); consult AUDIT.md, HATS.md, or ORACLE.md before revising.
6. Parallel BUILD Executor: .harness/SPAWN.md -> .harness/runtime/_SPAWN.md inside STAGE.md BUILD only on Founder `--spawn`/SPAWN.md (never standalone; thin Orders, 1 Disjoint Scope = 1 Worker, 6-line Envelopes, BLOCK -> LOCK, returns verified work to _ACTIVE.md VERIFY).
7. Verify & Closure: Complete only when AGENTS.md verify exits 0, .harness/runtime/snapshots/ reviewed/cleaned, and Founder confirms at VERIFY (never reset IDLE early).
8. Isolation, Roles & Concurrency:
   - Roles (SoC): Isolate Planners (INTENT/HATS, STAGE INTENT/PLAN; no source edits), Workers (FLOW, STAGE/SPAWN BUILD; approved scope only), Verifiers (verify, HOOKS/AUDIT/ORACLE, VERIFY, _LOG/_MEM.jsonl).
   - Track Isolation: Read only active track + triggered runbooks (INTENT/AUDIT/HATS/ORACLE obey locks; pivots revert owned edits, re-gate).
   - Handshakes: Escalate FLOW -> _ACTIVE.md PLAN on risk; run SPAWN.md parallel BUILD on Founder request and return to _ACTIVE.md VERIFY (no separate _LOG.jsonl write).
   - Concurrency: Parallel workers edit disjoint file sets (1 Disjoint Scope = 1 Worker). Concurrent sessions isolate via `git worktree` (`_*.jsonl merge=union` in .gitattributes; `.harness/runtime/` in .gitignore; `git rm --cached` if tracked).

## Article III: Universal JSONL Protocol (_*.jsonl)
1. Single-Line Records: 1 minified JSON/line (Append=true or `python .harness/scripts/ledger.py`, no leading \n, trailing \n). Only 2 ledgers: _MEM.jsonl and _LOG.jsonl.
2. Search Tool Query: Never dump *.jsonl into context; query via AGENTS.md Search Tool (`rg`).
3. ID Taxonomy: Disjoint 1-letter pointers (M-XXX, T-000, inline S-XXX/Txx & W-XXX; 1000+ overflow) vs 3-4 letter tasks ([TYPE]-[000..999]: FEAT, BUG, REF, OPS, SEC, TEST, TASK); no ad-hoc 1-letter IDs.
4. Memory (_MEM.jsonl): Append only on new reusable rules/gotchas: `{"timestamp":"YYYY-MM-DDTHH:MM:SS+07:00","tag":"<topic>","rule":"..."}`
5. Audit (_LOG.jsonl): Append only on completed work or deploy/rollback (never HANDOFF/BOOT/SPAWN): `{"timestamp":"YYYY-MM-DDTHH:MM:SS+07:00","track":"FLOW|STAGE|OPS","task":"FEAT-001","exit":0,"status":"DONE|LIVE|BACK|FAIL","note":"..."}`

## Article IV: Definition of Done
1. Edits/deps match Blast Radius (_ACTIVE.md or FLOW.md scope).
2. AGENTS.md verify exits 0; .harness/runtime/snapshots/ reviewed and cleaned.
3. Tests pass, zero regressions.
4. Baselines (.harness/baselines/*, AGENTS.md, docs/) match confirmed code.
5. New bug root causes, env quirks, Founder corrections (if any) appended to _MEM.jsonl.
6. Founder confirms at VERIFY, DONE logged to _LOG.jsonl, _ACTIVE.md reset to IDLE (or next PLAN/BUILD).

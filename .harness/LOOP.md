# LOOP.md - HITL Playbooks

Immutable: Governed by .harness/LAW.md. Read active loop only; .harness/STAGE.md (_ACTIVE.md) owns 5-state gating (IDLE|INTENT|PLAN|BUILD|VERIFY), 2-Strike (LAW II.5), and closure (_LOG.jsonl -> IDLE).

## Loop 0: Bootstrap & Environment Runbook
Execute .harness/BOOT.md.

## Loop A: Feature Development
1. Context & Spec (INTENT->PLAN): Raw brief -> INTENT.md. Query _*.jsonl & impacted baselines/_ARCH|_API.md via Search Tool (full read only if editing); trade-offs -> HATS.md; if graphify-out/graph.json exists -> `graphify affected|query`. Draft Plan in _ACTIVE.md (PLAN).
2. Execute (BUILD->VERIFY): Implement steps sequentially or via SPAWN.md (`--spawn`); on UI edits inspect rendered view/screenshots via visual tool if available; verify & capture snapshot (`python .harness/scripts/scope.py verify` or `snapshot.py capture --track STAGE --tag <Task> --exit 0`); sync docs before VERIFY.

## Loop B: Bugfix & Incident
P0 Outage: Instant Rollback in .harness/baselines/_OPS.md <= 60s first, then steps 1-2.
1. RCA (PLAN): Trace failure, query _*.jsonl via Search Tool (complex -> AUDIT.md; if graphify-out/graph.json exists -> `graphify path`). Draft Root Cause + Minimal Fix in _ACTIVE.md (PLAN).
2. Red-Green-Verify (BUILD->VERIFY): Failing Red test -> minimal structural Green fix -> full AGENTS.md verify & snapshot; append _MEM.jsonl (Loop E) if reusable rule.

## Loop C: Safe Refactoring
1. Pre-Check & Spec (PLAN): Run tests; abort if failing; add characterization tests if uncovered. Log target symbols, steps, zero-API-change guarantee in _ACTIVE.md (PLAN).
2. Restructure (BUILD->VERIFY): Refactor internals keeping external API identical; capture snapshot; sync docs before VERIFY.

## Loop D: Release & Deploy
Decoupled from _ACTIVE.md / _SPAWN.md. Pre-Flight (tests pass, Expand-and-Contract migrations, baselines/_SEC.md) -> execute .harness/baselines/_OPS.md.

## Loop E: Continuous Learning (_MEM.jsonl)
Only when a bugfix, correction, or gotcha yields a reusable rule (skip routine tasks):
1. Append: 1 minified JSON line (Append=true or `python .harness/scripts/ledger.py mem`) to _MEM.jsonl. Never edit existing lines.
2. Promote: Propose permanent invariants to AGENTS.md.

## Loop S: Unified Gated & Multi-Stage Loop (STAGE.md)
Single/multi-slice gated tasks (IDLE|INTENT|PLAN|BUILD|VERIFY) -> .harness/STAGE.md -> _ACTIVE.md.

## Loop H: Context Handoff Loop (HANDOFF.md)
Session/model/multi-agent transfer (--save|--resume) -> .harness/HANDOFF.md -> .harness/runtime/_HANDOFF.md.

## Loop W: Parallel BUILD Executor (SPAWN.md)
Founder-directed parallel BUILD (--spawn) -> .harness/SPAWN.md -> .harness/runtime/_SPAWN.md -> return to _ACTIVE.md VERIFY.

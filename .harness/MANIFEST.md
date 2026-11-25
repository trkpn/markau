# MANIFEST.md - File Taxonomy (Shared Core & Swappable Engines)

Read-Only (RO), Read-Write (RW), and Append-Only files across Shared Core and Swappable Engines.

## 1. Shared Core (CONST & ATOMIC)
Lifecycle: IDLE -> INTENT -> PLAN -> BUILD -> VERIFY
- RW _ACTIVE.md: Unified live state (State, Task, Planner, Builder, Verifier, Strike, Cursor) + Spec/Index (T01..Txx / S-001..S-xxx).
- RW .harness/runtime/snapshots/<TRACK>_<tag>.md: Script-generated snapshots via .harness/scripts/snapshot.py (cleaned after VERIFY).
- Append _LOG.jsonl, _MEM.jsonl: Completion trail and gotchas via .harness/scripts/ledger.py.

## 2. Swappable Engine Adapters & Automations
- CONST System RO (.harness/*.md): FLOW.md, STAGE.md, INTENT.md, LAW.md, LOOP.md, SPAWN.md, HATS.md, HANDOFF.md, AUDIT.md, BOOT.md, HOOKS.md, MANIFEST.md
- CONST Scripts RO (.harness/scripts/*.py): scope.py, snapshot.py, ledger.py, guard.py, check.py, repomap.py, notify.py, verify_ui.py, metrics.py, _core.py
- CONST Baselines RW (.harness/baselines/, Git-tracked): _ARCH.md, _API.md, _SEC.md, _TEST.md, _SCOPE.md, _OPS.md
- Ephemeral Runtime RW (.harness/runtime/, Gitignored): sessions/, snapshots/, _ENV.md, _SPAWN.md, _HANDOFF.md, opt-in _FLOW.md (ATOMIC also uses advisor_thread.json)
- ATOMIC RO (root): SYSTEM.md, FLOW.md, PLAN.md, BUILD.md, VERIFY.md, ADVISOR.md

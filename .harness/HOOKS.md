# HOOKS.md - Capability Contract & Runtime Hook Adapter

Bridge between .harness/ governance, host capabilities, and deterministic runtime hooks across any coding agent.

## 1. Capability-Based Tool Contract
Never hardcode host tool names; resolve each capability from host tool schema or workspace CLI:
1. Host-Native Capabilities:
   - File Ops: Native read/edit/write with bounded reads (<= 200 lines/read). Never mutate source via shell redirection (cat, sed, echo >).
   - Clarification (INTENT.md): Native interactive question/plan tool if declared; else ask concisely in plain text.
   - Delegation (SPAWN.md, Art. II.6, II.8): If host declares subagent/delegation, dispatch thin Zero/One/Few-Shot Orders (1 Disjoint Scope = 1 Worker; never LAW.md or chat), log 6-line Envelopes in .harness/runtime/_SPAWN.md, sync to _ACTIVE.md; else run sequentially.
2. Workspace CLI (Tool Triad in AGENTS.md; CLI-first -> host-native fallback):
   - Graph: If graphify-out/graph.json exists, run `graphify explain|affected|path|query`; else Search.
   - File: CLI `fd` if recorded; else host file discovery.
   - Search: CLI `rg <pattern> <path>` if recorded; else host search.
3. Shared Governance CLI (.harness/scripts/):
   - `guard.py` (policy, verify & `--event secrets`), `check.py` (single-file lint/type), `repomap.py` (symbol map), `snapshot.py` (evidence), `ledger.py` (_LOG/_MEM.jsonl with redaction), `verify_ui.py` (browser verify), `notify.py` (gate alerts).

## 2. Deterministic Policy Engine (.harness/scripts/guard.py)
SSOT enforcing .harness/LAW.md invariants across hooks and post-facto checks:
1. Graphify Coexistence: Graphify hooks handle sync; exempt `graphify-out/*` from Blast Radius; preserve graphify sections on merge.
2. Pre-Edit Gate (`python .harness/scripts/guard.py --event pre-edit --path <file>` or JSON stdin):
   - Immutability (Art. 0.1): Deny .harness/*.md, .harness/scripts/*, root RO files (writable in .harness/: baselines/, runtime/).
   - Secret Immunity (Art. I.7): Deny .env* (except .env.example|.sample|.template) and private keys.
   - Lock Gate (Art. II.1-2, II.6): Deny source writes outside baselines/, runtime/, _ACTIVE.md, AGENTS.md, graphify-out/ unless _ACTIVE.md is in BUILD (within Target/Scope) or active FLOW / opt-in .harness/runtime/_FLOW.md PASS (denying high-risk DB/migration/auth/manifest paths).
3. Stop Gate (`python .harness/scripts/guard.py --event stop`):
   - Block turn exit if active BUILD, FLOW, or opt-in _FLOW.md PASS has unverified source edits without a passing snapshot (Exit Code: 0) in .harness/runtime/snapshots/.
4. Post-Facto Fallback (`python .harness/scripts/guard.py`):
   - On hosts without hook APIs, enforce invariants from `git status` at VERIFY.

## 3. Thin Host Hook Adapters
Wire hook-capable hosts to `python .harness/scripts/guard.py --event pre-edit|stop --format <fmt>` (exit 0 allow, exit 2 deny/block; path via `--path` or JSON stdin):
- Antigravity (.agents/hooks.json): `--format antigravity`
- Claude Code (.claude/settings.json) & ZCode (hooks/hooks.json): `--format claude`
- Codex (.codex/hooks.json): `--format codex`
- OpenCode / DeepSeek / Other: `--format json` (map `decision`: allow|deny|block + `reason`).

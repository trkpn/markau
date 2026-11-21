# BOOT.md - Bootstrap & Env Runbook

Idempotent setup & env sync (skip Loop A/B/C); blank/new/evolved repos.

## 1. Env Probing Matrix
- 1.1 OS/Shell: Probe active host shell (`Win/pwsh|cmd` | `macOS/zsh` | `Linux/bash`); write machine-local Env/tools (1.1-1.4, optional `SPAWN_MAX_WORKERS: <N|2>`) to `.harness/runtime/_ENV.md` (gitignored; keep `AGENTS.md` OS-agnostic).
- 1.2-1.3 File/Search: Record if installed: fd; rg <pattern> <path>
- 1.4 Graph: If graphify + graphify-out/graph.json exist, record CLI graphify (explain, affected, path, query; .harness/ in .graphifyignore)
- 1.5 Verify/Deploy: Node/TS (npm|pnpm|bun test, vitest, jest), Python (pytest, unittest, uv run pytest), PHP (pest, artisan test, phpunit; deploy.php|yaml|dep -> bind .harness/baselines/_OPS.md), Rust (cargo test), Go (go test ./...)
- 1.6 Risk Guards: Probe migrations, auth, billing, API, deploy (else Blank-State defaults); refines on re-run.

## 2. Idempotent Reconcile
1. Diff Section 1 vs AGENTS.md, .harness/runtime/_ENV.md, CLAUDE/GEMINI.md, .harness/baselines/; no diffs -> ready (IDLE).
2. Prepare Entrypoints & Baselines (sync missing/drifted):
   - AGENTS.md: Top CONST block (<=15 lines), then 1-3L Overview ([brief]/repo; TBD if blank), project verify cmds (keep OS-agnostic & preserve non-CONST):
```markdown
<!-- CONST:START -->
## Governance (.harness/)
- Language: In-repo & Git: English only. Agent responses: Thai + English tech terms; concise, no fluff.
- Auto-Route (by intent/risk, not file count; pick 1 track, never read FLOW to re-route; ambiguous -> INTENT.md first): T0 read-only/Q&A -> skip .harness/. T1 (no active gated track & ALL 3: clear spec, local reversible edit, no arch/contract/Risk Guard) -> ONLY .harness/FLOW.md. Else .harness/LAW.md + track: T2 gated task, refactor, RCA, or Risk Guard -> STAGE.md (_ACTIVE.md) + LOOP A|B|C|S (`--spawn` for parallel BUILD); release -> baselines/_OPS.md. 2 consecutive cmd fails -> stop & ask.
- Risk Guards: <From 1.6 | Blank-State defaults> (extend per project).
- Shell: Follow active host shell (on Win never assume Bash: `powershell` lacks `&&` and `>` writes UTF-16 BOM; `cmd` uses `%VAR%`/`^`). No inline code with unescaped `>`/`->`/`<`/`|`/`&` or shell-redirect edits; use file tools, runners, or script files.
- Roles: Planners (plan only, no edits), Workers (scoped edits), Verifiers (verify/audit/gate/log).
- Memory & Audit: Search _*.jsonl via rg (never dump); Append=true or `python .harness/scripts/ledger.py`. Log _MEM.jsonl only new gotchas; _LOG.jsonl on completion: {"timestamp":"<ISO-8601>","track":"FLOW|STAGE|OPS","task":"<ID>","exit":0,"status":"DONE|LIVE|BACK|FAIL","note":"<DESC>"}
- On-Demand: Load .harness/HOOKS, HANDOFF (-> runtime/_HANDOFF.md), SPAWN (-> runtime/_SPAWN.md), baselines/_OPS, BOOT, INTENT, HATS, AUDIT, ORACLE only when triggered.
- Prompt Whitelist (.md): FLOW, STAGE, PLAN, BUILD, VERIFY, _ACTIVE, SPAWN, _SPAWN, HANDOFF, _HANDOFF, HATS, AUDIT, ORACLE, INTENT, _OPS, HOOKS, BOOT -> .harness/<FILE>.md (PLAN/BUILD/VERIFY/_ACTIVE.md -> STAGE.md; _OPS.md -> baselines/_OPS.md; _SPAWN/_HANDOFF -> runtime/_<FILE>.md); other *.md stay project-scoped. Invoke: bare/@/md-link + [--flags] [arg] (halt unknown flags).
<!-- CONST:END -->
```
   - CLAUDE.md/GEMINI.md: If present or Claude/ZCode/Gemini CLI: ensure "See AGENTS.md & .harness/LAW.md." keeping existing sections (## graphify).
   - Baselines: Ensure root _ACTIVE.md, _LOG.jsonl, _MEM.jsonl exist (never edit .harness/STAGE.md); bind <PROJECT_NAME>, verify cmds, missing .harness/baselines/_SCOPE|_ARCH|_API|_TEST|_SEC|_OPS.md (or link docs). Team/worktree: add `_*.jsonl merge=union` in .gitattributes; ignore `.harness/runtime/` and `.harness/scripts/__pycache__/` in .gitignore (`git rm --cached` if tracked).
3. Gate 1: Write creates/diffs in `_ACTIVE.md` (`State: PLAN`; ask Overview if TBD), halt. Approved -> apply, reset `IDLE` (no `_LOG.jsonl`).

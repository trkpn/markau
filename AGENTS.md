<!-- CONST:START -->
## Governance (.harness/)
- Language: In-repo & Git: English only. Agent responses: Thai + English tech terms; concise, no fluff.
- Auto-Route (by intent/risk, not file count; pick 1 track, never read FLOW to re-route; ambiguous -> INTENT.md first): T0 read-only/Q&A -> skip .harness/. T1 (no active gated track & ALL 3: clear spec, local reversible edit, no arch/contract/Risk Guard) -> ONLY .harness/FLOW.md. Else .harness/LAW.md + track: T2 gated task, refactor, RCA, or Risk Guard -> STAGE.md (_ACTIVE.md) + LOOP A|B|C|S (`--spawn` for parallel BUILD); release -> baselines/_OPS.md. 2 consecutive cmd fails -> stop & ask.
- Risk Guards: Deploy (npm run deploy -> Cloudflare Pages/wrangler, bound to .harness/baselines/_OPS.md); public read-only proxy /api/fetch. No migrations/auth/billing. Blank-State defaults otherwise.
- Shell: Follow active host shell (on Win never assume Bash: `powershell` lacks `&&` and `>` writes UTF-16 BOM; `cmd` uses `%VAR%`/`^`). No inline code with unescaped `>`/`->`/`<`/`|`/`&` or shell-redirect edits; use file tools, runners, or script files.
- Roles: Planners (plan only, no edits), Workers (scoped edits), Verifiers (verify/audit/gate/log).
- Memory & Audit: Search _*.jsonl via rg (never dump); Append=true or `python .harness/scripts/ledger.py`. Log _MEM.jsonl only new gotchas; _LOG.jsonl on completion: {"timestamp":"<ISO-8601>","track":"FLOW|STAGE|OPS","task":"<ID>","exit":0,"status":"DONE|LIVE|BACK|FAIL","note":"<DESC>"}
- On-Demand: Load .harness/HOOKS, HANDOFF (-> runtime/_HANDOFF.md), SPAWN (-> runtime/_SPAWN.md), baselines/_OPS, BOOT, INTENT, HATS, AUDIT, ORACLE only when triggered.
- Prompt Whitelist (.md): FLOW, STAGE, PLAN, BUILD, VERIFY, _ACTIVE, SPAWN, _SPAWN, HANDOFF, _HANDOFF, HATS, AUDIT, ORACLE, INTENT, _OPS, HOOKS, BOOT -> .harness/<FILE>.md (PLAN/BUILD/VERIFY/_ACTIVE.md -> STAGE.md; _OPS.md -> baselines/_OPS.md; _SPAWN/_HANDOFF -> runtime/_<FILE>.md); other *.md stay project-scoped. Invoke: bare/@/md-link + [--flags] [arg] (halt unknown flags).
<!-- CONST:END -->

## Overview
MarkAu ("Markdown you can hear") — an offline-capable Markdown editor (Vite + vanilla JS, src/) with synchronized word-by-word TTS narration (Web Speech API), importers (URL, YouTube, arXiv, Substack, Reddit, PDF, EPUB, DOCX; src/importers/), translation, and version history — 100% client-side except one read-only Cloudflare Pages function (`/api/fetch`, functions/ + server/). See README.md.

## Verify
- `npm run check` (eslint + vitest)
- `npm run build` (vite -> dist)
- Deploy: `npm run deploy` (Cloudflare Pages/wrangler — Risk Guard, see .harness/baselines/_OPS.md)

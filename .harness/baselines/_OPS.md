# _OPS.md - Hosting Budget, Env Registry, Deploy & Rollback

RULES (`.harness/LAW.md`):
Release Isolation: Decoupled from `_ACTIVE.md` and `.harness/runtime/_SPAWN.md`. Governed by Loop D: halt at Release Gate (`WAIT -> PASS`) before deploy, then log `_LOG.jsonl` (`"track":"OPS","status":"LIVE"` on deploy or `"status":"BACK"` on rollback). Active specs in `_ACTIVE.md` / `.harness/runtime/_SPAWN.md` remain undisturbed during deployment.
Frugal Mandate: Keep baseline infrastructure within `<TARGET_MONTHLY_BUDGET>`. Never add paid infrastructure tiers without Release Gate approval.

## 1. Hosting Topology & Monthly Budget
- Project: markau (Cloudflare Pages project `markau`, wrangler.toml)
- Domain / Target: `<PRIMARY_DOMAIN_OR_TARGET>` (pages.dev domain + custom domain if bound)
- Runtime & Process Manager: Cloudflare Pages (static build `dist/` + Pages Functions)
- Edge & SSL: Cloudflare edge, managed SSL
- Port / Resource Map: dev `npm run dev` (vite, default 5173); prod `dist/` + `/api/fetch` function

| Component | Provider | Tier / Specs | Monthly Cost |
| :--- | :--- | :--- | :--- |
| Compute & Runtime | Cloudflare Pages | Free tier (static + functions) | `<0.00>` |
| Database / State | none | Browser-local (IndexedDB/localStorage) | `<0.00>` |
| CDN, DNS & SSL | Cloudflare | Managed | `<0.00>` |
| Backups & Storage | none | git repo is the record | `<0.00>` |
| Email / Messaging | none | - | `<0.00>` |
| Telemetry / Errors| none | - | `<0.00>` |
| External API Cap | `<PROVIDER>` (translation/LLM keys, if added) | `<HARD_CAP>` | `<0.00>` |
| Total Baseline | | | `<0.00>` |

## 2. Environment Variables Registry
RULE: Never read or edit live secret files (`.env`). Register new keys below and add safe placeholders to the example config file.

| Key | Scope (`Secret` / `Public`) | Required | Purpose & Placeholder |
| :--- | :--- | :--- | :--- |
| `<ENV_KEY>` | `<Secret \| Public>` | `<Y/N>` | `<Purpose & placeholder>` |

## 3. Zero-Downtime Deployment Runbook (Target Prod OS)
```text
# Cloudflare Pages via wrangler (functions/ compiled with static build)
# 1. Pre-deploy check
npm run check          # eslint + vitest

# 2. Build release artifact
npm run build          # vite -> dist/

# 3. Deploy
npm run deploy         # npx wrangler pages deploy --project-name markau (includes build)
# (no migrations/reload steps; stateless static + function deploy, atomic on Cloudflare edge)

# 4. Liveness check
# Open deployed URL; verify app loads and /api/fetch responds
```

## 4. Instant Rollback (< 60s)
```text
# Cloudflare Pages -> Deployment history: roll back to previous production deployment in dashboard (< 60s), or:
npx wrangler pages deployment list --project-name markau
# then promote/rollback the previous deployment via dashboard (atomic)
```

## 5. Backup & Restore Protocol
- Schedule & Target: No server state; repository (git remotes) is the only durable record. Browser document/history is user-local.
- Retention: Per git hosting policy.
- Restore Command: `git clone <remote> && npm install && npm run build`

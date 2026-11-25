# _OPS.md - Hosting Budget, Env Registry, Deploy & Rollback

RULES (`.harness/LAW.md`):
Release Isolation: Decoupled from `_ACTIVE.md` and `.harness/runtime/_SPAWN.md`. Governed by Loop D: halt at Release Gate (`WAIT -> PASS`) before deploy, then log `_LOG.jsonl` (`"track":"OPS","status":"LIVE"` on deploy or `"status":"BACK"` on rollback). Active specs in `_ACTIVE.md` / `.harness/runtime/_SPAWN.md` remain undisturbed during deployment.
Frugal Mandate: Keep baseline infrastructure within `<TARGET_MONTHLY_BUDGET>`. Never add paid infrastructure tiers without Release Gate approval.

## 1. Hosting Topology & Monthly Budget
- Domain / Target: `<PRIMARY_DOMAIN_OR_TARGET>`
- Runtime & Process Manager: `<DEPLOYMENT_RUNTIME>`
- Edge & SSL: `<EDGE_AND_SSL_STRATEGY>`
- Port / Resource Map: `<PORT_OR_RESOURCE_MAPPING>`

| Component | Provider | Tier / Specs | Monthly Cost |
| :--- | :--- | :--- | :--- |
| Compute & Runtime | `<PROVIDER>` | `<SPECS>` | `<0.00>` |
| Database / State | `<PROVIDER>` | `<SPECS>` | `<0.00>` |
| CDN, DNS & SSL | `<PROVIDER>` | `<TIER>` | `<0.00>` |
| Backups & Storage | `<PROVIDER>` | `<TIER>` | `<0.00>` |
| Email / Messaging | `<PROVIDER>` | `<TIER>` | `<0.00>` |
| Telemetry / Errors| `<PROVIDER>` | `<TIER>` | `<0.00>` |
| External API Cap | `<PROVIDER>` | `<HARD_CAP>` | `<0.00>` |
| Total Baseline | | | `<0.00>` |

## 2. Environment Variables Registry
RULE: Never read or edit live secret files (`.env`). Register new keys below and add safe placeholders to the example config file.

| Key | Scope (`Secret` / `Public`) | Required | Purpose & Placeholder |
| :--- | :--- | :--- | :--- |
| `<ENV_KEY>` | `<Secret \| Public>` | `<Y/N>` | `<Purpose & placeholder>` |

## 3. Zero-Downtime Deployment Runbook (Target Prod OS)
```text
# Option A: Atomic Release Tool (e.g. PHP Deployer 8.x: deploy.php / deploy.yaml)
vendor/bin/dep deploy    # Runs deploy:prepare, deploy:vendors, artisan:migrate, atomic current -> releases/N symlink (shared/.env stays on server)

# Option B: Manual / Container Step-by-Step
# 1. Pre-deploy backup
<BACKUP_CMD>

# 2. Fetch / build release artifact
<BUILD_OR_PULL_CMD>

# 3. Run backward-compatible migrations (Expand-and-Contract)
<MIGRATION_CMD>

# 4. Reload services
<RELOAD_CMD>

# 5. Liveness check
<HEALTH_CHECK_CMD>
```

## 4. Instant Rollback (< 60s)
```text
# Option A: Atomic Release Tool (PHP Deployer 8.x)
vendor/bin/dep rollback        # Atomic symlink revert to previous release (< 60s)
vendor/bin/dep deploy:unlock   # Clear stale deploy lock if previous run aborted

# Option B: Manual / Container Step-by-Step
# 1. Revert to previous release/artifact
<ROLLBACK_CMD>

# 2. Optional schema rollback (only if required)
<MIGRATION_ROLLBACK_CMD>

# 3. Verify recovery
<HEALTH_CHECK_CMD>
```

## 5. Backup & Restore Protocol
- Schedule & Target: `<SCHEDULE_AND_DESTINATION>`
- Retention: `<RETENTION_POLICY>`
- Restore Command: `<RESTORE_CMD>`

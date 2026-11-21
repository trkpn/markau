# _SCOPE.md - Lean Scope, Unit P&L & Sunset Criteria

ANTI-SCOPE-CREEP: AI agents must refuse to build features under Out-of-Scope (V1) unless explicitly overridden by the Founder.

## 1. Product Identity & Value Canvas
- Name / Domain: `<PROJECT_NAME_OR_DOMAIN>`
- Category: `<ASSET_CATEGORY>`
- Monetization: `<MONETIZATION_MODEL>`
- Audience: `<TARGET_PERSONA>`
- Core Problem: `<ONE_SENTENCE_PROBLEM>`
- Value Outcome: `<ONE_SENTENCE_OUTCOME>`

## 2. V1 Scope Boundaries
### In-Scope (Target Launch: `<TIMELINE>`)
- `<Deliverable 1: Core value workflow>`
- `<Deliverable 2: Monetization / Conversion flow>`
- `<Deliverable 3: Access control or SEO discovery>`
- `<Deliverable 4: Cost guardrails & legal pages>`

### Out-of-Scope (Deferred Until `<TRACTION_MILESTONE>`)
- `<Deferred 1>`
- `<Deferred 2>`
- `<Deferred 3>`

## 3. Unit Economics & Direct P&L
| Metric | Target | Actual | Status |
| :--- | :--- | :--- | :--- |
| Primary Revenue (`<REVENUE_KPI>`) | `<TARGET_BY_DAY_90>` | `<0.00>` | `WAIT` |
| Gross Margin (`(Rev - Direct Cost) / Rev`)| `<TARGET_MARGIN_%>` | `-` | `WAIT` |
| Retention / Conversion (`<RETENTION_KPI>`)| `<TARGET_RATE>` | `-` | `WAIT` |
| Maintenance Time | `<MAX_HRS_PER_WEEK>` | `-` | `WAIT` |

| Monthly P&L Line Item | M1 | M2 | M3 | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Gross Revenue | `0.00` | `0.00` | `0.00` | `<Sources>` |
| `(-)` Platform / Payment Fees | `0.00` | `0.00` | `0.00` | `<Fee %>` |
| `(-)` Variable Usage / API Cost | `0.00` | `0.00` | `0.00` | `<Variable Cost>` |
| `(-)` Fixed Hosting & Domain | `0.00` | `0.00` | `0.00` | `<Fixed Share>` |
| Net Operating Profit | `0.00` | `0.00` | `0.00` | Gross - Direct Costs |

## 4. Post-MVP RICE Backlog
Formula: `RICE = (Reach * Impact * Confidence) / Effort`

| Feature | Reach | Impact (0.25-3) | Confidence (0-1) | Effort (Wks) | Score | Decision |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `<FEATURE>` | `<0>` | `<1.0>` | `<0.8>` | `<0.5>` | `<0>` | `BACKLOG` |

## 5. Sunset Criteria (`<EVAL_DATE, e.g., Day 90>`)
- Trigger: Net Profit `< <MIN_PROFIT>` (or usage `< <MIN_TRAFFIC>`) AND MoM growth `< <MIN_GROWTH_%>`
- Action: Freeze features -> Send 30-day notice & refunds -> Sell domain/code or open-source -> Reclaim hosting resources.

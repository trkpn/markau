# _SEC.md - Threat Model, Guardrails & Legal Compliance

MANDATE: Enforce abuse/cost guardrails and comply with privacy and monetization rules (GDPR, CCPA, PDPA, payment processor terms, FTC/ad disclosures).

## 1. Threat Model & Mitigations
| Threat | Risk | Mandatory Mitigation | Status |
| :--- | :--- | :--- | :--- |
| Denial of Wallet (DoW) | Bots/abuse exhaust paid APIs, compute, or bandwidth | Sliding-window rate limits; payload size cap (`HTTP 413`); pre-flight quota check (`HTTP 402`); hard provider spend caps. | `WAIT` |
| Broken Access / IDOR | Cross-user/tenant data read or mutation | Mandatory ownership/tenant scoping on every query + cross-boundary tests. | `WAIT` |
| Injection (Query/XSS/Prompt)| Data breach, XSS, or prompt override | Parameterized queries, sanitized output rendering, delimiter isolation for untrusted inputs. | `WAIT` |
| Webhook Spoofing | Forged callbacks unlock paid features | Cryptographic signature verification + idempotency deduplication. | `WAIT` |
| Secret Exposure | Keys committed to Git or leaked to client bundle | Server-only env vars; never expose secrets in client-public build variables. | `WAIT` |

## 2. Statutory Legal Pages
| Page | Route | Required Standard | Status |
| :--- | :--- | :--- | :--- |
| Terms of Service | `<e.g., /terms>` | Acceptable use, liability limits, billing/refund terms, governing law. | `WAIT` |
| Privacy Policy | `<e.g., /privacy>` | PII collected, purpose, retention, sub-processors, contact channel. | `WAIT` |
| Cookie Notice | `<e.g., /cookies>` | Essential vs. analytics/ad tracking disclosure + opt-out control. | `WAIT` |
| Affiliate / Ad Disclosure| `<e.g., /disclosure>`| (If Ads/Affiliates used) FTC/Ad network disclosure + `rel="sponsored"`. | `WAIT` |

## 3. Sub-Processors Registry
| Category | Provider | Data Shared | Privacy / Retention Setting |
| :--- | :--- | :--- | :--- |
| Hosting & Edge | `<PROVIDER>` | `<IP, headers>` | `<Compliance>` |
| Payments | `<PROVIDER>` | `<Billing info>` | `<PCI status>` |
| External APIs / AI| `<PROVIDER>` | `<Task payload>` | `<Zero-retention / Opt-out>` |
| Analytics / Errors| `<PROVIDER>` | `<Telemetry>` | `<PII masking / Cookieless>` |

## 4. Data Privacy Controls (GDPR / CCPA / PDPA)
- Data Export: `<User data export mechanism, or N/A>`
- Account & PII Erasure: `<Erasure endpoint/mechanism - deletes PII, cancels subscriptions, anonymizes tax ledger rows>`

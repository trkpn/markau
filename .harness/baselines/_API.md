# _API.md - Interfaces, Schemas, Events & Error Contracts

SYNC RULE: Keep all external/internal interfaces, routes, CLI flags, streaming events, and webhooks documented here and synced with runtime validators.

## 1. Conventions
- Protocol / Style: `<PROTOCOL_OR_STYLE>`
- Base Path / Prefix: `<BASE_PATH>`
- Auth: `<AUTH_MECHANISM>`
- Isolation Header/Param: `<ISOLATION_IDENTIFIER>`
- Format: `<JSON / ISO-8601 UTC>`

## 2. Interface & Route Registry
| Method / Cmd | Route / Identifier | Auth | Rate Limit | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `<METHOD>` | `<HEALTH_ROUTE>` | `No` | `<LIMIT>` | Liveness & dependency check |
| `<METHOD>` | `<ROUTE>` | `<Y/N>`| `<LIMIT>` | `<Purpose>` |

## 3. Contract Specifications
### 3.1 `<INTERFACE_NAME>`
- Headers / Context: `<HEADERS>`
- Input Schema:
  ```json
  {"<field>": "<type_and_constraints>"}
  ```
- Output / Stream Schema (`<STATUS>`):
  ```json
  {"data": {}}
  ```

## 4. Webhooks & Async Events
| Source | Event | Handler | Idempotency & Signature Rule |
| :--- | :--- | :--- | :--- |
| `<SOURCE>` | `<EVENT>` | `<HANDLER>` | `<Signature check + deduplication key>` |

## 5. Standard Error Envelope
```json
{
  "success": false,
  "error": {"code": "<ERROR_CODE>", "message": "<Explanation>", "details": {}}
}
```

| Status | `error.code` | Trigger & Recovery |
| :--- | :--- | :--- |
| `400 / 422`| `VALIDATION_ERROR` | Invalid input -> Surface field details |
| `401` | `UNAUTHENTICATED` | Missing/invalid auth -> Re-authenticate |
| `402` | `QUOTA_EXCEEDED` | Tier/usage limit reached -> Prompt upgrade |
| `403` | `FORBIDDEN` | Cross-boundary or unauthorized access |
| `413` | `PAYLOAD_TOO_LARGE` | Input exceeds size cap |
| `429` | `RATE_LIMITED` | Rate limit hit -> Backoff and retry |
| `503` | `UPSTREAM_UNAVAILABLE`| External timeout -> Fallback or retry |

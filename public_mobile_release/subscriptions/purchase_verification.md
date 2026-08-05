# Purchase verification architecture

**Status:** ARCHITECTURE · NON_SUBMISSION · billing disabled

## Endpoint (future)

`POST /v1/billing/verify`

### Request (shape)

```json
{
  "platform": "ios|android",
  "signed_transaction": "...",
  "product_id": "PLACEHOLDER_ONLY",
  "app_account_token": "user_uuid"
}
```

### Server steps

1. Reject if `live_billing_enabled=false` → `403 BILLING_DISABLED`
2. Validate platform payload signature / call store verify API
3. Confirm `bundle_id` / `package_name` matches public identifiers
4. Confirm product is in allow-list (empty allow-list while real IAP banned)
5. Idempotent upsert entitlement by `original_transaction_id`
6. Emit audit event (no secrets)

## Failure modes

| Code | Meaning |
|------|---------|
| `BILLING_DISABLED` | Lane / env hard ban |
| `PRODUCT_NOT_ALLOWLISTED` | Real IAP not authorized |
| `BUNDLE_MISMATCH` | Wrong app identity |
| `SIGNATURE_INVALID` | Tamper / replay |
| `ALREADY_OWNED_OTHER_USER` | Conflict — manual support path |

## Restore

`POST /v1/billing/restore` re-runs verification for current store account receipts and binds matching transactions to the authenticated user when policy allows.

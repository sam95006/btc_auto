# Account deletion architecture (public mobile)

**Status:** ARCHITECTURE · NON_SUBMISSION  
**Legal approval claimed:** NO

## Requirements (store-facing)

Apple and Google require a path for users to initiate account deletion. This package defines the flow without enabling a production customer database.

## Flow

1. Authenticated user opens **Settings → Account → Delete account**
2. Client shows irreversible warning + data categories to be removed/anonymized (from `privacy/data_inventory.yaml`)
3. User confirms with re-auth challenge
4. Client calls `POST /v1/account/deletion-requests` on Public API Gateway only
5. Server creates `DeletionRequest(status=PENDING)` with `request_id`, `requested_at`, `actor_user_id`
6. Async worker transitions: `PENDING → VERIFYING → PURGING → COMPLETED | FAILED`
7. Client polls `GET /v1/account/deletion-requests/{id}` until terminal
8. On `COMPLETED`, local caches + push tokens cleared; session invalidated

## Data handling matrix (draft)

| Category | Action |
|----------|--------|
| Auth credentials / sessions | Revoke + delete |
| Email / profile | Delete or irreversible anonymize |
| Decision Objects (user-authored) | Soft-delete then purge per retention policy; correction events remain non-attributable if legal hold requires |
| Push tokens | Delete |
| Diagnostics | Unlink user_id; retain aggregate |
| Entitlement records | Mark cancelled; retain store transaction ids per Apple/Google rules when billing exists |

## Hard bans

- No silent deletion without user confirmation
- No private-core Lesson Memory access during public deletion
- No production customer DB in this lane (`production_customer_db_enabled=false`)
- Deletion API must reject if `PRIVATE_CORE` route is targeted

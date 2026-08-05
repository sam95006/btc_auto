# Subscription entitlement architecture

**Status:** ARCHITECTURE · `live_billing_enabled=false` · `real_iap_products_enabled=false`  
**Legal approval claimed:** NO · **Submission authorized:** NO

## Goal

Define how public membership entitlements will bind to Apple/Google subscriptions **without** enabling live billing in this lane.

## Components

| Component | Responsibility |
|-----------|----------------|
| StoreKit / Play Billing client | Purchase UI (disabled until flags flip) |
| PurchaseVerificationService | Server verifies signed transactions with Apple/Google |
| EntitlementLedger | Maps `user_id` → `plan` + `expires_at` + `source` |
| MembershipGate | Feature flags per plan (`FREE_PREVIEW`, future paid SKUs) |
| RestoreController | Re-links prior store transactions to current account |
| Cancel/RefundObserver | Ingests store server notifications → state machine |

## Entitlement states

See `restore_cancel_refund_states.yaml`.

## Verification architecture (when enabled later)

1. Client obtains store purchase token / signed transaction
2. Client → `POST /v1/billing/verify` (public gateway only)
3. Server talks to Apple App Store Server API / Google Play Developer API using **server-side secrets**
4. On success, EntitlementLedger upserts active entitlement
5. Client refreshes membership claims via auth token mint (public issuer only)

## Hard bans (current)

- No real IAP product IDs in shipped config (`real_iap_products_enabled=false`)
- No live billing UI (`live_billing_enabled=false`)
- No shared JWT issuer with private core
- Client never embeds App Store Connect / Play API secrets

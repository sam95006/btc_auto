# PUB-L Hard Bans

Machine-enforced. See `backend/public_mobile_release/hard_bans.py`.

## Global bans (this lane)

- merge PR #26 / PR #27
- deploy private core
- Demo / Shadow / exchange write / mainnet / real money
- App Store submission
- Google Play submission
- live billing
- real IAP products
- production customer database
- custodial wallet
- copy trading
- automated customer trading
- fabricated participants / interviews / paid pilots
- legal approval claims
- profitability guarantees
- G-source deletion
- writing `*_status.json`

## Required posture

| Field | Required value |
|-------|----------------|
| `submission_authorized` | `false` |
| `legal_approval_claimed` | `false` |
| `live_billing_enabled` | `false` |
| `real_iap_products_enabled` | `false` |
| `production_customer_db_enabled` | `false` |
| `private_core_route_embedded` | `false` |
| `store_submission_attempt_count` | `0` |

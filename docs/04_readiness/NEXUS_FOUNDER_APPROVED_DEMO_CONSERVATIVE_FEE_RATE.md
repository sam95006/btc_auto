# Founder Approval — Bybit Demo Conservative Fee Rate

**FOUNDER_GATE:** `APPROVE_BYBIT_DEMO_CONSERVATIVE_FEE_RATE`  
**APPROVED:** true  
**Effective:** 2026-07-31  
**Review by:** 2026-08-31  

## Values

| Key | Value |
|-----|-------|
| ENABLED | true |
| FOUNDER_APPROVED | true |
| TAKER | 0.00055 |
| MAKER | 0.00020 |
| VERSION | founder-conservative-v1-2026-07-31 |
| SOURCE | BYBIT_PUBLIC_VIP0_BASE_SCHEDULE |

## Runtime honesty

```text
fee_endpoint_supported=false
fee_rate_status=FEE_RATE_CONFIGURED_CONSERVATIVE
fee_source=FOUNDER_APPROVED_CONFIG
fee_account_specific=false
fee_live_private_api=false
```

## Pretrade policy

```text
PRETRADE_ENTRY=TAKER
PRETRADE_EXIT=TAKER
PRETRADE_ROUND_TRIP=0.00110
```

Maker `0.00020` may be used **only** in post-trade accounting when fill evidence proves maker.

## Expiry

After 2026-08-31 without re-approval → `FEE_RATE_CONFIG_EXPIRED` → `new_entry_blocked=true`.

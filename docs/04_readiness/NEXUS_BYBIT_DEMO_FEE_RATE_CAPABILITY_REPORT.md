# NEXUS Bybit Demo Fee-Rate Capability Report

**Probe run:** https://github.com/sam95006/btc_auto/actions/runs/30602684513  
**Observed:** 2026-07-31 (container on `nexus-bybit-demo-learning-validation`)  
**Domain (locked):** `https://api-demo.bybit.com`  
**Forbidden fallbacks used:** **false** (never hit mainnet/testnet)

## Result

| Field | Value |
|-------|-------|
| demo_domain | `https://api-demo.bybit.com` |
| endpoint | `/v5/account/fee-rate` |
| category | `linear` |
| symbols_tested | BTCUSDT, ETHUSDT |
| http_status | 200 |
| ret_code | **10001** |
| result_list_count | 0 |
| endpoint_supported | **false** |
| fee_rate_status | **`DEMO_FEE_ENDPOINT_UNSUPPORTED`** |
| maker_fee_rate | UNAVAILABLE |
| taker_fee_rate | UNAVAILABLE |
| fee_source | UNAVAILABLE |
| fallback_required | **true** |
| fallback_honesty | Founder-gated `FEE_RATE_CONFIGURED_CONSERVATIVE` only |
| secret_redaction | true |
| credential_mode | BYBIT_DEMO |

Both symbols identical: HTTP 200 + `retCode=10001` + empty list → **not AUTH_FAILED**, **not LIVE**.

## Recommendation

**`DEMO_FEE_ENDPOINT_UNSUPPORTED_USE_APPROVED_CONSERVATIVE`**

Runtime may use conservative fee **only after** Founder sets:

```text
NEXUS_FEE_RATE_CONSERVATIVE_ENABLED=true
NEXUS_FEE_RATE_CONSERVATIVE_FOUNDER_APPROVED=true
NEXUS_FEE_RATE_CONSERVATIVE_TAKER=<approved>
NEXUS_FEE_RATE_CONSERVATIVE_MAKER=<optional>
NEXUS_FEE_RATE_VERSION=<version>
```

Offline replay `0.00055` remains **`REPLAY_CONFIGURED_CONSERVATIVE`** until that approval — must not be auto-promoted to production constant.

# NEXUS Bybit Demo Fee-Rate Capability Report

**Status:** Probe workflow dispatched / pending live container result  
**Domain (locked):** `https://api-demo.bybit.com`  
**Endpoint:** `GET /v5/account/fee-rate`  
**Forbidden fallbacks:** `api.bybit.com`, `api-testnet.bybit.com` — **never used**

## Policy

Success is **not** “must be LIVE”.

```text
Demo fee-rate probe
├─ supported + parseable → FEE_RATE_LIVE
└─ unsupported on Demo → DEMO_FEE_ENDPOINT_UNSUPPORTED
                        → FEE_RATE_CONFIGURED_CONSERVATIVE (Founder-gated only)
```

Offline replay fee `0.00055` is labeled **`REPLAY_CONFIGURED_CONSERVATIVE`** only — not a runtime production constant until Founder approval.

## Probe fields (filled after CI artifact)

| Field | Value |
|-------|-------|
| demo_domain | `https://api-demo.bybit.com` |
| endpoint | `/v5/account/fee-rate` |
| category | `linear` |
| symbols_tested | BTCUSDT, ETHUSDT |
| http_status | *(from artifact)* |
| ret_code | *(from artifact)* |
| endpoint_supported | *(from artifact)* |
| fee_rate_status | *(from artifact)* |
| maker_fee_rate | *(from artifact)* |
| taker_fee_rate | *(from artifact)* |
| fee_source | *(from artifact)* |
| fallback_required | *(from artifact)* |
| fallback_honesty | `FEE_RATE_CONFIGURED_CONSERVATIVE_requires_founder_approval` |
| secret_redaction | true |
| forbidden_domain_fallback_used | false |

## Recommendation (pending live probe)

Placeholder until CI artifact lands:

- `DEMO_FEE_RATE_LIVE_VERIFIED` **or**
- `DEMO_FEE_ENDPOINT_UNSUPPORTED_USE_APPROVED_CONSERVATIVE` **or**
- `DEMO_FEE_RATE_PARTIAL_WITH_BLOCKERS`

## Code landed

- `tools/analysis/probe_bybit_demo_fee_rate_capability.py`
- `DEMO_FEE_ENDPOINT_UNSUPPORTED` status in `fee_rate.py`
- CI mode `probe_demo_fee_capability` on registered workflow

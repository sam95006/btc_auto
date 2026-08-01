# NEXUS Same-Router Probe Wave Report

**Recommendation:** `NEXUS_SAME_ROUTER_PROBE_PASS_12H_ENGINE_AUDIT_REQUIRED`

**12H_ALLOWED=`false`** · **24H_GATE_APPROVED=`false`** · **12H NOT STARTED**

## CI / Deploy

| Field | Value |
|-------|-------|
| ci_status | PASS |
| ci_run_id | 30710064646 |
| deployment_run | 30710117257 |
| deployment_commit (requested) | `3c6370803f25f54182b3d315813c9b60033f7671` |
| runtime env label NEXUS_DEPLOYMENT_ID | `92a89dfaa8cc` (stale label; soft finding) |
| proof new code live | observability fields + `bounded_12h_controller_type=PLACEHOLDER` + probe API |

## Read-only T+0 / T+60 / T+180

All: health=200 · positions=0 · orders=0 · mainnet=false · real_money=false · fee=FEE_RATE_CONFIGURED_CONSERVATIVE · taker=0.00055

## Account

| Field | Value |
|-------|-------|
| api_domain | https://api-demo.bybit.com |
| wallet_balance after probe | 5024.2482928 (pre-wave ~5024.318) |
| fingerprint post-restart | epochs empty / UNKNOWN |
| prior fingerprint | 17ed5abfb1bb176c |
| founder_account_match | UNKNOWN |

## Probe

| Field | Value |
|-------|-------|
| dry_run | PASS (path identity; write Δ=0) |
| live verdict | **SAME_ROUTER_DEMO_PROBE_PASS** |
| symbol / side | BTCUSDT / Sell |
| order_id_hash | 361cae41b75a3295 |
| exchange_ret_code | 0 |
| exchange_order_status | Filled |
| fill_confirmed | true |
| entry_price | 62778.2 |
| quantity | 0.007 |
| protection_verified | true |
| protection_latency_ms | 237 |
| controlled_close_completed | true |
| position/order final | 0 / 0 |
| reconciliation_final | MATCH |
| gross_pnl / fees / net_pnl | 0 / null / null (not strategy evidence) |

## 12H audit

| Field | Value |
|-------|-------|
| bounded_12h_controller_type | **PLACEHOLDER** |
| bounded_12h_full_engine_ready | **false** |

Do not request 12H Founder start until full autonomous engine replaces `_run_placeholder`.

## Evidence

- `artifacts/same_router_probe_wave/`
- `docs/04_readiness/NEXUS_12H_CONTROLLER_AUDIT.md`

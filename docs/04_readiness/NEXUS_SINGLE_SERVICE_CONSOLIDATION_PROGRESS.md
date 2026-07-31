# NEXUS Single-Service Consolidation — Progress Report

**Gate:** `FINAL_ZEABUR_SERVICE_COUNT=1` (target) · **24H:** `APPROVED=false`  
**Branch:** `feature/nexus-single-service-consolidation`  
**Base:** PR #23 tip `c5220c9` (includes PR #6 Demo Execution)  
**Keep service:** `nexus-bybit-demo-learning-validation` (`6a69ad539949111176cefe63`)  
**new_service_created:** false

---

## Status: `NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS`

| Field | Value |
|-------|-------|
| consolidation_branch | `feature/nexus-single-service-consolidation` |
| source_pr6_sha | `2a647695e9cc6f90d54a92ce5c35fd8de3000aea` |
| source_pr23_sha | `c5220c92e5dd27bb7afdd2dddfb93d738865c7de` |
| stage3_modules_migrated | partial (registry single-service mode only; internal market endpoints not cut over) |
| fee_rate_source | code path: live `/v5/account/fee-rate` → cache → Founder-gated conservative |
| fee_rate_status | honesty statuses implemented; **live Zeabur fee fetch not yet re-verified** |
| replay_rows | 1221 |
| replay_pass | 0 |
| replay_block | 1221 (`BLOCK_COST_DOMINATED_ENTRY`) |
| fee_unknown_count (replay) | **0** |
| formula_errors | **0** |
| potential_false_negative (fee→would-pass) | 0 |
| single_service_build | scaffolding (`NEXUS_SINGLE_SERVICE`, component health) |
| single_service_tests | fee honesty + control plane: **19 passed** |
| execution_owner_count | 1 (contract) |
| stage3_dependency_required | **true** until internal market cutover |
| control_plane_dependency_required | **true** until UI served only from Demo Validation |
| deploy_target_service | `nexus-bybit-demo-learning-validation` (not redeployed this round) |
| stage3_retired | false |
| old_control_plane_retired | false |
| final_zeabur_service_count | **3** (unchanged; consolidation incomplete) |
| exchange_write | false |
| mainnet | false |
| real_money | false |
| recommendation | `NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS` |

---

## Fee root cause (confirmed)

6H blocked **100%** on `FEE_RATE_UNKNOWN` because `fetch_fee_rate()` swallowed errors and returned `None`.  
Cost math never ran; zeros were dataclass defaults.

### Fixes landed on this branch

1. `backend/nexus_demo_execution/fee_rate.py` — honest statuses (`LIVE` / `CACHED_FRESH` / `CONFIGURED_CONSERVATIVE` / `UNAVAILABLE` / `AUTH_FAILED` / `SCHEMA_MISMATCH`)
2. `demo_write_client.fetch_fee_rate_quote()` — no silent invent; optional Founder-gated conservative only when `NEXUS_FEE_RATE_CONSERVATIVE_ENABLED` + `NEXUS_FEE_RATE_CONSERVATIVE_FOUNDER_APPROVED`
3. `cost_entry_gate` — unavailable path emits `UNAVAILABLE`, not `0.0`
4. Offline replay tool + artifacts

---

## Replay finding (critical)

With explicit offline taker `0.00055` (reconstructed 20U×25 notional, ±0.8% TP/SL):

- **All 1221** still `BLOCK_COST_DOMINATED_ENTRY`
- **All** have **positive** net reward (median ≈ 3.27 USDT)
- Fail reason: **`net_rr` median ≈ 0.69 < `MIN_NET_REWARD_RISK_RATIO=1.2`**
- `net/cost` median ≈ 4.5 **passes** the 1.5 cost-multiple check

So after fee is fixed, the next blocker is **R:R threshold vs ±0.8% geometry**, not missing fee data.  
This is **not** grounds to open 24H; it is grounds for offline threshold/geometry review after live fee is proven.

`ready_for_next_bounded_test` (fee/formula completeness) = true  
`24h_gate_ready` = **false**

---

## Architecture correction acknowledged

| Temporary (6H freeze) | Final |
|----------------------|-------|
| 3 services; Control Plane = UI federation only | **1** Zeabur service = Demo Validation upgraded |
| Stage3 + Validation + Control Plane | Keep Validation; retire Stage3 + Control Plane after cutover |
| Do not create a 4th service | **Confirmed** |

---

## Remaining blockers before `NEXUS_SINGLE_SERVICE_READY_FOR_BOUNDED_DEMO_VALIDATION`

1. Live-verify `fetch_fee_rate_quote` on Demo Validation (readonly) — classify AUTH vs SCHEMA vs empty.
2. Internalize Market Intelligence APIs so `stage3_dependency_required=false`.
3. Serve `/control-plane` UI from Demo Validation only; set `NEXUS_SINGLE_SERVICE=true`.
4. Deploy **to existing** Validation service ID with `exchange_write=false` / new orders blocked; T+0/60/180.
5. Scale-to-zero Stage3 + independent Control Plane after 24h no-dependency (idle ≠ trading validation).
6. Founder review of R:R threshold vs smoke TP/SL geometry before any new bounded session.

---

## Explicit non-claims

- Not merged to one live Zeabur service yet.
- Not retired Stage3 / Control Plane.
- Not started 24H.
- Post-session idle ≠ validation duration.

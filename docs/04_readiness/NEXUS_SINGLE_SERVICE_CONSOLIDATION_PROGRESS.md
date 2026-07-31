# NEXUS Single-Service Consolidation — Progress Report

**Gate:** `FINAL_ZEABUR_SERVICE_COUNT=1` (target) · **24H trading:** `APPROVED=false` · **6H V2:** not started  
**Branch:** `feature/nexus-single-service-consolidation`  
**Keep service:** `nexus-bybit-demo-learning-validation` (`6a69ad539949111176cefe63`)  
**new_service_created:** false

---

## Status: `NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS`

Deploy + fee + internalization smoke **PASS**. Remaining blocker: Stage3 + independent Control Plane still need suspend/scale-to-zero, then 24h operational observation.

| Field | Value |
|-------|-------|
| consolidation_head | `598a5e1` (+ pending scale commit) |
| deploy_run | [30605493505](https://github.com/sam95006/btc_auto/actions/runs/30605493505) |
| fee_rate_status | `FEE_RATE_CONFIGURED_CONSERVATIVE` |
| fee_source | `FOUNDER_APPROVED_CONFIG` |
| taker / maker | 0.00055 / 0.00020 |
| pretrade_round_trip | 0.00110 |
| fee_config_expiry | 2026-08-31 |
| market_internalized | true |
| control_plane_internalized | true |
| stage3_dependency_required | false |
| external_control_plane_dependency_required | false |
| geometry_complete_count (post-deploy scan) | 8 |
| geometry_missing_count | 0 |
| health_t0 / t60 / t180 | 200 / 200 / 200 |
| execution_owner_count | 1 |
| exchange_write_call_count | 0 |
| position_count / open_order_count | 0 / 0 |
| stage3_scaled_to_zero | pending |
| control_plane_scaled_to_zero | pending |
| active_running_service_count | **3** until suspend |
| mainnet / real_money | false / false |
| 6h_v2_gate_ready | **false** |
| recommendation | `NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS` |

See also: `NEXUS_SINGLE_SERVICE_CUTOVER_REPORT.md`, `NEXUS_SINGLE_SERVICE_24H_OPERATIONAL_OBSERVATION.md`.

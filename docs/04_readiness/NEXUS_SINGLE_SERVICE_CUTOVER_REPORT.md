# NEXUS Single-Service Cutover Report

**Recommendation:** `NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS`  
**Blocker remaining:** 24h read-only **operational** observation still in progress (not a trading validation). **6H V2 not started.**

| Field | Value |
|-------|-------|
| consolidation_head | `5f690be` |
| branch | `feature/nexus-single-service-consolidation` |
| fee_rate_status | `FEE_RATE_CONFIGURED_CONSERVATIVE` |
| fee_source | `FOUNDER_APPROVED_CONFIG` |
| taker_fee_rate | 0.00055 |
| maker_fee_rate | 0.00020 |
| pretrade_round_trip_fee | 0.00110 |
| fee_config_expiry | 2026-08-31 |
| market_internalized | true |
| control_plane_internalized | true |
| stage3_dependency_required | false |
| external_control_plane_dependency_required | false |
| deployment_target | `nexus-bybit-demo-learning-validation` |
| new_service_created | false |
| deployment_commit | `598a5e1` (fee env) → head `5f690be` |
| deploy_run | [30605493505](https://github.com/sam95006/btc_auto/actions/runs/30605493505) |
| health_t0 / t60 / t180 | 200 / 200 / 200 |
| market_worker / geometry_complete / missing | scan OK / **8** / **0** |
| cost_gate | configured fee path active (read-only) |
| execution_owner_count | 1 |
| exchange_write_call_count | 0 |
| position_count | 0 |
| open_order_count | 0 |
| stage3_scaled_to_zero | **true** (health **502** after `zeabur service suspend`; not deleted) |
| control_plane_scaled_to_zero | **true** (health **502** after suspend; not deleted) |
| scale_run | [30606087614](https://github.com/sam95006/btc_auto/actions/runs/30606087614) |
| active_running_service_count (HTTP 200) | **1** (Validation only) |
| hidden_dependency_count (post-suspend smoke) | **0** (Validation market/CP/fee still OK) |
| mainnet | false |
| real_money | false |
| 6h_v2_gate_ready | **false** (needs 24h operational observation complete) |

## Notes

- GraphQL direct `urllib` suspend was blocked by Cloudflare 1010; Zeabur CLI `service suspend` returned exit 0 and legacy endpoints became non-200.
- Services were **not deleted** — short-term rollback via Zeabur Restart/Resume remains possible.
- Observation checklist: `NEXUS_SINGLE_SERVICE_24H_OPERATIONAL_OBSERVATION.md`.

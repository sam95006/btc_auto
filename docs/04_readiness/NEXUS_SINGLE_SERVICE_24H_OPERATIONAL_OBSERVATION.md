# NEXUS Single-Service 24H Read-Only Operational Observation

**NOT** 24H Trading Validation.  
**exchange_write=false** · **demo_autonomous=false** · **6H V2 not started**.

## Observation window

| Field | Value |
|-------|-------|
| observation_kind | `single_service_operational_observation` |
| started_at_utc | **2026-07-31T05:11:30Z** |
| ends_at_utc | **2026-08-01T05:11:30Z** |
| sole_running_service | `nexus-bybit-demo-learning-validation` |
| sole_url | https://nexus-bybit-demo-val.zeabur.app |
| legacy_stage3_health_at_start | 502 |
| legacy_control_plane_health_at_start | 502 |
| validation_health_at_start | 200 |
| fee_at_start | `FEE_RATE_CONFIGURED_CONSERVATIVE` / `FOUNDER_APPROVED_CONFIG` |
| geometry_at_start | complete=8 missing=0 |
| scale_run | [30606087614](https://github.com/sam95006/btc_auto/actions/runs/30606087614) |

## Required continuous truths

- `stage3_http_dependency_count=0`
- `external_control_plane_http_dependency_count=0`
- `hidden_dependency_count=0`
- `market_cycles_progressing=true`
- `candidate_evidence_progressing=true`
- `geometry_complete_count` increasing over time
- `cost_gate_records_progressing=true` (read-only / dry evaluation only)
- `demo_account_fresh=true`
- `persistence_healthy=true`
- `position_count=0`
- `open_order_count=0`
- `exchange_write_call_count=0`
- `fee_rate_status=FEE_RATE_CONFIGURED_CONSERVATIVE`

## Failure flag

If any required capability dies because Stage3 / old Control Plane stopped:

`NEXUS_SINGLE_SERVICE_HIDDEN_DEPENDENCY_FOUND` → **do not** propose 6H V2.

## End-state recommendation options

- `NEXUS_SINGLE_SERVICE_READY_FOR_6H_V2_FOUNDER_APPROVAL`
- `NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS`
- `BLOCKED_NEXUS_SINGLE_SERVICE_CONSOLIDATION`

## Current checkpoint recommendation

`NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS` — observation **started**, not finished.

# NEXUS Single-Service Operational Observation — ABORTED

**Not a 24H PASS.** Founder prioritized bounded Demo execution validation.

| Field | Value |
|-------|-------|
| observation_status | `ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION` |
| operational_observation_status | `ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION` |
| operational_observation_pass | `false` |
| observation_completed_full_24h | `false` |
| reason | `FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION` |

**Forbidden claim:** `NEXUS_SINGLE_SERVICE_OPERATIONAL_24H_PASS` — **not** recorded.

## Founder Override

| Field | Value |
|-------|-------|
| founder_override_id | `FO-20260731-ABORT24H-DEMO6H12H` |
| founder_override_reason | `FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION` |
| approved_at | `2026-07-31T10:05:06Z` |
| approved_scope | abort incomplete 24H observation; Demo 6H V2; Demo 12H V3 **only via 6H machine gate** |
| FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H | `true` |
| FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2 | `true` |
| FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3 | `true` |
| source_observation_report | `docs/04_readiness/NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md` |
| override record | `artifacts/founder_override_record.json` (checksum computed from this report at gate time) |
| observation_aborted.json | `artifacts/single_service_observation/observation_aborted.json` |

Override **cannot**: enable mainnet, enable real money, disable risk controls, lower Net R:R (1.2), bypass 6H→12H machine gate, or auto-start 24H.

## Window (actual)

| Field | Value |
|-------|-------|
| observation_started_at | `2026-07-31T05:11:30Z` |
| observation_aborted_at | `2026-07-31T10:05:06Z` |
| planned_ends_at | `2026-08-01T05:11:30Z` (not reached) |
| actual_duration_hours | **4.8933** (~4h 53m) |
| sole_url | https://nexus-bybit-demo-val.zeabur.app |
| deployment_commit_at_abort | `598a5e11985f613007c8d65e61fa1dd9c7cbdf67` |
| deploy_run_at_abort | `30605493505` |

## Checkpoints (honest — no fabrication)

| Checkpoint | Status |
|------------|--------|
| T+EARLY | completed (`2026-07-31T05:52:40Z`) |
| T+1H | completed (`2026-07-31T06:11:53Z`) |
| T+3H | completed (`2026-07-31T08:12:05Z`) |
| ABORT_FINAL | completed GET-only (`2026-07-31T10:05:06Z`) |
| T+6H | **missing** (not taken; sleeper cancelled) |
| T+12H | **missing** |
| T+18H | **missing** |
| T+24H | **missing** |

completed_checkpoints=`T+EARLY,T+1H,T+3H,ABORT_FINAL`  
missing_checkpoints=`T+6H,T+12H,T+18H,T+24H`

## Abort FINAL snapshot (GET-only)

| Metric | Value |
|--------|------:|
| runtime_health (HTTP) | 200 |
| market_worker_health | HEALTHY |
| position_supervisor_health | UNKNOWN (soft) |
| persistence_health | UNKNOWN (soft) |
| geometry_complete | 8 |
| geometry_missing | 0 |
| candidate_count | 8 |
| candidate_delta (vs T+EARLY) | 0 |
| market_cycles_delta | not claimed (counter non-incremental) |
| cost_gate_delta | not claimed (null at checkpoints) |
| position_count_at_abort | **0** |
| open_order_count_at_abort | **0** |
| exchange_write_call_count_at_abort | **0** |
| hidden_dependency_count_at_abort | **0** |
| active_http_200_service_count | **1** |
| execution_owner_count | **1** |
| legacy_stage3_http_status | 404 (SUSPENDED) |
| legacy_control_plane_http_status | 404 (SUSPENDED) |
| fee_rate_status | FEE_RATE_CONFIGURED_CONSERVATIVE |
| mainnet | false |
| real_money | false |
| exchange_write | false |

Soft flags at abort (not elevated to PASS): identity label mismatch vs SoT; some component UNKNOWN.

## Legacy services (this wave)

| Service | State |
|---------|-------|
| nexus-stage3-bybit-demo-learning | **SUSPENDED** (do not resume / do not delete this wave) |
| nexus-unified-control-plane | **SUSPENDED** (do not resume / do not delete this wave) |
| nexus-bybit-demo-learning-validation | **KEEP** — sole HTTP 200 / execution owner |

## Next (approved sequence)

1. Explicit Founder override gate in CI/workflows  
2. Deploy PR #24 package to **existing Validation only** (write OFF initially)  
3. T+0 / T+60 / T+180 health  
4. Preflight → start **6H V2**  
5. Finalize / flatten / reconcile / export  
6. Machine gate → **12H V3** only if 6H hard safety PASS  
7. Stop before 24H (`DEMO_AUTONOMOUS_24H_BOUNDED_VALIDATION` APPROVED=false)

## Recommendation at abort

`NEXUS_OPERATIONAL_24H_ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION` — proceed under explicit override; **not** an operational 24H PASS.

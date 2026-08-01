# NEXUS Single-Service 24H Read-Only Operational Observation

## Status: ABORTED

| Field | Value |
|-------|-------|
| observation_status | `ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION` |
| operational_observation_pass | `false` |
| observation_completed_full_24h | `false` |
| reason | `FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION` |

**Not** `NEXUS_SINGLE_SERVICE_OPERATIONAL_24H_PASS`.

Full abort export: [`NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md`](./NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md)

## Window

| Field | Value |
|-------|-------|
| started_at_utc | 2026-07-31T05:11:30Z |
| first_abort_recorded_at_utc | 2026-07-31T10:05:06Z |
| founder_directive_reconfirm_at_utc | 2026-08-01T08:34:44Z |
| observation_aborted_at | 2026-08-01T08:34:44Z |
| planned_ends_at_utc | 2026-08-01T05:11:30Z |
| actual_duration_hours | 27.3872 |
| note | Wall clock exceeded planned end; formal T+6/12/18/24 checkpoints were **not** completed → still ABORTED, not PASS |

## Checkpoints completed before abort

| Checkpoint | Target UTC | Status |
|------------|------------|--------|
| T+EARLY | 2026-07-31T05:52:40Z | completed |
| T+1H | 2026-07-31T06:11:53Z | completed |
| T+3H | 2026-07-31T08:12:05Z | completed |
| ABORT_FINAL | 2026-07-31T10:05:06Z | completed GET-only |
| ABORT_FINAL_RECONFIRM | 2026-08-01T08:34:44Z | completed GET-only (Founder directive) |
| T+6H / T+12H / T+18H / T+24H | — | **missing** (not fabricated) |

## At abort (reconfirm)

position_count=0 · open_order_count=0 · exchange_write_call_count=0 · hidden_dependency_count=0 · active_http_200=1 · execution_owner=1 · legacy SUSPENDED · fee_ok=true · geometry_complete=0 (runtime soft/stall signal; not elevated to 24H PASS)

## Recommendation

`NEXUS_OPERATIONAL_24H_ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION`

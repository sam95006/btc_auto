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
| aborted_at_utc | 2026-07-31T10:05:06Z |
| planned_ends_at_utc | 2026-08-01T05:11:30Z (not reached) |
| actual_duration_hours | 4.8933 |

## Checkpoints completed before abort

| Checkpoint | Target UTC | Status |
|------------|------------|--------|
| T+EARLY | 2026-07-31T05:52:40Z | completed |
| T+1H | 2026-07-31T06:11:53Z | completed |
| T+3H | 2026-07-31T08:12:05Z | completed |
| ABORT_FINAL | 2026-07-31T10:05:06Z | completed GET-only |
| T+6H / T+12H / T+18H / T+24H | — | **missing** (not fabricated) |

## At abort

position_count=0 · open_order_count=0 · exchange_write_call_count=0 · hidden_dependency_count=0 · active_http_200=1 · execution_owner=1 · legacy SUSPENDED

## Recommendation

`NEXUS_OPERATIONAL_24H_ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION`

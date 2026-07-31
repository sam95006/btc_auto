# NEXUS Single-Service 24H Read-Only Operational Observation

**NOT** 24H Trading Validation.  
**exchange_write=false** · **demo_autonomous=false** · **6H V2 not started** · **legacy delete frozen until PASS**.

## Service count (Founder SoT)

| Layer | Count | Detail |
|-------|------:|--------|
| Zeabur service **cards** | 3 | Validation + Stage3 + old Control Plane still listed |
| Active **HTTP 200** services | **1** | `nexus-bybit-demo-learning-validation` only |
| Execution owners | **1** | Demo Validation |
| Suspended (HTTP ≠200) | 2 | Stage3 + old Control Plane (502) |

## Version identity (do not conflate)

| Label | SHA / ID | Meaning |
|-------|----------|---------|
| **deployment_commit (runtime SoT)** | `598a5e11985f613007c8d65e61fa1dd9c7cbdf67` | Fee-env fix + single-service deploy |
| deploy_run | `30605493505` | Validation read-only deploy |
| scale_run | `30606087614` | Legacy suspend |
| **branch_docs_tip** | `38eb6b3…` | Readiness / observation docs only — **not** runtime |

UI `version_labels.observation_deployed_code_sha` may still show an older label; treat Founder SoT `598a5e1` as deployment truth during this freeze (fee policy LIVE proves conservative config is loaded).

## Observation window

| Field | Value |
|-------|-------|
| observation_kind | `single_service_operational_observation` |
| started_at_utc | **2026-07-31T05:11:30Z** |
| ends_at_utc | **2026-08-01T05:11:30Z** |
| started_at_taiwan | 2026-07-31T13:11:30+08:00 |
| ends_at_taiwan | 2026-08-01T13:11:30+08:00 |
| sole_url | https://nexus-bybit-demo-val.zeabur.app |

## Freeze until ends_at_utc

Forbidden: redeploy, runtime code change, env/fee/geometry/R:R change, service resume/delete/rename, 6H V2, 24H trading, exchange write, demo order, mainnet, real money.

Monitor: **GET only** (`tools/ci/single_service_operational_monitor.py` + workflow `nexus-single-service-observation`).

## Checkpoints

| Checkpoint | Target UTC | Status |
|------------|------------|--------|
| T+EARLY | 2026-07-31T05:52:40Z | **PASS soft** — health 200; geo 8/0; pos/orders 0; legacy ≠200; fee_ok; soft: identity label mismatch + some component UNKNOWN |
| T+1H | 2026-07-31T06:11:53Z | **PASS soft** — health 200; geo 8/0; candidates 8; pos/orders 0; stage3/cp 404; active_http_200=1; fee_ok; same soft flags |
| T+3H | 2026-07-31T08:11:30Z | pending |
| T+6H | 2026-07-31T11:11:30Z | pending |
| T+12H | 2026-07-31T17:11:30Z | pending |
| T+18H | 2026-08-01T00:11:30Z | pending |
| T+24H | 2026-08-01T05:11:30Z | pending |

Artifacts: `artifacts/single_service_observation/`.

## Soft findings to watch

- Component health: `market_worker_health=HEALTHY`; `web` / `position_supervisor` / `persistence` may report `UNKNOWN` until workers annotate (freeze = no redeploy to “fix” labels).
- Identity label mismatch vs SoT may appear in UI envelopes — do not “fix” by redeploy during freeze.

## After T+24H PASS only

1. Final report → `NEXUS_SINGLE_SERVICE_24H_OPERATIONAL_FINAL_REPORT.md`
2. Backup legacy **non-secret** metadata
3. Conditional Founder delete of Stage3 + old Control Plane
4. Verify `zeabur_project_service_count=1`
5. **STOP BEFORE 6H V2** (`DEMO_AUTONOMOUS_6H_V2_APPROVED=false`)

## Current recommendation

`NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS` — observation in progress; legacy delete not yet allowed.

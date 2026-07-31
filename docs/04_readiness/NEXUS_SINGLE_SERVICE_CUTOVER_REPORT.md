# NEXUS Single-Service Cutover Report

**Status after T+180 smoke:** deploy PASS · fee config LIVE · legacy scale pending/partial  
**Recommendation (this checkpoint):** `NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS` until Stage3 + Control Plane are suspended and 24h operational observation completes.

| Field | Value |
|-------|-------|
| consolidation_head | `598a5e1` (fee env CLI fix) · prior fee/market `1b452a8` |
| branch | `feature/nexus-single-service-consolidation` |
| deployment_target | `nexus-bybit-demo-learning-validation` (`6a69ad539949111176cefe63`) |
| new_service_created | **false** |
| deploy_run | [30605493505](https://github.com/sam95006/btc_auto/actions/runs/30605493505) |
| deployment_commit | `598a5e1` |
| keep_service | `nexus-bybit-demo-learning-validation` |

## Fee (Founder-approved conservative)

| Field | Live value |
|-------|------------|
| fee_endpoint_supported | false |
| fee_rate_status | `FEE_RATE_CONFIGURED_CONSERVATIVE` |
| fee_source | `FOUNDER_APPROVED_CONFIG` |
| taker_fee_rate | 0.00055 |
| maker_fee_rate | 0.00020 |
| pretrade_round_trip_fee | 0.00110 (TAKER+TAKER) |
| fee_config_expiry | 2026-08-31 |
| fee_account_specific | false |
| fee_live_private_api | false |
| fee_version | `founder-conservative-v1-2026-07-31` |

## Internalization

| Field | Value |
|-------|-------|
| market_internalized | true (`market_owner=INTERNAL_MARKET_INTELLIGENCE`) |
| control_plane_internalized | true (served from Validation `/control-plane`) |
| stage3_dependency_required | **false** |
| external_control_plane_dependency_required | **false** |
| execution_owner_count | 1 |

## T+0 / T+60 / T+180 (read-only)

| Check | Result |
|-------|--------|
| health_t0 | 200 PASS |
| health_t60 | 200 PASS |
| health_t180 | 200 PASS |
| fee_rate_status (all) | `FEE_RATE_CONFIGURED_CONSERVATIVE` |
| geometry_complete_count (scan) | **8** |
| geometry_missing_count | **0** |
| exchange_write | false |
| mainnet | false |
| real_money | false |
| pytest (deploy job) | **35 passed** |

## Legacy services

| Service | Target | Status |
|---------|--------|--------|
| Stage3 `6a3b81652fdef84a45a2a553` | Scale/suspend (not delete) | pending CI `scale_legacy_to_zero` |
| Control Plane `6a6bf638ffb4fc697c8a7b1f` | Scale/suspend (not delete) | pending CI `scale_legacy_to_zero` |
| Validation | KEEP running | LIVE |

## Explicit non-approvals (still closed)

`DEMO_AUTONOMOUS_6H_V2=false` · `DEMO_AUTONOMOUS_24H=false` · `EXCHANGE_WRITE=false` · no Demo orders · no 4th Zeabur service · Net R:R 1.2 unchanged.

## Next

1. Run `scale_legacy_to_zero` (or Dashboard Suspend if API/CLI lacks suspend).
2. Confirm `active_running_service_count=1`.
3. Start **24h read-only operational observation** (not trading validation).
4. Stop before 6H V2 Founder gate.

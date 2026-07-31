# NEXUS Single-Service Consolidation — Progress Report

**Gate:** `FINAL_ZEABUR_SERVICE_COUNT=1` · trading 24H/6H V2 still closed  
**Branch:** `feature/nexus-single-service-consolidation` @ `5f690be`  
**Keep:** `nexus-bybit-demo-learning-validation` · **new_service_created=false**

## Status: `NEXUS_SINGLE_SERVICE_PARTIAL_WITH_BLOCKERS`

Cutover deploy + fee + internalization + legacy suspend smoke **done**. Remaining: finish 24h operational observation, then Founder may consider 6H V2 gate (do not auto-start).

| Metric | Value |
|--------|-------|
| deploy_run | 30605493505 |
| scale_run | 30606087614 |
| fee_rate_status | FEE_RATE_CONFIGURED_CONSERVATIVE |
| active HTTP-200 services | 1 |
| stage3 / CP health | 502 / 502 (suspended / not serving) |
| geometry_complete / missing | 8 / 0 |
| 6h_v2_gate_ready | false |
| observation_ends_utc | 2026-08-01T05:11:30Z |

# Unified Control Plane — Deploy Runbook

**Gate:** `FOUNDER_GATE=DEPLOY_UNIFIED_NEXUS_CONTROL_PLANE`  
**This document is preparation only.** Current sprint: `deploy=false`, `live_effect=false`.

## Preconditions

- PR #23 Draft green on `unified_nexus_control_plane_validation.yml`
- `pr23_scope_frozen=true`
- `execution_owner_count=1`
- `federation_write_attempt_count=0` on smoke
- `exchange_write=false`, `mainnet=false`, `real_money=false`
- 6H observation cohort **not** modified by this deploy
- Stage3 runtime **not** overwritten
- Demo Validation execution worker **not** redeployed as part of Control Plane deploy

## What deploy may change

- Deploy **read-only** Control Plane / Web surface only (when Founder approves)
- Federation GET to configured:
  - `NEXUS_STAGE3_URL` / `NEXUS_MARKET_INTELLIGENCE_URL`
  - `NEXUS_DEMO_VALIDATION_URL` / `NEXUS_DEMO_EXECUTION_URL`

## What deploy must NOT change

- 6H / 24H session state
- Cost gate / leverage / margin caps
- Demo Validation env
- Stage3 execution flags (remain disabled)
- PR #6 merge

## Smoke after Founder-approved deploy

1. `/health` 200
2. `/api/nexus/control-plane/overview` 200
3. Overview shows separate version labels (PR head ≠ observation SHA)
4. Demo Execution DOWN → `DEMO_EXECUTION_SERVICE_UNAVAILABLE` (no Stage3 wallet fallback)
5. POST `/api/nexus/control-plane/orders` → 405
6. `federation-counters.federation_write_attempt_count` remains policy-compliant

## Rollback

- Roll back Control Plane web service only
- Leave Demo Validation observation / execution worker untouched

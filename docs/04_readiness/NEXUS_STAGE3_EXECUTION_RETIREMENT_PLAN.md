# Stage3 Execution Retirement Plan

**Plan only — do not execute during 6H observation.**  
`stage3_modified=false` for this sprint. Stage3 live runtime must remain untouched until Founder gates.

## Classification key

| Class | Meaning |
|-------|---------|
| KEEP_AS_MARKET | Retain as Market Intelligence / public scan |
| MIGRATE_TO_CONTROL_PLANE | Surface via Control Plane read federation |
| DEPRECATE_AFTER_6H | Mark deprecated after 6H export + report |
| DEPRECATE_AFTER_24H | Soft-deprecate after 24H gate (if approved) |
| REMOVE_AFTER_72H | Candidate for removal after 72H evidence |
| DO_NOT_TOUCH | Frozen / out of scope |

## Inventory

| Component | Class | Notes |
|-----------|-------|-------|
| Stage3 public market status `/api/nexus/stage3/status` | KEEP_AS_MARKET + MIGRATE_TO_CONTROL_PLANE | Market SoT |
| Stage3 summary / universe scan surfaces | KEEP_AS_MARKET | Market Intelligence Gateway |
| Stage3 provider / regime / strategy cards | KEEP_AS_MARKET | Read-only intelligence |
| `/api/nexus/stage3/account` | DEPRECATE_AFTER_6H | Must not own Demo wallet UI |
| `/api/nexus/stage3/trades` | DEPRECATE_AFTER_6H | Must not own Demo trades UI |
| `/api/nexus/stage3/learning` | MIGRATE_TO_CONTROL_PLANE (display) then DEPRECATE_AFTER_24H if Validation learning supersedes | Evidence ownership moves to Validation |
| Legacy `/api/nexus/demo/autonomous/*` GET status/account/trades | DEPRECATE_AFTER_6H | Causes ACTIVE vs NONE contradiction |
| Legacy autonomous session issue/renew/emergency-stop POST | DEPRECATE_AFTER_6H | Stage3 must not be execution owner |
| Legacy autonomous scan POST | KEEP_AS_MARKET (if public scan) else DEPRECATE_AFTER_24H | Prefer Market Intelligence routes |
| Legacy autonomous close POST | DEPRECATE_AFTER_6H | Execution moves to Validation only |
| Old Auto Send / Demo Autonomous controller flags | DEPRECATE_AFTER_6H | `stage3_auto_send=false` contract |
| Old Position/Order state on Stage3 | DEPRECATE_AFTER_24H | After Validation recon proven |
| Old Reflection state on Stage3 | DEPRECATE_AFTER_24H / REMOVE_AFTER_72H | Validation persistent evidence is SoT |
| Stage3 Zeabur service process / domain | DO_NOT_TOUCH during 6H | No shutdown, no overwrite |
| Stage3 DB / volume | DO_NOT_TOUCH during 6H | |

## Target roles after Founder deploy gate

- **Stage3** → NEXUS Web + Control Plane host + Public Market Intelligence Gateway  
  (`stage3_execution_owner=false`, `stage3_exchange_write=false`, `stage3_auto_send=false`)
- **Demo Validation** → Demo Execution Worker + Reconciliation + Position Supervision + Outcome/Reflection  
  (`execution_owner=DEMO_VALIDATION_SERVICE`)

## Explicit non-actions now

- Do not delete Stage3 routes mid-6H
- Do not disable Stage3 service
- Do not redeploy Stage3 for this plan
- Do not migrate live traffic to Control Plane until `FOUNDER_GATE=DEPLOY_UNIFIED_NEXUS_CONTROL_PLANE`

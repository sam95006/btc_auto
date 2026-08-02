# NEXUS Readiness Source of Truth

Updated: 2026-08-02T15:57:33Z

## Current system stage

`OOS_PREFLIGHT_FROZEN_AWAITING_FOUNDER_PHRASE`

PR #24 head `ce661009d26df73fd369560dbe5c0220c28a079e` — Draft, not merged.

## Approved / rejected strategies

- **PRIMARY_QUALIFICATION_COHORT:** H3E (`WALK_FORWARD_VALIDATED`) — policy `H3E_OOS_POLICY_V1_FROZEN`
- **CONFIRMATORY_COHORT:** H3D (`WALK_FORWARD_VALIDATED`) — policy `H3D_OOS_POLICY_V1_FROZEN`
- **EXPLORATORY_ONLY:** H3G (`REPLAY_VALIDATED`) — must not rescue a failed H3E OOS
- **H1:** excluded — `INSUFFICIENT_SAMPLE` / `TARGET_TOO_CLOSE`
- **H2:** excluded — `REJECTED` / `NO_GROSS_EDGE` / `COST_DOMINATED_CHURN`

## Consumed datasets

- Research wave V2: `CONSUMED_NO_VALIDATED_COHORT`
- Failed OOS holdout: `OOS_REAL_MARKET_2026Q_FAILED_HOLDOUT_e186d13` (immutable, do not reuse)

## Safety state

- EXCHANGE_WRITE=false · DEMO_AUTONOMOUS_ENABLED=false · MAINNET=false · REAL_MONEY=false
- NO 6H / 12H / 24H / Shadow / Canary

## Account state

- wallet_delta_classification=`UNKNOWN`
- wallet_delta_unattributed=`-0.97052039`

## Blockers

- New untouched OOS reserved but **not** downloaded / **not** executed
- Exact Founder phrase required: `APPROVE_NEXUS_H3_UNTOUCHED_OOS_V1`
- Risk Review packet not ready
- Shadow not applied

## Next permitted action

Await Founder phrase `APPROVE_NEXUS_H3_UNTOUCHED_OOS_V1`. Until then: no OOS download, no OOS metrics, no Shadow/Demo execution.

## Recommendation

`NEXUS_NEW_OOS_PLAN_READY`

# NEXUS Readiness Source of Truth

Updated: 2026-08-02T17:18:07Z

## Current system stage

`FOOTPRINT_REDUCED_AWAITING_OOS_APPROVAL`

PR #24 — Draft, not merged. Head: `638fb5558396a113a2b91f66aef6f089e0deeed3`.

## Footprint

- initial_total_bytes=`3271808626` (~3.04GB Drive folder before cleanup)
- final_total_bytes (operational ACTIVE with venv+node_modules)=`391853326` (<= 2500000000)
- git_history_strategy=`SHALLOW_SINGLE_BRANCH_PLUS_EXTERNAL_BUNDLE`
- external bundle: `C:\\Temp\\btc_bot_history_20260803.bundle`
- Note: `G:\\我的雲端硬碟\\btc_bot` recovered via shallow clone; Google Drive sync corrupted prior `.git` during interrupted `git gc`. Local untracked `trading.db` was lost (not in git).

## Route contract

- classification=`SCANNER_USED_WRONG_APP_ENTRYPOINT`
- production entrypoint=`run.app` (not `backend.api.server.app`)
- route_count=`238`, route_contract_difference_count=`0`, runtime_import_error_count=`0`

## Approved / rejected strategies

- **PRIMARY_QUALIFICATION_COHORT:** H3E (`WALK_FORWARD_VALIDATED`) — policy `H3E_OOS_POLICY_V1_FROZEN`
- **CONFIRMATORY_COHORT:** H3D (`WALK_FORWARD_VALIDATED`) — policy `H3D_OOS_POLICY_V1_FROZEN`
- **EXPLORATORY_ONLY:** H3G (`REPLAY_VALIDATED`) — must not rescue a failed H3E OOS
- **H1:** excluded — `INSUFFICIENT_SAMPLE` / `TARGET_TOO_CLOSE`
- **H2:** excluded — `REJECTED` / `NO_GROSS_EDGE` / `COST_DOMINATED_CHURN`

## Frozen policy checksums

- H3E=`bca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33`
- H3D=`d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7`

## OOS reservation

- reservation_id=`OOS_H3_UNTOUCHED_V1_RESERVED`
- reserved_start=`1785663000001` · reserved_end=`1789551000000`
- downloaded=`false` · executed=`false`
- oos_runner_dry_run=`PASS`

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

`NEXUS_H3_OOS_APPROVAL_REQUIRED`

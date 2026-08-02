# NEXUS Readiness Source of Truth

Updated: 2026-08-02T17:52:00Z

## Current system stage

`RUNTIME_DEFECTS_REPAIRED_AWAITING_OOS_APPROVAL`

PR #24 — Draft, not merged. Head: `4aebf540178c0fe6a6ff5a72156f9e865f0eda9d`.

Canonical operational workspace: `C:\NEXUS\BTC_BOT_ACTIVE` (do not run from Google Drive).

## Verified runtime state

- D_REAL_RUNTIME_DEFECT remaining=`0`
- full_suite_collection_errors=`0`
- full_suite_test_failures=`0`
- tests_collected=`1996` · tests_passed=`1995` · skipped=`1`
  - skipped: `tests/test_market_geometry_qualification.py:113` — `cost gate blocked on fixture` (not a failure)
- runtime startup=`PASS` · health=`200`
- frontend typecheck=`PASS` · frontend production build=`PASS`
- route_count=`238` · route_contract_difference_count=`0`
- production entrypoint=`run.app`

## Footprint / workspace

- Canonical: `C:\NEXUS\BTC_BOT_ACTIVE`
- Incomplete Drive copy must be renamed to `btc_bot_INCOMPLETE_DO_NOT_RUN` (helper waits on old Cursor lock)
- Temp duplicate `C:\Temp\BTC_BOT_ACTIVE` permanently removed after tracked-tree match
- trading_db_status=`TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED` (~62MB prior local state not recovered; empty stubs not promoted)

## Approved / rejected strategies

- **PRIMARY_QUALIFICATION_COHORT:** H3E (`WALK_FORWARD_VALIDATED`) — policy `H3E_OOS_POLICY_V1_FROZEN`
- **CONFIRMATORY_COHORT:** H3D (`WALK_FORWARD_VALIDATED`) — policy `H3D_OOS_POLICY_V1_FROZEN`
- **EXPLORATORY_ONLY:** H3G (`REPLAY_VALIDATED`) — must not rescue a failed H3E OOS
- **H1:** excluded — `INSUFFICIENT_SAMPLE` / `TARGET_TOO_CLOSE`
- **H2:** excluded — `REJECTED` / `NO_GROSS_EDGE` / `COST_DOMINATED_CHURN`

## Frozen policy checksums

- H3E=`bca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33`
- H3D=`d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7`
- h3e_policy_unchanged=`true` · h3d_policy_unchanged=`true`

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
- Prior local trading.db state not recovered

## Next permitted action

Await Founder phrase `APPROVE_NEXUS_H3_UNTOUCHED_OOS_V1`. Until then: no OOS download, no OOS metrics, no Shadow/Demo execution.

## Recommendation

`NEXUS_H3_OOS_APPROVAL_REQUIRED`

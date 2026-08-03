# NEXUS Readiness Source of Truth

Updated: 2026-08-03T05:06:01Z

## Current system stage

H3_OOS_DATA_INVALID_NEW_RESERVATION_REQUIRED

PR #24 — Draft, not merged. Head: c2668ac81be1e2eea882ee0ea59bb0a519a507d7.

Canonical workspace: G:\我的雲端硬碟\btc_bot (tc_bot.code-workspace).

## OOS terminal result (H3 untouched V1)

- reservation_id=OOS_H3_UNTOUCHED_V1_RESERVED
- reserved_start=1785663000001 (2026-08-02T09:30:00.001Z)
- reserved_end=1789551000000 (2026-09-16T09:30:00Z)
- downloaded=	rue · executed=alse
- classification=DATA_INVALID
- primary_status=OOS_DATA_INVALID
- dataset_record_count=515
- dataset_checksum=9cc83d2997fc98a0d43f43324acbc7a73266b4c38a32379e640301dedc85e3d2
- Reason: reserved window still open at download time; available history is a small incomplete subset. No H3E/H3D/H3G simulation executed.
- Immutable package: rtifacts/readiness/immutable/h3_oos_v1/

## Frozen policy checksums

- H3E=ca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33 · unchanged=	rue
- H3D=d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7 · unchanged=	rue

## Approved / rejected strategies (pre-OOS walk-forward state unchanged)

- **PRIMARY_QUALIFICATION_COHORT:** H3E (WALK_FORWARD_VALIDATED) — policy H3E_OOS_POLICY_V1_FROZEN
- **CONFIRMATORY_COHORT:** H3D (WALK_FORWARD_VALIDATED) — policy H3D_OOS_POLICY_V1_FROZEN
- **EXPLORATORY_ONLY:** H3G (REPLAY_VALIDATED)

## Safety state

- EXCHANGE_WRITE=false · DEMO_AUTONOMOUS_ENABLED=false · MAINNET=false · REAL_MONEY=false
- NO 6H / 12H / 24H / Shadow / Canary
- shadow_status=NOT_APPLIED
- risk_review_packet_ready=alse

## Account state

- wallet_delta_classification=UNKNOWN
- wallet_delta_unattributed=-0.97052039
- trading_db_status=TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED

## Next permitted action

Create a **new** future untouched OOS reservation only after a complete historical reserved window is available. Do not retune H3 policies using this partial download. Do not start Shadow/Demo/timed sessions.

## Recommendation

NEXUS_H3_OOS_DATA_INVALID

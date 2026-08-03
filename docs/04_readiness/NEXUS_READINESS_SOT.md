# NEXUS Readiness Source of Truth

Updated: 2026-08-03T05:47:27Z

## Current system stage

`H3_CLOSED_HISTORICAL_FAILED_RETURN_TO_RESEARCH`

PR #24 — Draft. Head at update time: `337045fc434970ec8f83f5420a951a2255c4f033`.

## Closed Historical Holdout V1

- reservation_id=`H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED`
- window=`1720863000000` → `1736415000000` (180 days)
- dataset_checksum=`b59d8409005e5f89d01b8fa167a571b9e0665ea66b732367b006222fd988db46`
- integrity=`PASS`
- H3E primary=`CLOSED_HISTORICAL_PERFORMANCE_FAILED` trades=`32` net_pnl=`-17.84107443`
- H3D confirmatory=`CONFIRMATORY_INSUFFICIENT_SAMPLE`
- consumed=`CONSUMED_FAILED_CLOSED_HISTORICAL_HOLDOUT`
- historical_execution_mode=`HISTORICAL_SIMULATION_ONLY`
- exchange_write_attempt_count=`0` · demo_order_count=`0`

## September untouched OOS

Still sealed: `OOS_WINDOW_NOT_MATURE` / not consumed / not for research.

## Frozen policies

- H3E unchanged=`true`
- H3D unchanged=`true`

## Wallet residual (blocker for live Demo writes)

- classification=`WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST`
- remaining=`-0.97052039`

## Recommendation

`NEXUS_H3_CLOSED_HISTORICAL_FAILED_RETURN_TO_RESEARCH`

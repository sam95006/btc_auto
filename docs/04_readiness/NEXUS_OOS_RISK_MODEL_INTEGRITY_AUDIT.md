# OOS Failure Attribution And Risk-Model Integrity Audit

**Status:** COMPLETE (offline forensic)  
**No 6H / 12H / 24H / Shadow / Canary / Mainnet / Real Money**

## Canonical refs

| Field | Value |
|---|---|
| qualification_commit (consumed OOS) | `e186d130552e2456d9c26df2feb0ac8667dee54f` |
| oos_cohort_status | `CONSUMED_FAILED_HOLDOUT` |
| market_data_source | `REAL_HISTORICAL_MARKET_DATA` |
| synthetic_forced_trade_count | `0` |
| look_ahead_contamination | `false` |

## Simulator verdict

**`simulator_risk_model_result = MULTIPLE_SIMULATION_DEFECTS`**

Root cause of the prior −30U / −66U expectancy scale:

1. **Position sizing bug:** `market_event_sim` defaulted `qty=1.0` (whole coin). Legacy mean notional ≈ **15,881 USDT** vs desired **500 USDT** (`20 × 25`).
2. **Risk budget ignored:** mean max loss at stop ≈ **83 USDT** vs **3 USDT** cap (`invalid_position_size_trade_count=802`, `risk_budget_breach_count=326`).
3. **Liquidation model missing** on legacy path (`liquidation_boundary_breach_count=5` stops beyond liq; model absent for all legacy fills).
4. **PnL accounting form OK** once qty is correct (`pnl_accounting_error_count=0`) — fees on notional, not double-leveraged.

The prior OOS numbers were **not** a faithful 20U / 25x / 3U risk model. They remain a **consumed failed holdout** and must not be retuned against.

## Recalculated (exchange-valid sizing)

| Cohort | Trades | Net PnL | PF | Expectancy | MDD |
|---|---:|---:|---:|---:|---:|
| WF (val fold) | 110 | −107.12 | 0.499 | −0.97 | −112.55 |
| Consumed OOS (diagnostic only) | 123 | −153.16 | 0.367 | −1.25 | −153.16 |

Expectancy is now **~−1U/trade**, consistent with a 3U stop budget + costs (not −30U).

`recalculated_oos_status = OOS_PERFORMANCE_FAILED` (still not proof; holdout consumed).

## Gross vs cost (Founder §5)

| Version | Trades | Gross PF | Net PF | Expectancy |
|---|---:|---:|---:|---:|
| A GROSS_NO_COST | 270 | **1.005** | 1.005 | +0.006 |
| B BASE_CONSERVATIVE | 270 | 0.941 | **0.594** | −0.728 |
| C OBSERVED | 270 | 0.941 | 0.594 | −0.728 |
| D ADVERSE_STRESS | 270 | 0.882 | 0.502 | −0.985 |

**`gross_edge_classification = GROSS_EDGE_DESTROYED_BY_COST`**  
Gross edge is only marginal (PF≈1.005); costs and churn destroy it.

**`primary_failure_classification = COST_DOMINATED_CHURN`**

## Attribution (consumed OOS diagnostic)

- Losses **not** concentrated in one symbol (all five symbols negative).
- Regime almost entirely `RANGE` (122/123).
- Strategy: `STRUCT_SWING` only.
- Side: both Buy and Sell negative.
- Exit: **93 STOP_LOSS** (−239.9 net) vs **25 TAKE_PROFIT** (+83.4).

## Wallet delta (unchanged, separate)

- `wallet_delta_classification = UNKNOWN`
- `wallet_delta_unattributed = -0.97052039`
- Independent blocker; not mixed with offline sim PnL.

## Gates

| Gate | Status |
|---|---|
| risk_review_packet_ready | `false` |
| shadow_status | `NOT_APPLIED` |
| qualification_complete | `false` |
| floors | unchanged (`MIN_NET_REWARD_RISK_RATIO=1.2`, `MIN_NET_REWARD_TO_COST=1.5`) |

## Recommendation

**`NEXUS_STRATEGY_EDGE_RESEARCH_REQUIRED`**

Simulator defects are identified and recalculation path fixed (`risk_sizing` + enforce). Next work is cohort-level strategy×regime×side research on **train/validation only**, then a new chronological Walk-forward — **not** reuse of this OOS, and **not** autonomous sessions.

## Artifacts

- `artifacts/demo_validation_geometry_market_oos/risk_model_audit_report.json`
- `artifacts/demo_validation_geometry_market_oos/consumed_oos_holdout.json`
- `tools/research/run_oos_risk_audit.py`
- `tests/test_oos_risk_audit.py`

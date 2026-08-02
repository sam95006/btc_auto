# Strategy Edge Research — Cohort Discovery And New Walk-Forward

**Status:** COMPLETE (offline research)  
**No 6H / 12H / 24H / Shadow / Canary / Mainnet / Real Money**

## Source of truth

| Field | Value |
|---|---|
| audit_commit (prior) | `55c2a891db2ac2fbfe56f42b48a465f5aedb3dd5` |
| simulator policy | 20U / 25x / 500U notional / 3U max loss |
| `STRUCTURAL_GEOMETRY_GLOBAL_POLICY` | `REJECTED` |
| consumed OOS | `CONSUMED_FAILED_HOLDOUT` — excluded from tuning and gates |
| Cost floors | unchanged (`1.2` / `1.5`) |

## Result summary

| Metric | Value |
|---|---:|
| cohorts_total | 20 |
| cohorts_rejected | 12 |
| cohorts_replay_validated | 0 |
| cohorts_walk_forward_validated | 0 |
| cohorts_insufficient_sample | 8 |
| edge_survives_base_cost | 0 |
| edge_survives_adverse_cost | 0 |
| cost_dominated | 6 |
| no_gross_edge | 6 |

`range_struct_swing_status` = **REJECTED**

## Research interpretation

- No cohort cleared Replay or Walk-forward gates under exchange-valid sizing and costs.
- Several Sell-side cohorts show **positive gross expectancy** that is **destroyed by costs** (e.g. `breakout×BREAKOUT×Sell`, `VWAP_reversion×RANGE×Sell`, `liquidity_sweep×REVERSAL×Sell`).
- `trend_following×TRENDING_DOWN×Sell` shows strong gross/net expectancy but only **5** completed trades → `INSUFFICIENT_SAMPLE` (hypothesis of interest, not proof).
- CVD / funding+OI cohorts remain `INSUFFICIENT_SAMPLE` (data not in kline bundle).
- New untouched OOS plan is **deferred** until ≥1 cohort is `WALK_FORWARD_VALIDATED` (`run_automatically=false`).

## Recommendation

**`NEXUS_STRATEGY_EDGE_RESEARCH_REQUIRED`**

Next research focus: deepen confirmations and churn for cost-destroyed Sell cohorts with positive gross edge; gather more trend-following samples; do **not** run new OOS yet.

## Safety

`EXCHANGE_WRITE=false` · `DEMO_AUTONOMOUS_ENABLED=false` · `MAINNET=false` · `REAL_MONEY=false` · `24H_GATE_APPROVED=false`

Wallet delta remains `UNKNOWN` / `-0.97052039` (separate blocker).

## Artifacts

- `artifacts/demo_validation_cohort_edge/cohort_edge_research_report.json`
- `backend/nexus_demo_execution/cohort_matrix.py`
- `backend/nexus_demo_execution/cohort_edge_research.py`
- `tools/research/run_cohort_edge_research.py`
- `tests/test_cohort_edge_research.py`

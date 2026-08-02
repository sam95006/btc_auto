# Strategy Edge Research V2 — Deep Cohort + Data Expansion + Nested WF

**Status:** COMPLETE (offline)  
**No 6H / 12H / 24H / Shadow / Canary / Mainnet / Real Money / New OOS**

## Dataset audit (pre-expansion)

| Field | Value |
|---|---|
| interval | 15 |
| start / end | 1770111900000 → 1785663000000 |
| calendar_days | ~180 |
| records / symbol | 17280 |
| missing / duplicate | 0 / 0 |
| funding-event coverage | `DATA_UNAVAILABLE` |
| coverage status | **`DATASET_REGIME_COVERAGE_INSUFFICIENT`** |

RANGE-heavy; TRENDING_DOWN present but short; no event-risk / funding history.

## Expanded research data

| Field | Value |
|---|---|
| symbols | BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT |
| intervals | 15 (strategy), 60 (structure), 240 (regime) |
| span | **540 calendar days** |
| total records | **340205** |
| expanded coverage | `DATASET_REGIME_COVERAGE_ADEQUATE` |
| consumed OOS | excluded (last 15% of each hypothesis timeline) |

Timeframe justification: expected hold 30m–12h → 240/60 for regime/structure, 15m for entry + adverse-first fills.

## Hypotheses

- Registered **before** evaluation: **9** (3×H1, 3×H2, 3×H3)
- Executed: **9**
- No post-hoc variants added

## Family outcomes (inner-selected)

| Family | Best hyp | Status | Trades | Gross exp | Net exp | Base PF | Adverse PF |
|---|---|---|---:|---:|---:|---:|---:|
| H1 breakout Sell | H1A | `INSUFFICIENT_SAMPLE` | 0 | — | — | — | — |
| H2 VWAP Range Sell | H2A | `REJECTED` | 254 | +0.135 | −0.690 | 0.640 | 0.542 |
| H3 Trend Down Sell | H3B | `INSUFFICIENT_SAMPLE` | 3 | +1.93 | +1.77 | 2.85 | 2.85 |

### Interpretation

- **H1:** Candidates exist, but fills ≈0 because Structural Geometry **Cost Gate** blocks under unchanged floors (1.2 / 1.5). Not evidence of edge; not a reason to lower floors.
- **H2:** Clear sample. Gross edge destroyed by cost (`COST_DOMINATED_CHURN`). Median hold ~5 bars; median gross_move_to_cost ~3.0 — still not enough after fees/spread/slip.
- **H3:** Expanded data still yields only **3** completed fills after Cost Gate — remains `INSUFFICIENT_SAMPLE` (threshold not lowered). Strong unit economics on those 3 are **not** qualification.

## Gates

| Metric | Value |
|---|---:|
| cohorts_replay_validated | 0 |
| cohorts_walk_forward_validated | 0 |
| cohorts_rejected | 2 |
| cohorts_insufficient_sample | 7 |
| new_untouched_oos_plan_ready | **false** |
| oi_funding_cvd_data_plan_ready | true (plan only; no promotion) |

## Recommendation

**`NEXUS_STRATEGY_EDGE_RESEARCH_REQUIRED`**

Next (still offline): redesign H2 for larger displacement / longer holds without lowering costs; redesign H1/H3 so Cost-Gate-passable geometry exists *before* counting sample; do not run new OOS.

Wallet delta remains `UNKNOWN` / `-0.97052039`.

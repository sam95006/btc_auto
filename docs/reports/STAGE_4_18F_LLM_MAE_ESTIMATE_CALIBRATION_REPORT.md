# Stage 4.18-F — LLM MAE Estimate Calibration Report

**Generated:** 2026-07-06 (UTC+8)  
**Code commit:** `2474a28`  
**Prior 4.18-E report:** `da66e8f`  
**Mode:** prompt/schema + offline validator replay — **no new LLM soak, no orders, no RG changes**

---

## 1. Executive summary

Stage 4.18-F calibrates **how the LLM should express** `mae_risk_estimate_pct` (percent units, symbol caps, invalidation consistency) and adds **offline paper-readiness validation** that marks over-cap MAE as `decision_quality_incomplete` without turning issues into `parse_error`.

**Verdict: PARTIAL (code PASS, replay confirms scale issue)**

| Criterion | Result |
|-----------|--------|
| Tests | **243/243 PASS** |
| Prompt MAE scale hints | PASS |
| Paper-readiness MAE cap validation | PASS |
| Logger blocks incomplete → `hypothetical_skip` | PASS (`decision_quality_incomplete` × 15) |
| Offline replay graduations | 0 (expected — no new LLM) |
| Stage 4.19 ready | **NO** |

**Root cause confirmed:** 418d LLM MAE estimates are **not wrong-unit (>5%)** but **systematically too high for paper caps** — BTC watches average **1.45%** vs cap **0.35%** (all 6 BTC MAE ticks > 0.28% and > 0.35%).

---

## 2. 4.18-E partial root cause

4.18-E wired `mae_risk_estimate_pct` into paper guards. Replay showed `llm_mae_used_count=23` but BTC/ETH LLM values still exceeded paper watch survival (0.28%) and graduation (0.35%) thresholds.

418-F analysis proves the blocker is **LLM estimate magnitude**, not guard plumbing:

- BTC `mae_risk_estimate_pct`: min **1.2**, max **1.5**, avg **1.45**
- SOL: min **1.2**, max **3.0**, avg **1.7**
- PEPE: min **0.02**, max **2.0**, avg **1.255**
- All 16 paper-ready watches (LLM-flagged) have MAE **above** symbol caps except **1** PEPE tick (0.02%)

The LLM appears to output values in **percent** but at **~4–10× the paper guard scale** (e.g. 1.2 meaning 1.2% when paper expects ~0.12–0.35% for majors).

---

## 3. 418D LLM MAE distribution

**Analysis output:** `/data/stage4_18f_mae_calibration_analysis/stage4_18f_mae_distribution.json`

| Metric | Value |
|--------|-------|
| `mae_present_count` | 16 |
| `btc_eth_above_0_28_pct_count` | 6 / 6 (100%) |
| `btc_eth_above_0_35_pct_count` | 6 / 6 (100%) |
| `recomputed_incomplete_count` | **15** |
| `paper_ready_watch_mae_within_cap_count` | **1** |
| `paper_ready_watch_mae_above_cap_count` | **15** |
| `mae_invalidation_consistency_fail_count` | 0 |

**By symbol (watch MAE %):**

| Symbol | Count | Min | Max | Avg | Above cap |
|--------|-------|-----|-----|-----|-----------|
| BTCUSDT | 6 | 1.2 | 1.5 | 1.45 | 6 |
| SOLUSDT | 6 | 1.2 | 3.0 | 1.7 | 6 |
| PEPEUSDT | 4 | 0.02 | 2.0 | 1.255 | 3 |

**MAE quality issues:** `mae_above_symbol_cap_0.35` × 6, `mae_above_symbol_cap_0.25` × 6, `mae_above_symbol_cap_0.2` × 3

---

## 4. Prompt calibration changes

**File:** `tools/research/stage4_prompt_builder.py`

Added Stage 4.18-F rules:

1. `mae_risk_estimate_pct` is **percent** (0.25 = 0.25%, not 25% or 0.0025)
2. BTC/ETH watch reasonable range **0.05–0.35%**; above 0.35% → soft/hard skip, not paper-ready watch
3. SOL watch > 0.25% → lower paper_readiness / soft_skip
4. PEPE watch > 0.20% → lower paper_readiness / soft_skip
5. High MAE → `paper_readiness.eligible_for_watchlist=false`, `block_reason=mae_risk_too_high`
6. `mae_risk_estimate_pct <= invalidation.max_adverse_move_pct` (same units)

---

## 5. MAE scale / cap validation rules

**File:** `tools/research/stage4_paper_readiness.py`

| Rule | Action |
|------|--------|
| `mae_risk_estimate_pct > 5.0` | `decision_quality_incomplete` (scale invalid) |
| `mae > invalidation.max_adverse_move_pct` | incomplete |
| BTC/ETH watch MAE > 0.35% | incomplete |
| SOL watch MAE > 0.25% | incomplete |
| PEPE watch MAE > 0.20% | incomplete |
| `paper_readiness.block_reason=mae_risk_too_high` | logger blocks |

`infer_decision_quality_incomplete()` **always recomputes** (418d replay applies new rules to stored JSONL).

**Logger** (`stage4_paper_event_logger.py`): incomplete / `mae_risk_too_high` → `hypothetical_skip` with reason `decision_quality_incomplete` or `paper_readiness_mae_block` (not silent exclusion).

**Validator** (`validate_stage4_ai_decision_outputs.py`): exports MAE calibration metrics.

**Analysis tool:** `tools/research/stage4_mae_calibration_analysis.py`

---

## 6. Offline replay result on 418D (no new LLM)

**Paper logger:** `/data/stage4_paper_events_418f_mae_calibrated`

| Metric | 4.18-E | 4.18-F |
|--------|--------|--------|
| `events_written` | 23 | 23 |
| `watchlist_count` | 1 | 1 |
| `hypothetical_skip_count` | 22 | 22 |
| `decision_quality_incomplete` (reason) | 0 | **15** |
| `paper_ready_watch_count` | 16 | **1** |
| `recomputed_incomplete_count` | — | **15** |

**Calibration:** `/data/stage4_18f_mae_calibration_replay`

- `calibration_total_graduations`: **0**
- `recommended_mode_for_419`: **none**
- Major watchlists created: **0** (incomplete BTC/ETH watches excluded from eligible pool)

This is **expected** without a new LLM soak — stored 418d decisions still carry high MAE values; 418-F correctly **reclassifies** them.

---

## 7. New LLM soak needed?

**YES — Stage 4.18-G (recommended): 30m schema regression** with updated prompt.

418-F only changes prompt/validator/logger. Until a new dry-run produces lower, cap-aligned `mae_risk_estimate_pct`, graduation replay will remain 0.

Success criteria for 4.18-G:

- BTC/ETH watch MAE mostly ≤ 0.35% (ideally ≤ 0.28% for watch survival)
- `paper_ready_watch_mae_within_cap_count` >> `paper_ready_watch_mae_above_cap_count`
- `recomputed_incomplete_count` near 0 for watch intents
- Then re-run paper logger + calibration before Stage 4.19 gate

---

## 8. Stage 4.19 readiness

**NOT READY**

Formal Risk Governor thresholds **unchanged**. Paper path now **correctly rejects** mis-scaled LLM MAE. Next gate requires **new LLM output** under calibrated prompt.

---

## 9. Safety confirmation

| Check | Value |
|-------|-------|
| `mock_ai_used_count` | 0 |
| `order_sent_count` | 0 |
| `any_exchange_call_made` | false |
| Formal RG thresholds changed | **NO** |
| `applied_patches` | **NO** |
| Stage 4.19 auto-started | **NO** |

---

## 10. Explicit non-execution statement

No orders, demo orders, paper execution, ARM, radar, production/btc-auto, 6h/24h soak, or exchange private API calls. Analysis and replay used existing `/data/stage4_ai_decisions_418d_schema_regression_30m` only.

---

## 11. Tests

```bash
python -m unittest tests.test_stage4_ai_decision_layer -v
python -m unittest tests.test_stage4_paper_event_logger -v
python -m unittest tests.test_stage4_watchlist_followup_simulator -v
```

**Result:** 243/243 passed.

---

**final_verdict:** `STAGE_4_18F_PARTIAL` — validation plumbing PASS; LLM MAE scale mismatch confirmed; **new 30m soak required before Stage 4.19**. Stopped at gate.

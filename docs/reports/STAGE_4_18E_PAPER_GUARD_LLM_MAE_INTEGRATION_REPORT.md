# Stage 4.18-E — Paper Guard LLM MAE Integration Report

**Generated:** 2026-07-06 (UTC+8)  
**Code commit:** `ec49a04`  
**Prior 4.18-D report:** `71a00fd`  
**Mode:** offline paper replay only — **no orders, no RG threshold changes, no Stage 4.19 auto-start**

---

## 1. Executive summary

Stage 4.18-E integrated `mae_risk_estimate_pct` from the AI decision layer into paper-only MAE guards via `get_paper_mae_pct()`, with automatic fallback to the legacy market-volatility proxy when LLM MAE is missing or invalid.

**Verdict: PARTIAL**

| Criterion | Result |
|-----------|--------|
| LLM MAE wired into paper logger | PASS (`llm_mae_used_count=23` on 418d) |
| Paper events written | PASS (23) |
| Watchlist events | PASS (1, was 0 in 4.18-D) |
| Calibration graduations (BTC/ETH) | FAIL (0 all modes) |
| Stage 4.19 ready | **NO** |

Integration is **correct and safer** than loosening formal Risk Governor thresholds. Remaining blocker: LLM `mae_risk_estimate_pct` on BTC/ETH watch ticks still exceeds paper MAE caps at graduation (and watch downgrade threshold for most majors).

---

## 2. Why 4.18-D still had zero watchlists / graduations

4.18-C repaired schema and produced `paper_ready_watch_count=16`, but paper guards used `_mae_proxy_pct()` derived from `market_context.volatility_15m` / `volatility_level`. High-vol proxy values (~0.30%+) exceeded the watch downgrade threshold (`mae_cap × 0.80` = 0.28% for BTC/ETH), causing `mae_watch_downgrade` on all 16 paper-ready watches.

4.18-E does **not** change formal RG thresholds. It only lets the **paper/offline path** prefer the LLM's own `mae_risk_estimate_pct` when valid.

---

## 3. MAE source integration design

**New module:** `tools/research/stage4_paper_guard_inputs.py`

```python
get_paper_mae_pct(decision, mae_source_mode="llm_mae_primary") -> (mae_pct, source)
```

| `source` | When |
|----------|------|
| `llm_mae_risk_estimate_pct` | Valid numeric `0 <= value <= 5.0` |
| `legacy_market_proxy` | LLM missing/invalid and legacy proxy > 0 |
| `missing` | Neither LLM nor legacy yields a positive value (never silently treated as allow) |

**Paper event logger** (`stage4_paper_event_logger.py`):

- `apply_paper_guards()` uses `get_paper_mae_pct()` for MAE watch/enter downgrade, SOL trend MAE, PEPE MAE cap
- Events include `paper_mae_pct`, `paper_mae_source`, `llm_mae_risk_estimate_pct`
- Summary includes `mae_source_distribution`, `llm_mae_used_count`, `legacy_mae_proxy_used_count`, `missing_mae_source_count`

**Watchlist simulator** (`stage4_watchlist_followup_simulator.py`):

- Legacy 4.18-B modes keep `mae_source_mode=legacy_proxy_primary`
- New LLM modes: `major_mae_100_llm_mae`, `major_mae_100_llm_mae_side_memory`, `major_mae_100_llm_mae_conf_floor`
- `recommend_calibration_mode_for_419` prefers LLM modes when graduations exist

---

## 4. Paper logger result on 4.18-D (replay, no new LLM soak)

**Input:** `/data/stage4_ai_decisions_418d_schema_regression_30m`  
**Output:** `/data/stage4_paper_events_418e_llm_mae` (overwrite after container tool sync)

| Metric | 4.18-D (legacy proxy) | 4.18-E (LLM primary) |
|--------|----------------------|----------------------|
| `events_written` | 23 | 23 |
| `watchlist_count` | 0 | **1** |
| `hypothetical_skip_count` | 23 | 22 |
| `mae_watch_downgrade` | 16 | **15** |
| `llm_mae_used_count` | 0 | **23** |
| `legacy_mae_proxy_used_count` | 23 | 0 |
| `order_sent_count` | 0 | 0 |

**MAE source distribution (418d):**

```json
{
  "llm_mae_risk_estimate_pct": 23,
  "legacy_market_proxy": 0,
  "missing": 0
}
```

**Residual blocks on 418d:**

- `mae_watch_downgrade`: 15 (BTC/ETH LLM MAE still above 80% watch cap for most ticks)
- `sol_trend_mae`: 6 (SOL trend guard, independent of proxy swap)
- `trend_watchlist_threshold_3`: 6
- `pepe_watchlist_only`: 4 (PEPE watch-only path; 1 PEPE watch became watchlist)

---

## 5. Calibration replay result on 4.18-D

**Output:** `/data/stage4_18e_llm_mae_calibration`

| Mode | `mae_source_mode` | `watchlist_confirmed` | `hypothetical_graduation_count` | Primary block |
|------|-------------------|----------------------|--------------------------------|---------------|
| `major_mae_100_llm_mae` | `llm_mae_primary` | 1 | 0 | `mae_cap_violation_100pct` (5) |
| `major_mae_100_llm_mae_side_memory` | `llm_mae_primary` | 1 | 0 | `mae_cap_violation_100pct` (5) |
| `major_mae_100_llm_mae_conf_floor` | `llm_mae_primary` | 1 | 0 | `confidence_below_0.4` (5) |
| Legacy `major_mae_100` | `legacy_proxy_primary` | 1 | 0 | `mae_cap_violation_100pct` (5) |

- `calibration_total_graduations`: **0**
- `BTC graduations`: **0**
- `ETH graduations`: **0**
- `SOL graduations`: **0**
- `PEPE graduations`: **0**
- `recommended_mode_for_419`: **none**

---

## 6. Optional combined historical + 4.18-D replay

**Paper output:** `/data/stage4_paper_events_418e_combined`  
**Calibration output:** `/data/stage4_18e_combined_calibration`

| Metric | Value |
|--------|-------|
| `combined_total_events` | 177 |
| `combined_watchlist_count` | 1 |
| `llm_mae_used_count` | 23 (418d rows only) |
| `legacy_mae_proxy_used_count` | 154 (pre-418c sessions) |
| `combined_total_graduations` | 0 |
| `combined_recommended_mode_for_419` | none |

Historical sessions without `mae_risk_estimate_pct` correctly fell back to legacy proxy without failure.

---

## 7. Quality improvement assessment

**Yes, partial improvement:**

- MAE source plumbing works end-to-end (`llm_mae_used_count=23` on 418d)
- Watchlist path unblocked for 1 PEPE watch (was 0)
- `mae_watch_downgrade` reduced 16 → 15
- Formal RG / live paths untouched

**Not sufficient for Stage 4.19:**

- BTC/ETH confirmed watchlists still fail graduation: LLM MAE at 100% cap still violates on 5 major ticks
- Majority of paper-ready watches remain `hypothetical_skip` due to MAE + symbol-specific guards (SOL trend MAE)

---

## 8. Stage 4.19 readiness

**NOT READY**

Recommended next step (gate — do not auto-start 4.19):

1. **Prompt / schema tuning (4.18-F candidate):** Calibrate LLM to output `mae_risk_estimate_pct` consistent with paper caps (BTC/ETH ≤ 0.28% for watch survival, ≤ 0.35% for graduation), without loosening formal RG.
2. Re-replay paper logger + calibration on 418d (no new soak) after prompt fix.
3. Only after `calibration_total_graduations > 0` and `recommended_mode_for_419 != none` should operator approve Stage 4.19 offline paper exit.

---

## 9. Safety confirmation

| Check | Value |
|-------|-------|
| `mock_ai_used_count` | 0 |
| `order_sent_count` | 0 |
| `any_exchange_call_made` | false |
| `demo_order_enabled` | false (not invoked) |
| `paper_order_execution_enabled` | false |
| `arm_enabled` | false |
| `radar_enabled` | false |
| `production_touched` | false |
| `btc_auto_touched` | false |
| Formal RG thresholds changed | **NO** |
| `applied_patches` written | **NO** |

---

## 10. Explicit non-execution statement

This stage performed **offline replay only** on existing `/data/stage4_ai_decisions_*` JSONL inputs. No new LLM soak, no demo orders, no paper order execution, no exchange private API calls, no ARM, no radar, no production/btc-auto changes, and no automatic Stage 4.19 start.

---

## 11. Tests

```bash
python -m unittest tests.test_stage4_paper_event_logger -v
python -m unittest tests.test_stage4_watchlist_followup_simulator -v
python -m unittest tests.test_stage4_ai_decision_layer -v
```

**Result:** 232/232 passed (local, post-`ec49a04`).

---

**final_verdict:** `STAGE_4_18E_PARTIAL` — LLM MAE integration verified; watchlist yield improved marginally; calibration graduations still zero; **stopped at gate**.

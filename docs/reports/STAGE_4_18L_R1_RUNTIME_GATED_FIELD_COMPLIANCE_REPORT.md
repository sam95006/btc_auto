# Stage 4.18-L-R1 — Runtime-Gated 30m Field Compliance Regression

**Date:** 2026-07-07 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Prior commit:** `227da99` (418-L)  
**Output:** `/data/stage4_ai_decisions_418l_r1_field_compliance_30m`  
**Mode:** read-only 30m dry-run with **418-L** prompt — no orders

---

## 1. Executive summary

**Verdict: PARTIAL**

| Layer | Result |
|-------|--------|
| Runtime version gate | **PASS** (418-L hints, stage_marker=4.18-L) |
| Preflight | **PASS** (`can_start_long_soak=true`, probe=2) |
| Technical soak | **PASS** (6/6 ticks, 24 effective, parse=0, order=0) |
| Field compliance | **PARTIAL** — side/trigger rates improved on some symbols; `valid_watch_candidate_count=0` |
| MAE alignment | **REGRESSED** — `within_cap=0` vs J-R1 `2`; `above_cap=18` vs J-R1 `13` |
| BTC / ETH graduations | **0** |
| `recommended_mode_for_419` | **none** |
| Stage 4.19 | **NOT started** |

418-L prompt produced marginal field-compliance gains (PEPE/ETH side rate, BTC/SOL trigger rate) but MAE estimates remain far above symbol caps (1.0–3.0% vs 0.35% BTC/ETH cap). All 19 paper-intent watches blocked by `mae_above_symbol_cap`. Prompt-only iteration insufficient — recommend **418-M** structured-output hardening, not 60m sample.

---

## 2. Runtime gate

| Check | Result |
|-------|--------|
| `runtime_version_check_passed` | **true** |
| `prompt_hints_present` | **true** (418-F/H/I/J/L) |
| `stage_marker` | **4.18-L** |
| BTC/ETH side examples | **present** |
| LONG→BUY / SHORT→SELL | **present** |
| `entry_trigger` required guidance | **present** |
| `app_file_stale_suspected` | **false** |
| Patch dir | `/data/stage4_418f_runtime_patch/` (14 files) |

---

## 3. Preflight

| Check | Result |
|-------|--------|
| `can_start_long_soak` | **true** |
| `preflight_probe_call_count` | **2** |
| `stage3_context_check_passed` | **true** |
| `mock_used` | **false** |
| `order_sent` | **false** |
| `debug_log_has_api_key` | **false** |

---

## 4. 30m technical result

| Metric | L-R1 | J-R1 |
|--------|------|------|
| `cloud_dry_run_completed` | **true** | true |
| `tick_count` / `expected` | **6** / **6** | 6/6 |
| `effective_decision_count` | **24** | 22 |
| `parse_error_count` | **0** | 0 |
| `mock_ai_used_count` | **0** | 0 |
| `order_sent_count` | **0** | 0 |
| `validator_passed` | **true** | true |
| `technical_valid` | **true** | true |
| Provider mix | groq=12, cerebras=12 | groq=12, cerebras=10 |
| Fallback (groq_rate_limited) | 12 | 10 |

`STAGE4_CLOUD_DRY_RUN_MINUTES` reset to **0** confirmed after finalize.

---

## 5. Field compliance result

| Metric | L-R1 | J-R1 | Improved? |
|--------|------|------|-----------|
| `directional_bias_without_candidate_side_count` | **13** | 14 | slight ✓ |
| `missing_paper_fields_count` | **10** | 12 | slight ✓ |
| `entry_trigger_present_count` | **9** | — | new signal |
| `paper_ready_watch_count` | **18** | — | — |
| `valid_watch_candidate_count` (all) | **0** | 0 | ✗ |

### candidate_side_missing_rate_by_symbol

| Symbol | L-R1 | J-R1 |
|--------|------|------|
| BTCUSDT | **1.0** | 1.0 |
| ETHUSDT | **0.67** | 1.0 |
| SOLUSDT | **1.0** | 1.0 |
| PEPEUSDT | **0.2** | 1.0 |

### missing_entry_trigger_rate_by_symbol

| Symbol | L-R1 | J-R1 |
|--------|------|------|
| BTCUSDT | **0.5** | 1.0 |
| ETHUSDT | **1.0** | 1.0 |
| SOLUSDT | **0.2** | 1.0 |
| PEPEUSDT | **0.6** | 1.0 |

**Conclusion:** Partial field-compliance improvement on PEPE/ETH side pairing and BTC/SOL/PEPE triggers. BTC side still 100% missing; ETH trigger still 100% missing; **no symbol produced a valid watch candidate**.

---

## 6. MAE / enforcement result

| Metric | L-R1 | J-R1 |
|--------|------|------|
| `paper_ready_watch_mae_within_cap_count` | **0** | 2 |
| `paper_ready_watch_mae_above_cap_count` | **18** | 13 |
| `mae_above_symbol_cap_count` | **19** | 13 |
| `mae_invalidation_inconsistent_count` | **3** | 1 |
| `within_cap > above_cap` | **FAIL** (0 vs 18) | FAIL (2 vs 13) |

LLM continues outputting MAE 1.0–3.0% on majors (examples specify 0.30%). Dominant block reason: `mae_above_symbol_cap` (19/19 paper intents).

---

## 7. Paper logger result

| Metric | Value |
|--------|-------|
| `paper_logger_events_written` | **23** |
| `paper_logger_watchlist_count` | **0** |
| `paper_logger_hypothetical_entry_count` | **0** |
| `paper_logger_hypothetical_skip_count` | (included in events) |

Output: `/data/stage4_paper_events_418l_r1_enforced`

---

## 8. Calibration replay result

| Metric | Value |
|--------|-------|
| `calibration_total_graduations` | **0** |
| `calibration_btc_graduations` | **0** |
| `calibration_eth_graduations` | **0** |
| `calibration_recommended_mode_for_419` | **none** |
| `watchlist_created` (major_mae_100) | 2 |
| `watchlist_confirmed` | 2 |
| Block reasons | `mae_cap_violation_100pct`=6, `alt_blocked_major_only`=10 |

Output: `/data/stage4_18l_r1_calibration`

---

## 9. Compare J-R1 vs L-R1

| Delta | Value |
|-------|-------|
| `within_cap_delta` | **-13** (regression) |
| `above_cap_delta` | **+5** (worse) |
| `graduation_delta` | **0** |

Output: `/data/stage4_18l_r1_compare_j_r1_vs_l_r1`

---

## 10. Analyzer result

Output: `/data/stage4_18l_r1_failure_analysis`

**Recommendations:**
1. `candidate_side_missing_rate` still high for BTC/SOL/ETH → reinforce side examples
2. `missing_entry_trigger_rate` high for ETH → reinforce trigger examples
3. `valid_watch_candidate_count=0` all symbols → **do not propose 60m**; pursue **418-M** schema repair

---

## 11. Stage 4.19 readiness

| Check | Value |
|-------|-------|
| `stage_419_readiness` | **false** |
| `if_ready_next_step` | N/A — not ready |
| `if_not_ready_recommendation` | **Stage 4.18-M** — schema repair / structured output hardening |

---

## 12. Should 60m be proposed?

**No.** Field compliance improved marginally but `valid_watch_candidate_count=0` and MAE alignment **regressed**. Longer sample will not fix inflated MAE (1.5–3.0%) or missing side on BTC. Operator approval for 60m **not recommended** at this gate.

---

## 13. Safety confirmation

| Check | Value |
|-------|-------|
| `order_sent_count` | 0 |
| `mock_ai_used_count` | 0 |
| `any_exchange_call_made` | false |
| Production / btc-auto / ARM / radar | not touched |
| RG thresholds changed | **NO** |
| Stage 4.19 started | **NO** |
| `STAGE4_CLOUD_DRY_RUN_MINUTES_reset_to_0` | **true** |

---

## 14. Verdict and next step

**`STAGE_4_18L_R1_PARTIAL`** — technical PASS; field compliance marginal; MAE regression; zero graduations.

**PARTIAL type:** Mixed — partial field gains but `valid_watch=0` and MAE worsened → **Type B path: 418-M**, not 60m.

**Next:** **Stage 4.18-M** — schema repair / structured output hardening for `candidate_side`, `entry_trigger`, and MAE scale alignment. Stopped at gate.

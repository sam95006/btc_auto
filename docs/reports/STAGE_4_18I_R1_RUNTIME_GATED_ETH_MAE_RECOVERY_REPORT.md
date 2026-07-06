# Stage 4.18-I-R1 — Runtime-Gated ETH MAE Recovery (30m)

**Date:** 2026-07-06 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Code commit:** `4465130` (418-I)  
**Service:** `nexus-stage3-bybit-demo-learning` (`6a3b81652fdef84a45a2a553`)  
**Output:** `/data/stage4_ai_decisions_418i_r1_eth_mae_recovery_30m`  
**Mode:** read-only 30m dry-run with **418-I runtime** — no execution, no RG changes

---

## 1. Executive summary

30m fixed-fleet regression ran after runtime gate PASS with 418-I prompt (ETH invalidation-distance MAE, BTC confirmation recovery, SOL/PEPE conservative).

**Verdict: PARTIAL**

| Layer | Result |
|-------|--------|
| Runtime version gate | **PASS** |
| Technical soak | **PASS** (6/6 ticks, 22 effective, parse=0, order=0) |
| ETH MAE ≤ 0.35% | **FAIL** (avg **1.15%**, 0 within-cap ETH watches) |
| ETH MAE vs H-R1 | **REGRESSION** (H-R1 avg 0.454%) |
| BTC graduation | **NOT recovered** (0 vs G-R1 1) |
| ETH graduation | **0** |
| `within_cap > above_cap` | **FAIL** (2 vs 15) |
| Stage 4.19 ready | **NO** |

418-I increased skip discipline on ETH (2 watch vs 4 in H-R1) but **did not** bring ETH MAE within cap. Remaining ETH watches averaged **1.15%** — worse than H-R1. BTC avg MAE improved slightly (1.27% vs 1.42%) but graduation still 0.

---

## 2. Runtime version gate

| Check | Result |
|-------|--------|
| Deploy (`npx zeabur deploy`) | Success (image stale; patch used) |
| Manual sync + `/data/stage4_418f_runtime_patch/` | **13 files** (incl. `stage4_mae_regression_compare.py`) |
| `check_stage4_runtime_version.py --gate --apply-patch-dir` | **PASS** |
| `runtime_version_check_passed` | **true** |
| `prompt_hints_present` | **true** (418-F/H/I) |
| `compare_tool_present` | **true** |
| `app_file_stale_suspected` | **false** |

---

## 3. Preflight

| Check | Result |
|-------|--------|
| `can_start_long_soak` | `true` |
| `preflight_probe_call_count` | 2 |
| Stage3 context | `passed=true` |
| `mock_used` | `false` |
| `order_sent` | `false` |
| `debug_log_has_api_key` | `false` |

---

## 4. 30m regression summary

| Metric | I-R1 | H-R1 | G-R1 |
|--------|------|------|------|
| `cloud_dry_run_completed` | **true** | true | true |
| `tick_count` / `expected` | **6** / **6** | 6/6 | 6/6 |
| `effective_decision_count` | **22** | 21 | 22 |
| `parse_error_count` | **0** | 0 | 0 |
| `validator_passed` | **true** | true | true |
| `mock_ai_used_count` | **0** | 0 | 0 |
| `order_sent_count` | **0** | 0 | 0 |
| Provider mix | groq=5, cerebras=17 | groq=5, cerebras=16 | groq=5, cerebras=17 |
| Groq TPM cooldown | **yes** (tick 0) | yes | yes |

### Per-symbol intents (effective)

| Symbol | I-R1 | H-R1 | G-R1 |
|--------|------|------|------|
| BTCUSDT | watch=6 | watch=6 | watch=4, soft_skip=1 |
| ETHUSDT | watch=2, hard=1, soft=1 | **watch=4**, hard=1 | all skip |
| SOLUSDT | watch=3, soft=3 | watch=6 | watch=1, soft=4 |
| PEPEUSDT | watch=6 | watch=3, soft=1 | soft=6 |

---

## 5. MAE distribution vs G-R1 / H-R1

**Validator recomputation (22 effective decisions):**

| Symbol | I-R1 avg | H-R1 avg | G-R1 avg | Cap |
|--------|----------|----------|----------|-----|
| BTCUSDT | **1.268%** | 1.420% | 2.485% | 0.35% |
| ETHUSDT | **1.150%** ↑ | **0.454%** | N/A | 0.35% |
| SOLUSDT | **1.833%** | 2.217% | 2.800% | 0.25% |
| PEPEUSDT | **3.337%** | 2.000% | 0.916% | 0.20% |

| MAE metric | I-R1 | H-R1 | G-R1 |
|------------|------|------|------|
| `paper_ready_watch_mae_within_cap_count` | **2** | 2 | 7 |
| `paper_ready_watch_mae_above_cap_count` | **15** | 17 | 22 |
| `decision_quality_incomplete_count` | **15** | 17 | 32* |
| `mae_invalidation_consistency_fail_count` | 4 | 3 | 2 |

`within_cap (2) < above_cap (15)` — **PASS criterion not met.**

---

## 6. ETH MAE alignment result

| Metric | I-R1 | H-R1 |
|--------|------|------|
| ETH watch intents | **2** | 4 |
| ETH avg MAE | **1.150%** | **0.454%** |
| `eth_watch_mae_within_cap_count` | **0** | 1 |
| `eth_watch_mae_above_cap_count` | **2** | 3 |
| Paper logger ETH events | 4 (all hypothetical_skip) | — |

**418-I did not achieve ETH MAE ≤ 0.35%.** Skip guidance reduced ETH watch yield but remaining watches still report invalidation-distance MAE far above cap. ETH paper logger path: **100% hypothetical_skip** (4/4).

`eth_no_graduation_cause`: **eth_watch_mae_above_0_35pct_cap**

---

## 7. BTC confirmation recovery result

| Metric | I-R1 | H-R1 | G-R1 |
|--------|------|------|------|
| BTC avg MAE | 1.268% | 1.420% | 2.485% |
| `btc_watch_confirmation_candidate_count` | 1 | 1 | 2 |
| `btc_graduation_candidate_count` | 1 | 1 | 2 |
| Calibration BTC graduations | **0** | 0 | **1** |
| Watchlist confirmed | **0** | 0 | 1 |

BTC MAE improved vs H-R1 but **graduation not recovered** — watchlist never confirmed (`watchlist_confirmed=0`).

`btc_graduation_regression_cause`: **watchlist_confirmation_regression; btc_mae_above_cap_or_incomplete_quality**

---

## 8. Paper event logger

**Output:** `/data/stage4_paper_events_418i_r1_llm_mae`

| Metric | I-R1 | H-R1 |
|--------|------|------|
| `events_written` | **22** | 21 |
| `watchlist_count` | **2** | 2 |
| `hypothetical_entry_count` | **0** | 0 |
| `hypothetical_skip_count` | **20** | 19 |
| `excluded_decision_quality_incomplete` | **15** | 17 |

---

## 9. Calibration replay

**Output:** `/data/stage4_18i_r1_llm_mae_calibration`

| Metric | I-R1 | H-R1 | G-R1 |
|--------|------|------|------|
| `calibration_total_graduations` | **0** | 0 | 1 |
| `calibration_btc_graduations` | **0** | 0 | 1 |
| `calibration_eth_graduations` | **0** | 0 | 0 |
| `recommended_mode_for_419` | **none** | none | major_mae_100_llm_mae |

---

## 10. Compare tool output summary

**G-R1 vs I-R1:** `/data/stage4_18i_r1_mae_regression_compare/stage4_18i_compare_summary.json`  
**H-R1 vs I-R1:** `/data/stage4_18i_r1_vs_h_r1_compare/stage4_18i_compare_summary.json`

| Comparison | Key delta |
|------------|-----------|
| vs G-R1 | ETH watch yield +2; graduations -1 (lost BTC grad) |
| vs H-R1 | ETH avg MAE **+0.70%** regression; ETH within-cap 0 vs 1 |
| `watchlist_confirmation_regression_cause` | confirmation_window_or_side_missing; MAE above cap |

---

## 11. Whether Stage 4.19 is ready

**NOT READY**

| Criterion | Met? |
|-----------|------|
| Runtime gate PASS | ✅ |
| Technical soak PASS | ✅ |
| `within_cap > above_cap` | ❌ |
| BTC graduation > 0 | ❌ |
| ETH graduation > 0 | ❌ |
| ETH MAE ≤ 0.35% | ❌ |
| `recommended_mode_for_419 != none` | ❌ |

---

## 12. Safety confirmation

| Check | Value |
|-------|-------|
| `order_sent_count` | 0 |
| `mock_ai_used_count` | 0 |
| `STAGE4_CLOUD_DRY_RUN_MINUTES` reset | **0** (confirmed) |
| Production / btc-auto / ARM / radar | not touched |
| Stage 4.19 auto-started | **NO** |

---

## 13. PASS / PARTIAL / FAIL

| Criterion | Met? |
|-----------|------|
| Runtime + technical PASS | ✅ |
| Quality improved vs H-R1 | ❌ (ETH MAE regression) |
| Graduations / cap alignment | ❌ |

**`final_verdict`:** `STAGE_4_18I_R1_PARTIAL`

**`if_not_ready_recommendation`:** Investigate why 418-I skip guidance reduced ETH watches but **increased** ETH MAE on survivors (invalidation_price too wide / LLM not tying MAE to tight stops). Consider **418-J**: schema-level post-parse MAE cap enforcement + tighter ETH invalidation examples in prompt; re-run 30m. Do not loosen RG thresholds.

**Stopped at gate. Stage 4.19 not started.**

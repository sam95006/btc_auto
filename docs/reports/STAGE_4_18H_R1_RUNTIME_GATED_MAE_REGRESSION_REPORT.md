# Stage 4.18-H-R1 — Runtime-Gated MAE Regression (30m)

**Date:** 2026-07-06 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Code commit:** `e92ecdb` (418-H)  
**Service:** `nexus-stage3-bybit-demo-learning` (`6a3b81652fdef84a45a2a553`)  
**Output:** `/data/stage4_ai_decisions_418h_r1_mae_prompt_regression_30m`  
**Mode:** read-only 30m dry-run with **418-H runtime gate** — no execution, no RG changes

---

## 1. Executive summary

30m fixed-fleet regression ran with **418-H prompt** after runtime version gate PASS (manual sync + `/data/stage4_418f_runtime_patch/` + entrypoint re-apply).

**Verdict: PARTIAL**

| Layer | Result |
|-------|--------|
| Runtime version gate | **PASS** |
| Technical soak | **PASS** (6/6 ticks, 21 effective, parse=0, order=0) |
| ETH watch yield | **Improved** (4 ETH watches, avg MAE 0.45%) |
| MAE cap alignment (`within > above`) | **FAIL** (2 vs 17) |
| Calibration graduations | **0** (BTC=0, ETH=0) |
| Stage 4.19 ready | **NO** |

418-H ETH guidance produced directional watches with materially lower ETH MAE vs 4.18-G-R1, but BTC/SOL MAE remain high and **no** hypothetical graduations occurred.

---

## 2. Runtime version gate

| Check | Result |
|-------|--------|
| Deploy (`npx zeabur deploy`) | Success (image still stale) |
| Manual sync + `/data/stage4_418f_runtime_patch/` | 12 files |
| `check_stage4_runtime_version.py --gate --apply-patch-dir` | **PASS** |
| `runtime_version_check_passed` | **true** |
| `prompt_hints_present` | **true** (418-F + 418-H) |
| `mae_analysis_script_present` | **true** |
| `build_mae_metrics_present` | **true** |
| `app_file_stale_suspected` | **false** |

Entrypoint `STAGE4_APPLY_RUNTIME_PATCH=true` + `STAGE4_REQUIRE_RUNTIME_VERSION_CHECK=true` enforced before soak.

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

| Metric | 4.18-H-R1 | 4.18-G-R1 | 4.18-H target |
|--------|-----------|-----------|---------------|
| `cloud_dry_run_completed` | **true** | true | true |
| `tick_count` / `expected` | **6** / **6** | 6/6 | 6/6 |
| `effective_decision_count` | **21** | 22 | ≥20 |
| `parse_error_count` | **0** | 0 | 0 |
| `validator_passed` | **true** | true | true |
| `mock_ai_used_count` | **0** | 0 | 0 |
| `order_sent_count` | **0** | 0 | 0 |
| `paper_ready_watch_count` (summary) | **19** | 3 | — |
| `decision_quality_incomplete_count` (summary) | **0** | 2 | — |
| Provider mix | groq=5, cerebras=16 | groq=5, cerebras=17 | — |

### Per-symbol intents (effective)

| Symbol | H-R1 | G-R1 |
|--------|------|------|
| BTCUSDT | watch=6 | watch=4, soft_skip=1 |
| ETHUSDT | **watch=4**, hard_skip=1 | hard/soft skip only |
| SOLUSDT | watch=6 | watch=1, soft_skip=4 |
| PEPEUSDT | watch=3, soft_skip=1 | soft_skip=6 |

**ETH yield improved:** 4 watch intents with `directional_bias` + MAE fields (vs 0 MAE-bearing ETH in G-R1).

---

## 5. MAE distribution vs 4.18-G-R1

**Validator / analysis recomputation on 21 effective decisions:**

| Symbol | H-R1 avg | G-R1 avg | Cap | Improved? |
|--------|----------|----------|-----|-----------|
| BTCUSDT | **1.420%** | 2.485% | 0.35% | ✅ lower |
| ETHUSDT | **0.454%** | N/A | 0.35% | ✅ now present + lower |
| SOLUSDT | **2.217%** | 2.800% | 0.25% | ✅ slightly lower |
| PEPEUSDT | **2.000%** | 0.916% | 0.20% | ❌ higher |

| MAE metric | H-R1 | G-R1 |
|------------|------|------|
| `mae_estimate_scale_valid_count` | 19 | 41* |
| `mae_estimate_scale_invalid_count` | 0 | 1 |
| `paper_ready_watch_mae_within_cap_count` | **2** | 7 |
| `paper_ready_watch_mae_above_cap_count` | **17** | 22 |
| `recomputed_incomplete_count` | 17 | 32* |
| `mae_invalidation_consistency_fail_count` | 3 | 2 |

\*G-R1 validator counted all jsonl lines (74); H-R1 has 21 effective-only lines.

`within_cap (2) < above_cap (17)` — **PASS criterion not met.**

---

## 6. ETH candidate / graduation result

| Metric | H-R1 | G-R1 |
|--------|------|------|
| ETH effective decisions | 5 | 6 |
| ETH watch intents | **4** | 0 (all skip) |
| ETH avg MAE | **0.454%** | N/A |
| ETH ticks above 0.35% cap | 3 of 4 MAE ticks | — |
| `calibration_eth_graduations` | **0** | 0 |

ETH **directional yield** improved under 418-H, but MAE still exceeds paper cap on most ETH watches → validator marks incomplete → no ETH graduation.

---

## 7. Paper event logger

**Output:** `/data/stage4_paper_events_418h_r1_llm_mae`

| Metric | H-R1 | G-R1 |
|--------|------|------|
| `events_written` | **21** | 74 |
| `watchlist_count` | **2** | 6 |
| `hypothetical_entry_count` | **0** | 0 |
| `hypothetical_skip_count` | **19** | 68 |

Watchlists created but **0 confirmed** in calibration replay (vs G-R1: 1 confirmed → 1 BTC graduation).

---

## 8. Calibration replay

**Output:** `/data/stage4_18h_r1_llm_mae_calibration`

| Metric | H-R1 | G-R1 |
|--------|------|------|
| `calibration_total_graduations` | **0** | 1 |
| `calibration_btc_graduations` | **0** | 1 |
| `calibration_eth_graduations` | **0** | 0 |
| `recommended_mode_for_419` | **none** | `major_mae_100_llm_mae` |
| `major_mae_100_llm_mae` graduations | 0 | 1 |

Regression vs G-R1: fewer watchlists passed confirmation; no LLM-MAE graduation despite ETH watches.

---

## 9. Whether Stage 4.19 is ready

**NOT READY**

| Criterion | Met? |
|-----------|------|
| Runtime gate PASS | ✅ |
| Technical soak PASS | ✅ |
| `within_cap > above_cap` | ❌ (2 vs 17) |
| BTC graduation > 0 | ❌ |
| ETH graduation > 0 | ❌ |
| `recommended_mode_for_419 != none` | ❌ |

Formal RG thresholds **unchanged**. Do **not** start Stage 4.19.

---

## 10. Safety confirmation

| Check | Value |
|-------|-------|
| `order_sent_count` | 0 |
| `mock_ai_used_count` | 0 |
| `any_exchange_call_made` | false |
| `STAGE4_CLOUD_DRY_RUN_MINUTES` reset | **0** (confirmed) |
| Production / btc-auto / ARM / radar | not touched |
| Stage 4.19 auto-started | **NO** |

---

## 11. PASS / PARTIAL / FAIL

| Criterion | Met? |
|-----------|------|
| Runtime gate PASS | ✅ |
| Technical soak PASS | ✅ |
| `within_cap > above_cap` | ❌ |
| BTC + ETH graduation > 0 | ❌ |
| Quality improved vs G-R1 | **partial** (ETH yield, BTC/ETH MAE down; graduations lost) |

**`final_verdict`:** `STAGE_4_18H_R1_PARTIAL`

**`if_not_ready_recommendation`:** Targeted **418-I** ETH MAE cap alignment (ensure ETH watches with bias keep MAE ≤0.35% via invalidation-tied estimates); investigate watchlist confirmation regression; re-run 30m after patch. Require BTC **and** ETH graduation before 4.19.

**`if_ready_next_step`:** N/A — not ready.

---

**Stopped at gate. Stage 4.19 not started.**

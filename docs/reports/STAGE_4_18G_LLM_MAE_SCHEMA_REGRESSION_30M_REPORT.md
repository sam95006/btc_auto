# Stage 4.18-G — LLM MAE Schema Regression (30m)

**Date:** 2026-07-06 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Deploy commit:** `efefb36` (package sync) / 418F code `2474a28`  
**Service:** `nexus-stage3-bybit-demo-learning` (`6a3b81652fdef84a45a2a553`)  
**Output:** `/data/stage4_ai_decisions_418g_llm_mae_schema_regression_30m`  
**Mode:** read-only 30m dry-run — **no execution, no RG changes**

---

## 1. Executive summary

30m fixed-fleet read-only regression **completed technically** (6/6 ticks, 22 effective decisions, zero parse errors, zero orders). Real LLM produced watch intents with paper-readiness fields populated.

**Verdict: PARTIAL**

| Layer | Result |
|-------|--------|
| Technical soak | **PASS** |
| 418F prompt deployed in container | **FAIL** (deploy drift) |
| MAE cap alignment vs 4.18-D | **FAIL** (0 within-cap, 18 above-cap) |
| Calibration graduations | **0** |
| Stage 4.19 ready | **NO** |

**Critical finding:** Post-soak container inspection shows **418F code was not present** at runtime (`stage4_mae_calibration_analysis.py` missing; `stage4_prompt_builder.py` has no `4.18-F` hints; `stage4_paper_readiness.py` lacks `build_mae_calibration_metrics`). The soak therefore exercised **pre-418F prompt behavior**, not the calibrated MAE scale hints. Results are **inconclusive for prompt validation** until 418F files are synced and regression re-run.

---

## 2. Runtime / preflight

| Check | Result |
|-------|--------|
| `/app` exists | ✅ |
| `npx zeabur deploy` from `deploy/zeabur_stage3_demo_learning` | ✅ |
| **418F prompt hints in container** | ❌ (`grep 4.18-F` → 0) |
| **`stage4_mae_calibration_analysis.py` in container** | ❌ |
| **`build_mae_calibration_metrics` in container** | ❌ |
| `STAGE4_ORDER_ALLOWED` | `false` |
| `STAGE4_ALLOW_MOCK_FALLBACK` | `false` |
| Provider capacity `can_start_long_soak` | `true` |
| `preflight_probe_call_count` | 2 |
| Stage3 context seed | `passed=true` |
| `mock_used` | `false` |
| `order_sent` | `false` |

**Note:** Zeabur in-place deploy reported success but runtime image did not pick up 418F files from `efefb36` package. Manual base64 sync (as used in 4.18-E) is required before the next MAE regression soak.

---

## 3. 30m regression summary

| Metric | Value |
|--------|-------|
| `cloud_dry_run_completed` | **true** |
| `tick_count` / `expected_tick_count` | **6** / **6** |
| `effective_decision_count` | **22** (target ≥20) |
| `parse_error_count` | **0** |
| `validator_passed` | **true** |
| `technical_valid` | **true** |
| `mock_ai_used_count` | **0** |
| `order_sent_count` | **0** |
| `real_llm_used_count` | **22** |
| Provider mix | groq=12, cerebras=10 (10 groq_rate_limited fallbacks) |
| `skipped_tick_count` | 2 (ETH + PEPE chain fail, 1 tick each) |

### Per-symbol intent distribution

| Symbol | Effective | Intents |
|--------|-----------|---------|
| BTCUSDT | 6 | watch=6 |
| ETHUSDT | 5 | soft_skip=4, hard_skip=1 |
| SOLUSDT | 6 | watch=6 |
| PEPEUSDT | 5 | watch=4, enter_candidate=1 |

### Paper-readiness (summary.json)

| Metric | 4.18-G | 4.18-D |
|--------|--------|--------|
| `directional_bias_present_count` | 17 | 16 |
| `paper_ready_watch_count` | 15 | 16 |
| `decision_quality_incomplete_count` | **1** | 0 |
| `mae_risk_estimate_present_count` | 17 | 16 |

Validator recompute: `paper_ready_watch_count=18`, `decision_quality_incomplete_count=1`.

---

## 4. MAE distribution vs 4.18-D

**Analysis method:** In-container JSONL probe (418F analysis script not deployed).

| Symbol | 4.18-G avg | 4.18-G min–max | 4.18-D avg | Cap |
|--------|------------|----------------|------------|-----|
| BTCUSDT | **1.357%** | 0.5–1.5% | 1.45% | 0.35% |
| ETHUSDT | **N/A** | (no MAE ticks; all skip intents) | — | 0.35% |
| SOLUSDT | **2.171%** | 1.2–3.0% | 1.70% | 0.25% |
| PEPEUSDT | **2.083%** | 2.0–2.5% | 1.255% | 0.20% |

| MAE metric | 4.18-G | 4.18-D (418F offline replay) |
|------------|--------|-------------------------------|
| `mae_estimate_scale_valid_count` | **20** | 16 |
| `mae_estimate_scale_invalid_count` | **0** | 0 |
| `mae_estimate_above_symbol_cap_count` | **20** | 16 |
| `paper_ready_watch_mae_within_cap_count` | **0** | 1 |
| `paper_ready_watch_mae_above_cap_count` | **18** | 15 |
| `mae_invalidation_consistency_fail_count` | **2** | 0 |

**Conclusion:** BTC average MAE dropped slightly (~6%) but remains **~4× paper cap**. SOL and PEPE averages **increased**. Zero paper-ready watches have MAE within cap. Scale units remain valid percent (none >5%) but magnitudes are still unsuitable for paper graduation.

---

## 5. Paper readiness metrics

- All 20 MAE-bearing ticks are **above symbol cap**.
- `paper_ready_watch_mae_within_cap_count` (0) **<** `paper_ready_watch_mae_above_cap_count` (18) → **PASS criterion not met**.
- With 418F validator rules applied offline, most high-MAE watches would be `decision_quality_incomplete` (as seen in 418F replay on 418D: 15/16).

---

## 6. Paper event logger (4.18-G)

**Output:** `/data/stage4_paper_events_418g_llm_mae`

| Metric | 4.18-G | 4.18-D | 4.18-E |
|--------|--------|--------|--------|
| `events_written` | **25** | 23 | 23 |
| `watchlist_count` | **1** | 0 | 1 |
| `hypothetical_entry_count` | **0** | 0 | 0 |
| `hypothetical_skip_count` | **24** | 23 | 22 |

Watchlist creation improved vs 4.18-D (0→1) but remains blocked by MAE cap violations on BTC/ETH confirmation path.

---

## 7. Calibration replay (4.18-G)

**Output:** `/data/stage4_18g_llm_mae_calibration`

| Metric | Value |
|--------|-------|
| `calibration_total_graduations` | **0** |
| `calibration_btc_graduations` | **0** |
| `calibration_eth_graduations` | **0** |
| `recommended_mode_for_419` | **none** |
| Primary blockers | `mae_cap_violation_*` (5/mode), `alt_blocked_major_only_calibration` (13/mode) |

All five MAE modes (75/90/100% + side-memory + conf-floor) produced **0 hypothetical graduations**.

---

## 8. Whether MAE calibration improved

**`mae_calibration_improved=false`** (mixed at best)

| Signal | Improved? |
|--------|-----------|
| BTC avg MAE lower than 4.18-D | ✅ marginally (1.45→1.357) |
| ETH avg MAE lower | N/A (no MAE output) |
| SOL/PEPE avg MAE lower | ❌ worse |
| `paper_ready_watch_mae_within_cap_count` increased | ❌ (1→0 vs 418F replay baseline) |
| `calibration_total_graduations` > 0 | ❌ |

**`quality_improved=partial`** — watchlist_count 0→1 and `decision_quality_incomplete` low at summary layer, but cap alignment did not improve.

---

## 9. Stage 4.19 readiness

**`stage_419_readiness=false`**

- `calibration_total_graduations=0`
- BTC/ETH graduation=0
- `recommended_mode_for_419=none`
- Formal Risk Governor thresholds **unchanged**

**`if_not_ready_recommendation`:** (1) Manual-sync 418F deploy files into container and verify `grep 4.18-F` + `stage4_mae_calibration_analysis.py` before any re-soak. (2) Re-run 30m regression (418-G retry or 418-H) with confirmed 418F prompt. (3) If MAE still above cap, tighten prompt examples / add post-LLM MAE clamp in schema repair (design-only, not RG). Do **not** loosen formal RG MAE thresholds.

---

## 10. Safety confirmation

| Check | Value |
|-------|-------|
| `mock_ai_used_count` | 0 |
| `order_sent_count` | 0 |
| `any_exchange_call_made` | false |
| `demo_order_enabled` | false |
| `paper_order_execution_enabled` | false |
| `arm_enabled` | false |
| `radar_enabled` | false |
| `production_touched` | false |
| `btc_auto_touched` | false |
| `STAGE4_CLOUD_DRY_RUN_MINUTES` reset | **0** (confirmed) |
| Formal RG thresholds changed | **NO** |
| `applied_patches` | **NO** |
| Stage 4.19 auto-started | **NO** |

---

## 11. Explicit non-execution statement

No orders, demo orders, paper execution, ARM, radar, production/btc-auto, 6h/24h soak, exchange private API calls, or Risk Governor threshold changes. Read-only dry-run and offline replay only.

---

## 12. PASS / PARTIAL / FAIL criteria

| Criterion | Met? |
|-----------|------|
| `cloud_dry_run_completed=true` | ✅ |
| `tick_count=6`, `expected_tick_count=6` | ✅ |
| `effective_decision_count >= 20` | ✅ (22) |
| `parse_error_count=0` | ✅ |
| `validator_passed=true` | ✅ |
| `technical_valid=true` | ✅ |
| `mae_estimate_scale_invalid_count=0` | ✅ |
| `paper_ready_watch_mae_within_cap > above_cap` | ❌ (0 vs 18) |
| `mock_ai_used_count=0` | ✅ |
| `order_sent_count=0` | ✅ |
| `STAGE4_CLOUD_DRY_RUN_MINUTES_reset_to_0` | ✅ |
| `calibration_total_graduations > 0` | ❌ |
| 418F prompt actually deployed | ❌ |

**`final_verdict`:** `STAGE_4_18G_PARTIAL` — technical regression PASS; MAE cap alignment FAIL; deploy drift invalidates prompt-validation claim; **stopped at gate, Stage 4.19 not started**.

**`next_step_recommendation`:** Sync 418F runtime files → verify gate → re-run 30m MAE regression before considering 4.19 offline paper exit evaluation.

---

## 13. Tests (local, unchanged code)

```bash
python -m unittest tests.test_stage4_ai_decision_layer tests.test_stage4_paper_event_logger tests.test_stage4_watchlist_followup_simulator -q
```

**Result:** 243/243 passed.

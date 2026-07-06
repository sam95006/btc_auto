# Stage 4.18-G-R1 — Runtime Sync Verification + MAE Regression (30m)

**Date:** 2026-07-06 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Prior report:** `eb82859` (invalid 4.18-G — deploy drift)  
**Service:** `nexus-stage3-bybit-demo-learning` (`6a3b81652fdef84a45a2a553`)  
**Output:** `/data/stage4_ai_decisions_418g_r1_llm_mae_schema_regression_30m`  
**Mode:** read-only 30m dry-run with **418F runtime verified** — no execution, no RG changes

---

## 1. Executive summary

Stage 4.18-G-R1 fixed **Zeabur deploy drift** via manual base64 sync of 418F research files to `/app` (persisted to `/data/stage4_418f_runtime_patch/`), verified runtime gate, then ran a **valid** 30m fixed-fleet read-only soak with real LLM.

**Verdict: PARTIAL**

| Layer | Result |
|-------|--------|
| Deploy drift remediated | **YES** (manual sync; Zeabur deploy alone insufficient) |
| Runtime gate (418F code) | **PASS** |
| Technical soak | **PASS** (6/6 ticks, 22 effective, parse=0, order=0) |
| MAE cap alignment (`within_cap > above_cap`) | **FAIL** (7 vs 22) |
| Calibration graduations | **1** (BTC only, `major_mae_100_llm_mae`) |
| Stage 4.19 ready | **NO** (ETH graduation=0; operator gate not met) |

This soak **did** exercise the 418F calibrated prompt. The LLM shifted behavior: fewer paper-ready watches (3 vs 15–18 in invalid 4.18-G), more soft/hard skips, and **one** hypothetical BTC graduation under LLM-MAE calibration mode — but majors are still mostly above paper caps.

---

## 2. Deploy drift root cause

| Issue | Detail |
|-------|--------|
| Symptom (4.18-G) | `npx zeabur deploy` reported success but container kept **418C-era** `/app/tools/research/` (12K `stage4_paper_readiness.py`, no `stage4_mae_calibration_analysis.py`) |
| Local package | `deploy/zeabur_stage3_demo_learning` **already contained** 418F files (`efefb36`) |
| Root cause | Zeabur in-place deploy does not reliably refresh `/app` runtime; **restart wipes** any ephemeral `/app` edits |
| R1 fix | `tools/research/sync_418f_runtime_to_zeabur.py` — chunked base64 upload of 11 files; copy to `/data/stage4_418f_runtime_patch/` for persistence; re-apply before soak/post-processing |
| Soak launch | Manual `nohup` dry-run (not entrypoint restart) to preserve patched code |

---

## 3. Runtime gate verification

| Check | Result |
|-------|--------|
| `stage4_mae_calibration_analysis.py` | ✅ 6.8K |
| `stage4_paper_guard_inputs.py` | ✅ 2.9K |
| `stage4_paper_readiness.py` | ✅ **16K** (was 12K pre-sync) |
| `grep build_mae_calibration_metrics` | ✅ count=2 |
| `grep "0.25 = 0.25%"` prompt hints | ✅ present in synced `stage4_prompt_builder.py` |
| `imports_ok` / `get_paper_mae_pct` / `main` / `build_mae_calibration_metrics` | ✅ **True True True** |
| `STAGE4_ORDER_ALLOWED` | `false` |
| `STAGE4_ALLOW_MOCK_FALLBACK` | `false` |

**`runtime_gate_passed=true`**

---

## 4. Preflight

| Check | Result |
|-------|--------|
| `can_start_long_soak` | `true` |
| `preflight_probe_call_count` | 2 |
| Stage3 context | `passed=true` |
| `mock_used` | `false` |
| `order_sent` | `false` |
| `debug_log_has_api_key` | `false` |

---

## 5. 30m regression summary

| Metric | 4.18-G-R1 | Invalid 4.18-G | 4.18-D |
|--------|-----------|----------------|--------|
| `cloud_dry_run_completed` | **true** | true | true |
| `tick_count` / `expected` | **6** / **6** | 6/6 | 6/6 |
| `effective_decision_count` | **22** | 22 | 23 |
| `parse_error_count` | **0** | 0 | 0 |
| `validator_passed` | **true** | true | true |
| `mock_ai_used_count` | **0** | 0 | 0 |
| `order_sent_count` | **0** | 0 | 0 |
| `paper_ready_watch_count` (summary) | **3** | 15 | 16 |
| `decision_quality_incomplete_count` (summary) | **2** | 1 | 0 |
| Provider mix | groq=5, cerebras=17 | groq=12, cerebras=10 | groq=12, cerebras=11 |

### Intent shift (418F prompt effect)

| Symbol | R1 intents | Invalid 4.18-G |
|--------|------------|----------------|
| BTCUSDT | watch=4, soft_skip=1 | watch=6 |
| ETHUSDT | hard_skip=4, soft_skip=2 | soft/hard skip |
| SOLUSDT | watch=1, soft_skip=4 | watch=6 |
| PEPEUSDT | soft_skip=6 | watch=4, enter=1 |

418F prompt **reduced** paper-ready watch yield (expected when MAE too high → skip/downgrade).

---

## 6. MAE distribution vs 4.18-D / invalid 4.18-G

**Source:** `stage4_18g_r1_mae_calibration_analysis/stage4_18f_mae_distribution.json` + validator (all jsonl lines).

| Symbol | R1 avg | Invalid 4.18-G avg | 4.18-D avg | Cap |
|--------|--------|-------------------|------------|-----|
| BTCUSDT | **2.485%** | 1.357% | 1.45% | 0.35% |
| ETHUSDT | **N/A** | N/A | — | 0.35% |
| SOLUSDT | **2.800%** | 2.171% | 1.70% | 0.25% |
| PEPEUSDT | **0.916%** | 2.083% | 1.255% | 0.20% |

| MAE metric | R1 | Invalid 4.18-G | 4.18-F replay (418D) |
|------------|-----|----------------|----------------------|
| `mae_estimate_scale_valid_count` | 41 | 20 | 16 |
| `mae_estimate_scale_invalid_count` | **1** | 0 | 0 |
| `mae_estimate_above_symbol_cap_count` | 27 | 20 | 16 |
| `paper_ready_watch_mae_within_cap_count` | **7** | 0 | 1 |
| `paper_ready_watch_mae_above_cap_count` | 22 | 18 | 15 |
| `mae_invalidation_consistency_fail_count` | 2 | 2 | 0 |
| `recomputed_incomplete_count` | 32 | — | 15 |

**Interpretation:** 418F prompt **increased** `within_cap` from 0→7 and improved PEPE averages, but BTC/SOL averages **worsened** vs invalid 4.18-G. `within_cap (7) < above_cap (22)` — full PASS criterion not met.

---

## 7. Paper event logger

**Output:** `/data/stage4_paper_events_418g_r1_llm_mae`

| Metric | R1 | Invalid 4.18-G | 4.18-D |
|--------|-----|----------------|--------|
| `events_written` | **74** | 25 | 23 |
| `watchlist_count` | **6** | 1 | 0 |
| `hypothetical_entry_count` | **0** | 0 | 0 |
| `hypothetical_skip_count` | **68** | 24 | 23 |

Watchlist creation **improved** (6 vs 1 vs 0) but still no hypothetical entries.

---

## 8. Calibration replay

**Output:** `/data/stage4_18g_r1_llm_mae_calibration`

| Metric | Value |
|--------|-------|
| `recommended_mode_for_419` | **`major_mae_100_llm_mae`** |
| `calibration_total_graduations` | **1** (`major_mae_100_llm_mae` and variants) |
| `calibration_btc_graduations` | **1** |
| `calibration_eth_graduations` | **0** |
| Legacy proxy modes | 0 graduations (mae_cap_violation) |
| LLM MAE modes | **1** BTC graduation @ conf 0.62 |

**`stage_419_readiness=false`** — operator gate requires **BTC and ETH** graduation > 0; only BTC graduated. Do **not** auto-start Stage 4.19.

---

## 9. Whether 418F prompt improved MAE

**`mae_calibration_improved=partial`**

| Signal | Improved? |
|--------|-----------|
| Runtime actually used 418F | ✅ |
| `paper_ready_watch_mae_within_cap_count` vs invalid 4.18-G | ✅ 0→7 |
| PEPE avg MAE lower | ✅ 2.08→0.92 |
| BTC avg MAE lower | ❌ 1.36→2.48 |
| SOL avg MAE lower | ❌ 2.17→2.80 |
| `within_cap > above_cap` | ❌ |
| First non-zero LLM-MAE graduation | ✅ 1 BTC |

**`quality_improved=true`** at pipeline level (watchlists 6, within_cap up, 1 graduation) but **not sufficient** for Stage 4.19.

---

## 10. Stage 4.19 readiness

**NOT READY**

- `calibration_eth_graduations=0`
- Majority of paper-ready watches still above cap
- Formal RG thresholds **unchanged**

**`if_not_ready_recommendation`:** (1) Fix Zeabur GitHub bind / deploy pipeline so 418F ships without manual sync. (2) Optional 418-H: prompt tuning iteration focusing on BTC/SOL MAE scale (not RG loosening). (3) Re-run 30m regression after deploy pipeline fix. (4) Require **both** BTC and ETH graduation > 0 before 4.19 offline paper exit evaluation.

---

## 11. Safety confirmation

| Check | Value |
|-------|-------|
| `order_sent_count` | 0 |
| `mock_ai_used_count` | 0 |
| `any_exchange_call_made` | false |
| `STAGE4_CLOUD_DRY_RUN_MINUTES` reset | **0** (confirmed) |
| Production / btc-auto / ARM / radar | **not touched** |
| RG thresholds changed | **NO** |
| Stage 4.19 auto-started | **NO** |

---

## 12. PASS / PARTIAL / FAIL

| Criterion | Met? |
|-----------|------|
| `runtime_gate_passed` | ✅ |
| 418F prompt hints present | ✅ |
| `stage4_mae_calibration_analysis.py` present | ✅ |
| `build_mae_calibration_metrics` present | ✅ |
| Technical soak PASS | ✅ |
| `paper_ready_watch_mae_within_cap > above_cap` | ❌ (7 vs 22) |
| `calibration_total_graduations > 0` | ✅ (1) |
| BTC **and** ETH graduation > 0 | ❌ |
| Stage 4.19 operator gate | ❌ |

**`final_verdict`:** `STAGE_4_18G_R1_PARTIAL` — runtime sync + valid 418F soak PASS; MAE cap alignment incomplete; 1 BTC graduation only. **Stopped at gate.**

**`next_step_recommendation`:** Fix deploy pipeline; consider 418-H prompt iteration for BTC/SOL MAE; require ETH graduation before 4.19.

---

## 13. Tests (local, unchanged)

```bash
python -m unittest tests.test_stage4_ai_decision_layer tests.test_stage4_paper_event_logger tests.test_stage4_watchlist_followup_simulator -q
```

**Result:** 243/243 passed.

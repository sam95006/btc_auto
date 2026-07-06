# Stage 4.18-J-R1 — Runtime-Gated Schema-Enforced 30m Regression

**Date:** 2026-07-06 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Prior commit:** `d080162` (418-J)  
**Output:** `/data/stage4_ai_decisions_418j_r1_schema_enforced_regression_30m`  
**Mode:** read-only 30m dry-run with **418-J** runtime + schema enforcement — no orders

---

## 1. Executive summary

**Verdict: PARTIAL**

| Layer | Result |
|-------|--------|
| Runtime version gate | **PASS** (418-J hints, schema enforcement, compare tool) |
| Preflight | **PASS** (`can_start_long_soak=true`, probe=2) |
| Technical soak | **PASS** (6/6 ticks, 22 effective, parse=0, order=0) |
| `within_cap > above_cap` | **FAIL** (2 vs 13) |
| BTC / ETH graduations | **0** |
| `recommended_mode_for_419` | **none** |
| Stage 4.19 | **NOT started** |

418-J schema enforcement is active in runtime. ETH within-cap watches improved (**1** vs I-R1 **0**), but MAE cap alignment and confirmation graduation remain insufficient.

---

## 2. Runtime gate

| Check | Result |
|-------|--------|
| `runtime_version_check_passed` | **true** |
| `prompt_hints_present` | **true** (418-F/H/I/J) |
| `schema_enforcement_present` | **true** |
| `compare_tool_present` | **true** |
| `app_file_stale_suspected` | **false** |
| Patch dir | `/data/stage4_418f_runtime_patch/` (13 files) |

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

## 4. 30m regression summary

| Metric | J-R1 | I-R1 | G-R1 |
|--------|------|------|------|
| `cloud_dry_run_completed` | **true** | true | true |
| `tick_count` / `expected` | **6** / **6** | 6/6 | 6/6 |
| `effective_decision_count` | **22** | 22 | 22 |
| `parse_error_count` | **0** | 0 | 0 |
| `mock_ai_used_count` | **0** | 0 | 0 |
| `order_sent_count` | **0** | 0 | 0 |
| Provider mix | groq=12, cerebras=10 | groq=5, cerebras=17 | — |
| Fallback used | 10 | — | — |
| PEPE tick 6 | provider_chain_failed (skipped) | — | — |

Dry-run log: `completed=True`, `parse_errors=0`, `order_sent_count=0`.

---

## 5. MAE / enforcement metrics (418-J re-assessment)

| Metric | J-R1 | I-R1 |
|--------|------|------|
| `paper_ready_watch_mae_within_cap_count` | **2** | 2 |
| `paper_ready_watch_mae_above_cap_count` | **13** | 15 |
| `mae_above_symbol_cap_count` | **13** | 15 |
| `mae_invalidation_inconsistent_count` | **1** | 4 |
| `missing_paper_fields_count` | **12** | 12 |
| `directional_bias_without_candidate_side_count` | **14** | 7 |
| ETH watch count | **3** | 2 |
| ETH within-cap watches | **1** | 0 |
| ETH avg MAE | **~1.17%** | 1.15% |

`within_cap (2) < above_cap (13)` — **PASS criterion not met.**

---

## 6. Paper event logger

**Output:** `/data/stage4_paper_events_418j_r1_enforced`

| Metric | J-R1 |
|--------|------|
| Enforcement blocks | `mae_above_symbol_cap=13`, `missing_paper_fields=1` (primary) |
| Watchlist / skip mix | `hypothetical_skip=12`, `watchlist_pending_confirmation=1` |

Schema enforcement correctly blocks most paper-ready watches that exceed cap or lack fields.

---

## 7. Calibration replay

**Output:** `/data/stage4_18j_r1_calibration`

| Metric | J-R1 |
|--------|------|
| `recommended_mode_for_419` | **none** |
| `calibration_total_graduations` | **0** |
| `calibration_btc_graduations` | **0** |
| `calibration_eth_graduations` | **0** |
| Graduation candidates jsonl | **0 lines** |

---

## 8. Compare summaries

**G-R1 vs J-R1:** `/data/stage4_18j_r1_compare_g_r1_vs_j_r1`  
**I-R1 vs J-R1:** `/data/stage4_18j_r1_compare_i_r1_vs_j_r1`

| Comparison | Key delta |
|------------|-----------|
| vs I-R1 | ETH within-cap **0→1**; `mae_invalidation_inconsistent` **4→1**; still 0 graduations |
| vs G-R1 | Lost historical BTC graduation path under stricter field requirements |
| Breakdown | `mae_above_cap=13`, `quality_incomplete`, `side_missing_on_confirmation` |

---

## 9. Stage 4.19 readiness

**NOT READY** — BTC graduation=0, ETH graduation=0, `within_cap <= above_cap`, `recommended_mode_for_419=none`.

**Stage 4.19 offline paper exit evaluation was NOT started.**

---

## 10. Safety confirmation

| Check | Value |
|-------|-------|
| `STAGE4_CLOUD_DRY_RUN_MINUTES` reset | **0** (confirmed post-soak) |
| `order_sent_count` | 0 |
| `mock_ai_used_count` | 0 |
| `any_exchange_call_made` | false |
| Production / btc-auto / ARM / radar | **not touched** |
| RG thresholds changed | **NO** |

---

## 11. Verdict

**`STAGE_4_18J_R1_PARTIAL`** — runtime + technical PASS; quality gate FAIL.

**Next:** Stage 4.18-K diagnostics (code-only) — see `STAGE_4_18K_DIAGNOSTICS_AFTER_418J_R1.md`. Do **not** start Stage 4.19 until BTC **and** ETH graduation > 0 with `within_cap > above_cap`.

# Stage 4.18-N-R2 — 60m Read-Only Provider Schema Stability Sample

**Date:** 2026-07-09 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Code / deploy base:** `8230f73` (418-N) + redeploy `ab3fc0b`  
**Output:** `/data/stage4_ai_decisions_418n_r2_provider_schema_60m`  
**Baseline compare:** N-R1 `/data/stage4_ai_decisions_418n_r1_provider_schema_30m`  
**Mode:** read-only 60m dry-run — **no orders**

---

## 1. Executive summary

**Verdict: `STAGE_4_18N_R2_PARTIAL_A`**

| Layer | Result |
|-------|--------|
| Runtime version gate | **PASS** (`stage_marker=4.18-N`) |
| Preflight | **PASS** (probe=2) |
| Technical 60m soak | **PASS** (12/12 ticks, 42 effective, parse=0, order=0) |
| Provider/schema stability | **PASS** — side/trigger rates remain **0.0** |
| `valid_watch_candidate_count` | **6** (stable >0; ETH=5, PEPE=1) |
| Safe repair | **PASS** (forbidden=0, promoted=0) |
| MAE cap | **PASS** (within_cap=6, above_cap=0) |
| ETH calibration graduations | **2** (stable vs N-R1) |
| BTC calibration graduations | **0** (unchanged) |
| Stage 4.19 | **NOT started** — **not ready** (BTC graduation=0) |

418-N provider/schema fixes **held stable over 60m**. Next: **4.18-O BTC-specific diagnostics** — do not auto-start Stage 4.19.

**Note:** Container already held a completed R2 soak artifact set (`2026-07-09T04:19Z` END log) when this session finalized; `STAGE4_CLOUD_DRY_RUN_MINUTES` was reset to **0** and post-run analysis re-run on existing output.

---

## 2. Runtime gate result

| Check | Result |
|-------|--------|
| Service RUNNING / exec OK / health 200 | **yes** |
| `runtime_version_check_passed` | **true** |
| `stage_marker` | **4.18-N** |
| `prompt_hints_present` | **true** |
| `schema_enforcement_present` | **true** |
| `app_file_stale_suspected` | **false** |
| Groq/Cerebras strict + schema repair + provider review | **present** |

---

## 3. Preflight result

| Check | Result |
|-------|--------|
| `can_start_long_soak` | **true** |
| `preflight_probe_call_count` | **2** |
| `stage3_context_check_passed` | **true** |
| `mock_used` / `order_sent` | **false** |
| `debug_log_has_api_key` | **false** |

---

## 4. 60m technical result

| Metric | N-R2 (60m) | N-R1 (30m) |
|--------|------------|------------|
| `cloud_dry_run_completed` | **true** | true |
| `tick_count` / `expected` | **12** / **12** | 6/6 |
| `effective_decision_count` | **42** | 21 |
| `skipped_tick_count` / chain_failed | **6** | 3 |
| `parse_error_count` | **0** | 0 |
| `mock_ai_used_count` | **0** | 0 |
| `order_sent_count` | **0** | 0 |
| `validator_passed` / `technical_valid` | **true** | true |
| Provider mix | groq=24, cerebras=18 | groq=12, cerebras=9 |

`STAGE4_CLOUD_DRY_RUN_MINUTES` reset to **0**; container env confirmed.

---

## 5. Provider compliance stability

| Provider | decisions | `side_missing_rate` | `trigger_missing_rate` | `valid_watch` |
|----------|-----------|---------------------|------------------------|---------------|
| groq | 24 | **0.0** | **0.0** | 0 |
| cerebras | 18 | **0.0** | **0.0** | **6** |

vs M-R1 baseline: Groq side_missing **1.0→0.0**; Cerebras trigger_missing **1.0→0.0** — **no regression** over 60m.

---

## 6. `valid_watch_candidate_count`

| Symbol | N-R1 | N-R2 |
|--------|------|------|
| ETHUSDT | 4 | **5** |
| PEPEUSDT | 0 | **1** |
| BTCUSDT | 0 | **0** |
| SOLUSDT | 0 | **0** |
| **Total** | **4** | **6** |

Sustained **>0** across extended window.

---

## 7. ETH graduation stability

| Metric | N-R1 | N-R2 |
|--------|------|------|
| `calibration_eth_graduations` | 2 | **2** |
| ETH watch count | 4 | **5** |
| ETH within_cap | 4 | **5** |
| ETH above_cap | 0 | **0** |

ETH path **stable**.

---

## 8. BTC graduation result

| Metric | Value |
|--------|-------|
| `valid_watch_candidate_count` (BTC) | **0** |
| `btc_watch_confirmation_candidate_count` | **0** |
| `calibration_btc_graduations` | **0** |

BTC still produces no paper-intent watch / graduation under `major_mae_100_llm_mae`.

---

## 9. Safe repair metrics

| Metric | Value |
|--------|-------|
| `schema_repair_applied_count` | **0** |
| `schema_repair_safe_only_count` | **42** |
| `schema_repair_forbidden_action_count` | **0** |
| `schema_repair_promoted_eligibility_count` | **0** |

---

## 10. Paper logger result

| Metric | Value |
|--------|-------|
| `total_events_written` | **42** |
| `watchlist_count` | **1** |
| `hypothetical_entry_count` | **0** |

---

## 11. Calibration replay result

| Mode | graduations | per-symbol |
|------|-------------|------------|
| `major_mae_100_llm_mae` (recommended) | **2** | ETHUSDT=**2**, BTC=**0** |

| Metric | Value |
|--------|-------|
| `calibration_total_graduations` | **2** |
| `calibration_recommended_mode_for_419` | `major_mae_100_llm_mae` |
| Tool `stage_419_readiness` flag | true (offline tool only) |

---

## 12. Analyzer result

| Metric | Value |
|--------|-------|
| `directional_bias_without_candidate_side_count` | **0** |
| `missing_paper_fields_count` | **0** |
| `mae_above_symbol_cap_count` | **0** |
| Output | `/data/stage4_18n_r2_failure_analysis` |

---

## 13. Compare N-R1 vs N-R2

| Metric | Delta |
|--------|-------|
| `within_cap` | 4 → **6** (+2) |
| `above_cap` | 0 → **0** |
| `graduation_delta` | **0** (ETH=2 both) |
| `eth_watch_delta` | **+1** |
| PEPE valid watch | 0 → **1** (new) |

Compare output: `/data/stage4_18n_r2_compare_n_r1_vs_n_r2`

---

## 14. Stage 4.19 readiness

**`stage_419_readiness=false` for operator gate.**

| Criterion | Status |
|-----------|--------|
| `calibration_eth_graduations > 0` | **yes** (2) |
| `calibration_btc_graduations > 0` | **no** (0) |
| `recommended_mode_for_419 != none` | **yes** |
| `within_cap > above_cap` | **yes** (6 > 0) |

**Do not start Stage 4.19** without operator approval and BTC graduation path.

---

## 15. Whether Stage 4.19 requires operator approval

**Yes — always.** Even if BTC later graduates, Stage 4.19 requires explicit operator sign-off. Not auto-started.

---

## 16. Safety confirmation

- `mock_ai_used_count=0`, `order_sent_count=0`, `any_exchange_call_made=false`
- demo / paper execution / ARM / radar / production / btc-auto: **not enabled**
- `STAGE4_CLOUD_DRY_RUN_MINUTES=0` confirmed post-run

---

## 17. Final verdict

**`STAGE_4_18N_R2_PARTIAL_A`**

60m stability sample **PASS** on technical + field-contract stability.  
**Stage 4.19 blocked** — BTC graduation still **0**.

**Next:** **Stage 4.18-O** — BTC-specific schema / sample diagnostics.  
**Do not** run 6h/24h. **Do not** auto-start Stage 4.19.

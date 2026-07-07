# Stage 4.18-M-R1 — Runtime-Gated 30m Structured Output Regression

**Date:** 2026-07-07 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Prior commit:** `9ee2056` (418-M)  
**Output:** `/data/stage4_ai_decisions_418m_r1_structured_output_30m`  
**Mode:** read-only 30m dry-run with **418-M** structured output contract — no orders

---

## 1. Executive summary

**Verdict: PARTIAL B**

| Layer | Result |
|-------|--------|
| Runtime version gate | **PASS** (stage_marker=4.18-M) |
| Preflight | **PASS** (probe=2) |
| Technical soak | **PASS** (6/6 ticks, 23 effective, parse=0, order=0) |
| Field contract | **FAIL** — `valid_watch_candidate_count=0` all symbols |
| MAE alignment | **Marginal improve** — within_cap 0→3, above_cap 18→15 vs L-R1 |
| Graduations | **0** |
| Stage 4.19 | **NOT started** |

418-M structured contract is active in runtime, but LLM output still fails field contract on majors. **Do not run 60m.** Proceed to **418-N** provider-specific JSON schema / repair path.

---

## 2. Runtime gate

| Check | Result |
|-------|--------|
| `runtime_version_check_passed` | **true** |
| `stage_marker` | **4.18-M** |
| `prompt_hints_present` | **true** |
| `schema_enforcement_present` | **true** |
| `app_file_stale_suspected` | **false** |

---

## 3. Preflight

| Check | Result |
|-------|--------|
| `can_start_long_soak` | **true** |
| `preflight_probe_call_count` | **2** |
| `stage3_context_check_passed` | **true** |
| `mock_used` / `order_sent` | **false** |

---

## 4. 30m technical result

| Metric | M-R1 | L-R1 |
|--------|------|------|
| `cloud_dry_run_completed` | **true** | true |
| `tick_count` / `expected` | **6** / **6** | 6/6 |
| `effective_decision_count` | **23** | 24 |
| `skipped_tick_count` | **1** (ETH tick1 chain_failed) | 0 |
| `parse_error_count` | **0** | 0 |
| `mock_ai_used_count` | **0** | 0 |
| `order_sent_count` | **0** | 0 |
| `validator_passed` | **true** | true |
| Provider mix | groq=12, cerebras=11 | groq=12, cerebras=12 |

`STAGE4_CLOUD_DRY_RUN_MINUTES` reset to **0** confirmed.

---

## 5. Structured output field compliance

| Metric | M-R1 | L-R1 |
|--------|------|------|
| `valid_watch_candidate_count` (all) | **0** | 0 |
| `no_valid_watch_candidate_count` | **18** | 19 |
| `derived_candidate_side_suggestion_count` | **13** | 13 |
| `mae_scale_drift_suspected_count` | **1** | 0 |
| `directional_bias_without_candidate_side` | **13** | 13 |
| `missing_paper_fields_count` | **18** | 10 |
| `mae_above_symbol_cap_count` | **15** | 19 |

### candidate_side_missing_rate_by_symbol

| Symbol | M-R1 | L-R1 |
|--------|------|------|
| BTCUSDT | **1.0** | 1.0 |
| ETHUSDT | **1.0** | 0.67 |
| SOLUSDT | **1.0** | 1.0 |
| PEPEUSDT | **0.0** | 0.2 |

### missing_entry_trigger_rate_by_symbol

| Symbol | M-R1 | L-R1 |
|--------|------|------|
| BTCUSDT | **0.67** | 0.5 |
| ETHUSDT | **1.0** | 1.0 |
| SOLUSDT | **0.67** | 0.2 |
| PEPEUSDT | **1.0** | 0.6 |

**Conclusion:** PEPE side pairing improved (0% missing) but **no symbol produced a valid watch candidate**. Field contract still fails → **PARTIAL B**.

---

## 6. MAE / cap result

| Metric | M-R1 | L-R1 |
|--------|------|------|
| `paper_ready_watch_mae_within_cap_count` | **3** | 0 |
| `paper_ready_watch_mae_above_cap_count` | **15** | 18 |
| `within_cap > above_cap` | **FAIL** (3 vs 15) | FAIL (0 vs 18) |
| `mae_invalidation_inconsistent_count` | **2** | 3 |

MAE within-cap improved slightly but insufficient for graduation.

---

## 7. Paper logger / calibration

| Metric | Value |
|--------|-------|
| `paper_logger_events_written` | **23** |
| `paper_logger_watchlist_count` | **0** |
| `paper_logger_hypothetical_entry_count` | **0** |
| `calibration_total_graduations` | **0** |
| `calibration_recommended_mode_for_419` | **none** |

---

## 8. Analyzer / compare

- **Analyzer:** `/data/stage4_18m_r1_failure_analysis`
- **Compare L-R1 vs M-R1:** `/data/stage4_18m_r1_compare_l_r1_vs_m_r1`
- `within_cap_delta`: **+3** (candidate vs L-R1 baseline in compare session)
- `above_cap_delta`: **-3**
- `graduation_delta`: **0**

**Recommendations:** `structured_schema_side_required`, `structured_schema_trigger_required`, `mae_scale_contract_or_provider_specific_prompt`, `do_not_extend_sample_until_field_contract_passes`

### field_contract_failure_by_symbol

| Symbol | side | trigger | mae_above_cap | mae_scale_drift |
|--------|------|---------|---------------|-----------------|
| BTCUSDT | 6 | 4 | 6 | 0 |
| ETHUSDT | 1 | 1 | 1 | 1 |
| SOLUSDT | 6 | 4 | 6 | 0 |
| PEPEUSDT | 0 | 5 | 2 | 0 |

### Provider review (418-N offline on M-R1)

| Provider | decisions | side_missing_rate | trigger_missing_rate | valid_watch |
|----------|-----------|-------------------|----------------------|-------------|
| Groq | 12 | **1.0** | 0.67 | 0 |
| Cerebras | 11 | 0.17 | **1.0** | 0 |

**418-N recommendations:** Groq → tighten JSON schema / `response_format`; Cerebras → `entry_trigger` contract in `json_schema`.

---

## 9. Stage 4.19 readiness

| Check | Value |
|-------|-------|
| `stage_419_readiness` | **false** |
| `should_propose_60m_sample` | **false** |
| `if_not_ready_recommendation` | **Stage 4.18-N** — provider JSON schema / output repair |

---

## 10. Safety confirmation

| Check | Value |
|-------|-------|
| Orders / mock / exchange | **0 / 0 / false** |
| Production / btc-auto / ARM / radar | **not touched** |
| Stage 4.19 started | **NO** |

---

## 11. Verdict and next step

**`STAGE_4_18M_R1_PARTIAL_B`** — technical PASS; field contract FAIL (`valid_watch=0`).

**Next:** **Stage 4.18-N** code-only provider schema / repair path. **Do not** run 60m. Stopped at gate.

**418-N started:** `stage4_provider_field_compliance_review.py` + plan doc (`STAGE_4_18N_PROVIDER_SCHEMA_AND_OUTPUT_REPAIR_PLAN.md`). **No soak.**

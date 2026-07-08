# Stage 4.18-N-R1 — Runtime-Gated 30m Provider Schema Regression

**Date:** 2026-07-08 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Code / deploy base:** `8230f73` (418-N) + redeploy `ab3fc0b`  
**Output:** `/data/stage4_ai_decisions_418n_r1_provider_schema_30m`  
**Mode:** read-only 30m dry-run — **no orders**

---

## 1. Executive summary

**Verdict: `STAGE_4_18N_R1_PASS`**

| Layer | Result |
|-------|--------|
| Runtime version gate | **PASS** (`stage_marker=4.18-N`) |
| Preflight | **PASS** (`can_start_long_soak=true`, probe=2) |
| Technical soak | **PASS** (6/6 ticks, 21 effective, parse=0, order=0) |
| Provider field contract | **PASS** — `valid_watch_candidate_count=4` (ETH / Cerebras) |
| Groq `side_missing_rate` | **1.0 → 0.0** vs M-R1 |
| Cerebras `trigger_missing_rate` | **1.0 → 0.0** vs M-R1 |
| Safe repair | **PASS** (forbidden=0, promoted=0) |
| Calibration graduations | **2** (ETHUSDT, `major_mae_100_llm_mae`) |
| Stage 4.19 | **NOT started** |
| 60m | **May be proposed** — **not auto-run** |

418-N provider schema / strict prompts restored field contract yield after M-R1 `valid_watch=0`. Stopped at gate.

---

## 2. Runtime gate result

| Check | Result |
|-------|--------|
| `service exec echo OK` | **OK** |
| `/health` | **200** |
| `runtime_version_check_passed` | **true** |
| `stage_marker` | **4.18-N** |
| `prompt_hints_present` | **true** |
| `schema_enforcement_present` | **true** |
| `app_file_stale_suspected` | **false** |
| Groq / Cerebras strict rules | **present** |
| Schema repair / provider review | **present** |

---

## 3. Preflight result

| Check | Result |
|-------|--------|
| `can_start_long_soak` | **true** |
| `preflight_probe_call_count` | **2** (≤3) |
| `stage3_context_check_passed` | **true** |
| `mock_used` / `order_sent` | **false** |
| `debug_log_has_api_key` | **false** |

**Note:** First capacity probe failed because Zeabur LLM keys were missing after prior env wipe. Keys + full idle safety vars were restored **without changing product code**; then capacity/re-gate PASS before soak.

---

## 4. 30m technical result

| Metric | N-R1 | M-R1 |
|--------|------|------|
| `cloud_dry_run_completed` | **true** | true |
| `tick_count` / `expected` | **6** / **6** | 6/6 |
| `effective_decision_count` | **21** | 23 |
| `skipped_tick_count` / chain_failed | **3** | 1 |
| `parse_error_count` | **0** | 0 |
| `mock_ai_used_count` | **0** | 0 |
| `order_sent_count` | **0** | 0 |
| `validator_passed` / `technical_valid` | **true** | true |
| Provider mix | groq=12, cerebras=9 | groq=12, cerebras=11 |

`STAGE4_CLOUD_DRY_RUN_MINUTES` reset to **0**; container + health confirmed.

---

## 5. Provider compliance result

| Provider | decisions | `side_missing_rate` | `trigger_missing_rate` | `valid_watch_candidate_count` |
|----------|-----------|---------------------|------------------------|-------------------------------|
| groq | 12 | **0.0** | **0.0** | **0** |
| cerebras | 9 | **0.0** | **0.0** | **4** |

---

## 6. Groq `side_missing` delta

| | M-R1 | N-R1 |
|--|------|------|
| Groq `side_missing_rate` | **1.0** | **0.0** |

Clear improvement. Groq produced no paper-intent watches this window (all soft/hard skip path), but no longer emits side-missing contract failures on paper intents.

---

## 7. Cerebras `trigger_missing` delta

| | M-R1 | N-R1 |
|--|------|------|
| Cerebras `trigger_missing_rate` | **1.0** | **0.0** |

Clear improvement. Cerebras supplied valid watch field contracts on ETHUSDT.

---

## 8. `valid_watch_candidate_count`

| Scope | Count |
|-------|-------|
| Total (cerebras) | **4** |
| ETHUSDT | **4** |
| BTC / SOL / PEPE | **0** |

`valid_watch_candidate_count > 0` → field-contract unblock vs M-R1.

---

## 9. Safe repair metrics

| Metric | Value |
|--------|-------|
| `schema_repair_applied_count` | **0** |
| `schema_repair_safe_only_count` | **21** |
| `schema_repair_forbidden_action_count` | **0** |
| `schema_repair_promoted_eligibility_count` | **0** |

No forbidden / eligibility-promoting repairs at runtime.

---

## 10. Paper logger result

| Metric | Value |
|--------|-------|
| `total_events_written` | **21** |
| `watchlist_count` | **0** |
| `hypothetical_entry_count` | **0** |

Strict append-only logger wrote decision events; watchlist graduation remains in offline calibration path (not live paper order).

---

## 11. Calibration replay result

| Mode | graduations | notes |
|------|-------------|-------|
| `major_mae_100_llm_mae` (**recommended**) | **2** (ETHUSDT) | watchlist_created=2, confirmed=2 |
| legacy major_mae_* (non-LLM MAE) | **0** | mae_cap blocks |

| Metric | Value |
|--------|-------|
| `calibration_total_graduations` (recommended mode) | **2** |
| `calibration_btc_graduations` | **0** |
| `calibration_eth_graduations` | **2** |
| `calibration_recommended_mode_for_419` | `major_mae_100_llm_mae` |
| Tool `stage_419_readiness` | **true** (offline) |

---

## 12. Analyzer result

| Metric | Value |
|--------|-------|
| `paper_intent_count` | **4** |
| `directional_bias_without_candidate_side_count` | **0** |
| `missing_paper_fields_count` | **0** |
| `mae_above_symbol_cap_count` | **0** |
| `candidate_side_missing_rate_by_symbol` | ETHUSDT **0.0** |
| `missing_entry_trigger_rate_by_symbol` | ETHUSDT **0.0** |
| Output | `/data/stage4_18n_r1_failure_analysis` |

---

## 13. Compare M-R1 vs N-R1

| Metric | M-R1 | N-R1 | Delta |
|--------|------|------|-------|
| `paper_ready_watch_mae_within_cap_count` | 3 | **4** | +1 |
| `paper_ready_watch_mae_above_cap_count` | 15 | **0** | −15 |
| `mae_estimate_above_symbol_cap_count` | 15 | **0** | −15 |
| Recommended-mode graduations | 0 | **2** | +2 |
| ETH watch count | 1 | **4** | +3 |
| `directional_bias_without_candidate_side` | high (M-R1) | **0** | improved |

Compare output: `/data/stage4_18n_r1_compare_m_r1_vs_n_r1`

---

## 14. Stage 4.19 readiness

**NOT started.** Offline calibration flag is true, but operator gate still requires:

1. Explicit approval of this N-R1 PASS report  
2. Optional 60m read-only sample (proposed, not auto)  
3. Separate Stage 4.19 kickoff approval  

---

## 15. Whether 60m should be proposed

**Yes — propose only.**  
Reason: `valid_watch > 0`, side/trigger rates collapsed to 0, safe repair clean, technical PASS.  
**Do not auto-run 60m.** If operator declines, stay idle at DRY=0.

---

## 16. Safety confirmation

- `mock_ai_used_count=0`
- `order_sent_count=0`
- `any_exchange_call_made=false`
- demo / paper order execution / ARM / radar / production / btc-auto: **not enabled / not touched**
- `STAGE4_CLOUD_DRY_RUN_MINUTES` reset to **0**; container env confirmed

---

## 17. Final verdict

**`STAGE_4_18N_R1_PASS`**

**Next:** Operator may approve a **60m read-only** soak; **do not** auto-start Stage 4.19.  
If a follow-up window shows `valid_watch` collapsing back to 0, return to provider/schema output work — do not lengthen soak blindly.

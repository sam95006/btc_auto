# Stage 4.11 Extended Read-only Soak + Shadow Dataset Expansion Report

**Generated:** 2026-06-29  
**Status:** **PARTIAL FAIL** (dataset expansion target not met)  
**Source dataset:** `/data/stage4_ai_decisions_411_180m`  
**Shadow output:** `/data/stage4_shadow_compare_411`

> **sample_size_too_small=true**  
> **not_a_backtest=true**  
> **no_orders_sent=true**  
> **soak_partial=true** — 7 effective decisions (target ≥30; partial floor ≥20 not met)

Read-only throughout. No orders, no ARM, no production, no btc-auto.

---

## Executive summary

Stage 4.11 attempted a **180-minute ETHUSDT-only** cloud dry-run to expand the shadow dataset from 11 → ≥30 decisions. Safety checks passed and all 7 recorded decisions were valid real-LLM skips with `order_sent=false`. However, **Groq `empty_llm_response` / quota exhaustion** caused **25 skipped ticks** (~78% tick loss). The background dry-run **did not write a completion summary or bundle** (process ended at tick 32/≈36 without `stage4_ai_decision_summary.json`). Cerebras fallback was **never used** despite being configured.

---

## 1. Soak dataset summary

| Field | Value |
|---|---|
| output_dir | `/data/stage4_ai_decisions_411_180m` |
| configured_duration_minutes | 180 |
| poll_interval_seconds | 300 |
| symbols | ETHUSDT |
| tick_count (log) | 32 (incomplete; expected ~36) |
| effective_decision_count | **7** |
| real_successful_llm_decision_count | **7** |
| skipped_tick_count (log) | **25** (`empty_llm_response`) |
| cloud_dry_run_completed | **false** (no summary file) |
| parse_error_count | 0 |
| order_sent_count | 0 |
| mock_ai_used_count | 0 |
| stage3_context_available_count | 7 (= effective_decision_count) |
| bundle_exported | **false** |

---

## 2. Provider distribution

| provider | successful_decisions |
|---:|---:|
| groq | 7 |
| cerebras | 0 |

- `provider_success_distribution`: `{groq: 7}`
- `fallback_used_count`: 0
- `provider_rate_limit_count` (validator): 0
- `provider_quota_exhausted` (system events): **25** (reason: `empty_llm_response`)
- All 7 decisions used Groq `llama-3.3-70b-versatile`; secondary Cerebras never engaged on empty-response skips.

---

## 3. Decision intent distribution

| intent | count |
|---|---:|
| hard_skip | 4 |
| watch | 3 |
| soft_skip | 0 |
| enter_candidate | 0 |

Compared to Stage 4.9 (n=11): `{hard_skip:5, watch:4, soft_skip:2}` — similar skip-heavy posture, but sample too small for calibration.

---

## 4. Confidence distribution

| metric | value |
|---|---:|
| confidence_average | 0.2414 |
| confidence_min | 0.05 |
| confidence_max | 0.52 |

| band | count | notes |
|---|---:|---|
| 0.05 (hard_skip) | 4 | all hard_skip |
| 0.45–0.52 (watch) | 3 | watch intents |

---

## 5. Shadow label distribution

Shadow compare run at 2026-06-29T08:40:26Z (5 of 7 had full 60m horizon; last 2 insufficient_future_data).

| shadow_label | count |
|---|---:|
| good_skip | 2 |
| reasonable_watch | 1 |
| neutral | 2 |
| insufficient_future_data | 2 |
| bad_watch | 0 |
| missed_opportunity | 0 |

| metric | value |
|---|---:|
| shadow_compared_count | 5 |
| insufficient_future_data_count | 2 |
| return_60m_average_pct | -0.2324 |
| mfe_60m_average_pct | 0.1908 |
| mae_60m_average_pct | 0.3561 |

---

## 6. Good skip / bad watch / missed opportunity

| label | count |
|---|---:|
| good_skip_count | 2 |
| bad_watch_count | 0 |
| missed_opportunity_count | 0 |
| neutral_count | 2 |
| reasonable_watch_count | 1 |

On the 5 comparable decisions, ETH drifted mildly lower (avg 60m −0.23%). No `bad_watch` in this subset — unlike Stage 4.10 where 2 watch cases at 0.45–0.52 were flagged during a stronger down hour.

---

## 7. Watch calibration review

- 3 watch decisions at confidence **0.45–0.52**; shadow labels: 1 `reasonable_watch`, 2 `insufficient_future_data` (no 60m label yet).
- No `bad_watch` in comparable window — **inconclusive** vs Stage 4.10 finding due to tiny n and incomplete future data on latest ticks.
- Watch rate (3/7 = 43%) is higher than hard_skip alone would suggest; still all `final_action=skip`.

---

## 8. Patch / reflection influence summary

| awareness | count (of 7) |
|---|---:|
| patch_awareness_detected | 7/7 |
| reflection_awareness_detected | 6/7 |

Patch context universally present. Reflection awareness high (6/7) but did not prevent watch labels during volatile/trend regime shifts.

---

## 9. Whether Stage 4.10 findings repeated

| Stage 4.10 finding | Stage 4.11 |
|---|---|
| Skip-heavy reasonable in down hour | **Partially** — 2 good_skip on comparable ticks; mild down drift |
| 0 missed_opportunity | **Repeated** (0 on n=5 comparable) |
| 2 bad_watch at watch 0.45–0.52 | **Not repeated** in comparable window (0 bad_watch) |
| sample_size_too_small | **Still true** (worse: n=7 vs n=11) |

Stage 4.10 conclusions **cannot be confirmed or refuted** at scale; dataset expansion failed.

---

## 10. Recommendation for Stage 4.12

1. **Fix provider yield (P0):** Route `empty_llm_response` / `provider_quota_exhausted` on Groq → **Cerebras real fallback** before `skip_tick_no_decision`. Currently 25/32 ticks lost with zero Cerebras usage.
2. **Groq key dedup / rotation:** 3 distinct Groq keys still configured; empty-response pattern suggests quota exhaustion not HTTP 429 — review per-key limits and backoff.
3. **Resilient soak completion:** Write `stage4_ai_decision_summary.json` + bundle export even on partial completion or process SIGTERM (soak died without summary).
4. **Re-run extended soak** after provider fix; target ≥30 effective decisions before shadow calibration.
5. **Keep read-only** — no demo orders, no ARM until dataset ≥30 and watch calibration reviewed on adequate sample.

---

## Safety checklist

| check | result |
|---|---|
| full_test_suite_passed | **true** (85/85; commit `a51930c`) |
| stage3_context_check_passed | **true** (trades≥5, reflections≥5, patches≥5) |
| order_sent_count | 0 |
| mock_ai_used_count | 0 |
| validator_passed | **true** (on 7 decisions) |
| debug_log_has_api_key | false |
| any_trading_action_sent | false |
| production_service_touched | false |
| btc_auto_touched | false |
| STAGE4_CLOUD_DRY_RUN_MINUTES reset | **0** (post-soak) |

---

## Root cause: tick loss

```
25 SKIPPED ticks — reason=empty_llm_response
system_events: provider_quota_exhausted × 25 (groq)
7 successful decision ticks (groq only)
0 cerebras fallback invocations
```

The 180m soak **did not meet** the ≥30 (or ≥20 partial) decision target due to provider yield collapse, not decision-layer logic errors.

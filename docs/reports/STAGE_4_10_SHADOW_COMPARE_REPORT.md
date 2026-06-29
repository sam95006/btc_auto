# Stage 4.10 Shadow Compare Report

**Generated:** 2026-06-29T05:38:49Z  
**Source dataset:** `/data/stage4_ai_decisions_49_60m` (Stage 4.9 60m soak)  
**Shadow output:** `/data/stage4_shadow_compare_410`

> **sample_size_too_small=true**  
> **not_a_backtest=true**  
> **no_orders_sent=true**

Read-only shadow labels only. No orders, no ARM, no production, no btc-auto.

---

## 1. Dataset summary

| Field | Value |
|---|---|
| source_output_dir | `/data/stage4_ai_decisions_49_60m` |
| decision_count | 11 |
| effective_decision_count (Stage 4.9) | 11 |
| duration_minutes | 60 |
| poll_interval_seconds | 300 |
| symbol | ETHUSDT |
| provider | groq (11/11) |
| mock_ai_used_count | 0 |
| order_sent_count | 0 |
| decision_intent_distribution | hard_skip: 5, watch: 4, soft_skip: 2 |
| enter_candidate_count | 0 |
| confidence_average | 0.2355 |
| regime | volatile (11/11) |
| stage3_context_available | 11/11 |

Stage 4.9 soak was FULL PASS with one rate-limit skipped tick and zero parse errors.

---

## 2. Shadow label distribution

| shadow_label | count |
|---|---:|
| good_skip | 7 |
| bad_watch | 2 |
| reasonable_watch | 1 |
| neutral | 1 |
| missed_opportunity | 0 |
| insufficient_future_data | 0 |

- **shadow_compared_count:** 11  
- **insufficient_future_data_count:** 0 (all decisions had full 60m kline window at compare time)

---

## 3. Intent vs outcome

| tick | decision_intent | confidence | return_60m_pct | mfe_60m_pct | mae_60m_pct | shadow_label |
|---:|---|---:|---:|---:|---:|---|
| 1 | soft_skip | 0.20 | -0.32 | 0.06 | 0.62 | good_skip |
| 2 | hard_skip | 0.05 | -0.27 | 0.06 | 0.45 | good_skip |
| 3 | hard_skip | 0.05 | -0.21 | 0.38 | 0.13 | good_skip |
| 4 | watch | 0.52 | -0.10 | 0.44 | 0.22 | neutral |
| 5 | watch | 0.45 | -0.33 | 0.24 | 0.42 | reasonable_watch |
| 6 | watch | 0.45 | -0.56 | 0.09 | 0.56 | bad_watch |
| 7 | hard_skip | 0.05 | -0.74 | 0.01 | 0.66 | good_skip |
| 8 | soft_skip | 0.20 | -1.22 | 0.02 | 0.88 | good_skip |
| 9 | hard_skip | 0.05 | -0.90 | 0.14 | 1.16 | good_skip |
| 10 | watch | 0.52 | -0.70 | 0.20 | 1.18 | bad_watch |
| 11 | hard_skip | 0.05 | -0.72 | 0.20 | 1.17 | good_skip |

**Pattern:** ETH drifted lower over the hour (avg return_60m ≈ -0.55%). Skip intents avoided adverse drift; watch ticks at higher confidence (0.45–0.52) coincided with larger MAE.

---

## 4. Confidence vs outcome

| confidence band | count | dominant shadow labels |
|---|---:|---|
| 0.05 (hard_skip) | 5 | good_skip (5) |
| 0.20 (soft_skip) | 2 | good_skip (2) |
| 0.45 (watch) | 2 | reasonable_watch (1), bad_watch (1) |
| 0.52 (watch) | 2 | neutral (1), bad_watch (1) |

Low-confidence skips (0.05–0.20) aligned with good_skip under conservative rules. Watch labels at 0.45–0.52 show mixed quality — two bad_watch cases had the highest MAE in the sample.

---

## 5. Patch / reflection influence vs outcome

| awareness | count | shadow breakdown |
|---|---:|---|
| patch_awareness_detected | 11/11 | good_skip 7, bad_watch 2, reasonable_watch 1, neutral 1 |
| reflection_awareness_detected | 5/11 | good_skip 3, bad_watch 2 |

All decisions referenced patch context. Reflection-aware ticks (5) included both bad_watch cases (ticks 6, 10) — reflection did not prevent optimistic watch labels during a deteriorating hour.

---

## 6. Missed opportunity cases

**None (0).**

Conservative rule requires abs(return_60m) ≥ 0.4% **and** MFE − MAE ≥ 0.2% for a directional missed move. Despite net −0.55% average drift, candidate_side was NONE for all decisions; favorable excursion remained small relative to adverse excursion, so skips were not flagged as missed entries.

---

## 7. Good skip cases

7 decisions labeled **good_skip** (ticks 1–3, 7–9, 11 plus soft_skip tick 8):

- Adverse drift dominated (MAE ≫ MFE) while MFE−MAE margin stayed below the missed-opportunity threshold.
- Example tick 8: return_60m −1.22%, MAE 0.88%, MFE 0.02% — skipping avoided a clearly unfavorable hour.

---

## 8. Limitations

- **sample_size_too_small=true** (n=11, minimum recommended 30).
- **not_a_backtest=true** — no hypothetical entries; labels judge intent quality only.
- Uses public Bybit demo klines (read-only); no mainnet or production access.
- Shadow rules are conservative; large one-sided trends with NONE candidate_side may not register as missed_opportunity.
- Single symbol (ETHUSDT), single hour, all volatile regime — not representative of broader conditions.
- Watch labels are not calibrated for execution; bad_watch indicates post-hoc adverse volatility, not a trading failure.

---

## 9. Next recommendation

1. **Extend soak to ≥30 decisions** (Stage 4.9b or repeat 60m+ run) before tuning watch confidence thresholds.
2. **Review watch prompt calibration** — confidence 0.45–0.52 produced 2/4 bad_watch during a down hour; consider tying watch to tighter MAE/volatility gates.
3. **Keep read-only** until shadow distribution stabilizes; do not ARM or enable demo orders.
4. **Optional Stage 4.11:** re-run shadow compare after extended dataset with enter_candidate cases if supervisor ever approves candidates in dry-run.

---

## Safety checklist

| check | result |
|---|---|
| order_sent_count | 0 |
| mock_ai_used_count | 0 |
| any_trading_action_sent | false |
| production_service_touched | false |
| btc_auto_touched | false |
| debug_log_has_api_key | false |
| shadow_compare_completed | true |
| report_created | true |

---

## Aggregate metrics

| metric | value |
|---|---:|
| return_60m_average_pct | -0.5521 |
| mfe_60m_average_pct | 0.1666 |
| mae_60m_average_pct | 0.6783 |
| good_skip_count | 7 |
| missed_opportunity_count | 0 |
| bad_watch_count | 2 |
| neutral_count | 1 |
| reasonable_watch_count | 1 |

**Tool:** `tools/research/stage4_shadow_compare.py`

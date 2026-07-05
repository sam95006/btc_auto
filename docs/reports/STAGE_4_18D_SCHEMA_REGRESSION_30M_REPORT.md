# Stage 4.18-D — Paper Readiness Schema Regression (30m)

**Date:** 2026-07-05  
**Branch:** `stage3-demo-learning`  
**Deploy commit:** `f56179f` (package sync) / schema `a142f03`  
**Service:** `nexus-stage3-bybit-demo-learning` (`6a3b81652fdef84a45a2a553`)  
**Output:** `/data/stage4_ai_decisions_418d_schema_regression_30m`  
**Mode:** read-only dry-run — **no execution, no RG changes**

---

## 1. Executive summary

30m fixed-fleet read-only regression **completed successfully** with new Stage 4.18-C paper-readiness schema deployed. Real LLM produced **23 effective decisions** across **6/6 ticks** with **zero parse errors** and **zero decision_quality_incomplete** on eligible watch intents.

**Schema yield improved materially:** `paper_ready_watch_count=16`, `directional_bias_present_count=16`, `mae_risk_estimate_present_count=16`.

**Paper pipeline graduation path still blocked:** paper event logger emitted **23 hypothetical_skip** (MAE watch guard via market proxy); calibration replay **0 graduations**.

**Verdict:** `STAGE_4_18D_SCHEMA_REGRESSION_PASS`  
**Stage 4.19 readiness:** `false` — improve MAE alignment between LLM `mae_risk_estimate_pct` and paper guards before offline exit evaluation.

---

## 2. Runtime / preflight

| Check | Result |
|-------|--------|
| `/app` exists | ✅ |
| `stage4_paper_readiness.py` deployed | ✅ (11475 bytes) |
| `directional_bias` / `paper_readiness` in code | ✅ |
| `STAGE4_ORDER_ALLOWED` | `false` |
| `STAGE4_ALLOW_MOCK_FALLBACK` | `false` |
| Provider capacity `can_start_long_soak` | `true` |
| `preflight_probe_call_count` | 2 |
| Stage3 context seed | `passed=true` |
| `mock_used` | `false` |
| `order_sent` | `false` |

---

## 3. 30m regression summary

| Metric | Value |
|--------|-------|
| `cloud_dry_run_completed` | **true** |
| `tick_count` | **6** |
| `expected_tick_count` | **6** |
| `effective_decision_count` | **23** (target ≥20) |
| `parse_error_count` | **0** |
| `validator_passed` | **true** |
| `technical_valid` | **true** |
| `mock_ai_used_count` | **0** |
| `order_sent_count` | **0** |
| `real_llm_used_count` | **23** |
| Provider mix | groq=12, cerebras=11 (11 groq_rate_limited fallbacks) |
| `skipped_tick_count` | 1 (PEPEUSDT chain fail tick) |

### Per-symbol intent distribution

| Symbol | Effective | Intents |
|--------|-----------|---------|
| BTCUSDT | 6 | watch=6 |
| ETHUSDT | 6 | soft_skip=3, hard_skip=3 |
| SOLUSDT | 6 | watch=6 |
| PEPEUSDT | 5 | watch=4, soft_skip=1 |

---

## 4. Paper readiness metrics (4.18-D)

| Metric | 4.18-D | Pre-4.18-C baseline (4.17/4.18 fleet) |
|--------|--------|--------------------------------------|
| `directional_bias_present_count` | **16** | ~0 (field absent) |
| `directional_bias_none_count` | 7 | N/A |
| `watch_with_directional_bias_count` | **16** | ~0 |
| `paper_ready_watch_count` | **16** | 0 |
| `paper_ready_enter_candidate_count` | 0 | 0 |
| `decision_quality_incomplete_count` | **0** | high (implicit) |
| `mae_risk_estimate_present_count` | **16** | 0 |
| `entry_trigger_present_count` | 4 | 0 |
| `invalidation_present_count` | **16** | 0 |
| `enter_candidate_missing_side_count` | 0 | 29+ (4.18 blocker) |

**Conclusion:** New schema fields are populated and quality-gated correctly. LLM now produces paper-ready watch decisions when intent=watch.

---

## 5. Paper event logger (4.18-D only)

**Output:** `/data/stage4_paper_events_418d_schema_regression`

| Metric | Value |
|--------|-------|
| Events written | 23 |
| `watchlist_count` | **0** |
| `hypothetical_entry_count` | **0** |
| `hypothetical_skip_count` | **23** |
| Top block reason | `mae_watch_downgrade=16` |

Despite `paper_ready_watch_count=16` at decision layer, legacy paper guards still use `_mae_proxy_pct()` from market volatility and downgrade watches before watchlist creation. **Next integration step:** consume LLM `mae_risk_estimate_pct` in paper guards (design-only note — not applied in 4.18-D).

---

## 6. Calibration replay (4.18-D only)

**Output:** `/data/stage4_18d_schema_regression_calibration`

| Mode | Watchlists confirmed | Graduations |
|------|---------------------|-------------|
| major_mae_75 | 1 | 0 |
| major_mae_90 | 1 | 0 |
| major_mae_100 | 1 | 0 |
| major_mae_100_side_memory | 1 | 0 |
| major_mae_100_side_memory_conf_floor | 1 | 0 |

- `recommended_mode_for_419`: **none**
- Primary blocker: `mae_cap_violation` (5 per mode on BTC)
- SOL/PEPE blocked: 11 each mode

---

## 7. Quality improved?

| Criterion | Met? |
|-----------|------|
| `paper_ready_watch_count > 0` | ✅ **16** |
| `paper_ready_enter_candidate_count > 0` | ❌ 0 |
| Calibration BTC/ETH graduation > 0 | ❌ 0 |

**`quality_improved=true`** at **decision/schema layer**.  
**Paper pipeline graduation path not yet improved.**

---

## 8. Stage 4.19 readiness

**`stage_419_readiness=false`**

Rationale:
- Calibration still 0 graduations on 4.18-D data alone
- Paper logger 0 watchlists (MAE guard mismatch)
- No `enter_candidate` intents in 30m window

Do **not** loosen formal RG MAE thresholds. Next: wire LLM MAE estimates into paper guard evaluation, then re-run 4.18-B on combined datasets.

---

## 9. Safety confirmation

| Flag | Value |
|------|-------|
| `order_sent_count` | 0 |
| `mock_ai_used_count` | 0 |
| `any_exchange_call_made` | false |
| `production_touched` | false |
| `btc_auto_touched` | false |
| `STAGE4_CLOUD_DRY_RUN_MINUTES` reset | **0** (confirmed) |

---

## 10. Verdict

**`STAGE_4_18D_SCHEMA_REGRESSION_PASS`**

Regression soak met all technical PASS criteria. Schema repair succeeded — paper-ready watch yield is non-zero with zero quality-incomplete on watch intents.

**Stopped at gate.** Stage 4.19 requires explicit operator approval after paper-guard MAE integration and re-calibration.

**Next step:** Stage 4.18-E (proposed) — paper guard consumes `mae_risk_estimate_pct`; optional 30m re-run; then re-run 4.18-B calibration on 418d + historical fleet data.

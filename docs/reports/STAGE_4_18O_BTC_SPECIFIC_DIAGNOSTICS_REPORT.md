# Stage 4.18-O — BTC-Specific Schema / Sample Diagnostics

**Date:** 2026-07-09 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Input (N-R2 offline):** `/data/stage4_ai_decisions_418n_r2_provider_schema_60m`  
**Output:** `/data/stage4_18o_btc_specific_diagnostics`  
**Mode:** offline replay only — **no soak, no orders**

---

## 1. Executive summary

**Verdict: `STAGE_4_18O_PASS`**

| Layer | Result |
|-------|--------|
| Diagnostics tool | **PASS** — `stage4_btc_specific_diagnostics.py` |
| Unit tests | **PASS** (6/6) |
| Offline N-R2 replay | **PASS** |
| BTC `valid_watch` | **0** (12/12 `soft_skip`) |
| Near-watch candidates | **0** |
| Primary cause | `btc_consistently_skip_intent_no_watch_signal` |
| Stage 4.19 | **BLOCKED** (BTC graduation=0) |

418-N provider/schema stabilization is **not** the BTC blocker. All 12 BTC decisions were Groq `soft_skip` with no directional edge, no watch intent, and no paper fields populated. Skip behavior appears **correct** for this sample — not a schema repair failure.

**Do not** start Stage 4.19. **Do not** run another 60m soak. **Do not** force BTC watch.

---

## 2. N-R2 summary (baseline)

| Metric | N-R2 value |
|--------|------------|
| Verdict | `STAGE_4_18N_R2_PARTIAL_A` |
| `tick_count` | 12/12 |
| `effective_decision_count` | 42 |
| `parse_error_count` | 0 |
| `valid_watch` | 6 (ETH=5, PEPE=1) |
| Provider side/trigger missing | **0.0** / **0.0** |
| `calibration_eth_graduations` | 2 |
| `calibration_btc_graduations` | **0** |
| `recommended_mode_for_419` | `major_mae_100_llm_mae` |

---

## 3. Why Stage 4.19 remains blocked

| Criterion | Status |
|-----------|--------|
| `calibration_eth_graduations > 0` | **yes** (2) |
| `calibration_btc_graduations > 0` | **no** (0) |
| BTC `valid_watch_candidate_count` | **0** |
| BTC watch confirmation candidates | **0** |

Stage 4.19 requires **both** ETH and BTC graduation > 0 under the recommended calibration mode. ETH path is stable; BTC produced no watch intent across the full 60m window.

---

## 4. BTC decision distribution

| Metric | Value |
|--------|-------|
| `btc_decision_count` | **12** |
| `btc_valid_watch_count` | **0** |
| `btc_watch_intent_count` | **0** |
| `btc_soft_skip_count` | **12** |
| `btc_hard_skip_count` | **0** |

### Provider

| Provider | Count |
|----------|-------|
| groq | **12** |
| cerebras | 0 |

### Regime

| Regime | Count |
|--------|-------|
| trend | **12** |

### Confidence

| Confidence | Count |
|------------|-------|
| 0.20 | **10** |
| 0.35 | **2** |

### Directional bias / candidate side

| Field | Value | Count |
|-------|-------|-------|
| `directional_bias` | NONE | **12** |
| `candidate_side` | NONE | **12** |

### Block reasons

| Block reason | Count |
|--------------|-------|
| `skip_intent` | **12** |

### Representative BTC row pattern

- `decision_intent=soft_skip`
- `provider=groq`
- `confidence=0.20`
- `directional_bias=NONE`, `candidate_side=NONE`
- No `entry_trigger`, no `invalidation`, `mae_risk_estimate_pct=0.0`
- `risk_factors`: e.g. `high volatility`, `unclear trend`, `low trend strength`
- `why_not_valid_watch`: `intent_not_watch:soft_skip`, `candidate_side_none`, `paper_block:skip_intent`

---

## 5. BTC `valid_watch=0` root cause

**Primary cause:** `btc_consistently_skip_intent_no_watch_signal`

Interpretation:

1. **Not schema/provider field compliance** — N-R2 held side/trigger missing at 0.0; no forbidden repair; no `directional_bias_without_candidate_side`.
2. **Not MAE cap** — BTC decisions never reached watch intent; no MAE populated on skip rows.
3. **Not near-watch confirmation gap** — zero near-watch candidates (no row met majority of near-watch conditions).
4. **Consistent Groq conservative skip** — all 12 BTC ticks assigned to Groq returned `soft_skip` with NONE bias/side and low confidence (0.20 dominant).
5. **Provider asymmetry (observational)** — ETH `valid_watch=5` all via **Cerebras** (LONG/BUY, confidence avg 0.512, MAE avg 0.308). BTC never reached Cerebras paper-intent path in this sample.

**Conclusion:** BTC `valid_watch=0` is primarily **no-edge / skip-correct behavior**, not a broken schema path. Groq did not emit watch intent for BTC during N-R2.

---

## 6. BTC near-watch analysis

| Metric | Value |
|--------|-------|
| `btc_near_watch_candidate_count` | **0** |
| `btc_near_watch_failure_reasons` | `{}` |

Near-watch definition (majority of 8 conditions, not promoted): no BTC row qualified. Typical rows met only 2/8 conditions (`intent_soft_skip_or_watch`, `minor_block_only`). Missing: directional bias, candidate side, confidence ≥ 0.40, trigger, invalidation, MAE ≤ 0.35.

**No near-watch promotion occurred** — diagnostics only.

---

## 7. BTC vs ETH comparison

### ETH valid_watch reference (`count=5`)

| Condition | ETH pattern |
|-----------|-------------|
| Provider | cerebras (5/5) |
| Regime | trend (5/5) |
| `directional_bias` | LONG (5/5) |
| `candidate_side` | BUY (5/5) |
| Entry trigger | price_breakout (3), pullback_confirm (2) |
| Confidence avg | **0.512** |
| MAE avg | **0.308** |

### Delta summary

| Gap | Value |
|-----|-------|
| `confidence_gap` | **-0.1836** (BTC lower) |
| `provider_gap` | BTC: groq=12; ETH decisions: cerebras=7 |
| `bias_gap` | BTC: NONE=12; ETH: LONG=5, NONE=2 |
| `mae_gap` | null (BTC skip rows have no MAE) |
| `trigger_gap` | null (no BTC paper-intent rows) |
| `valid_watch_count_gap` | **-5** |
| `paper_intent_count_gap` | **-5** |

### Why ETH can `valid_watch=5` and BTC cannot

| Factor | ETH | BTC |
|--------|-----|-----|
| Watch intent | Cerebras emits `watch` with full paper fields | Groq emits `soft_skip` only |
| Directional edge | LONG + BUY present | NONE / NONE |
| Confidence | ~0.51 avg on valid watches | 0.20 (10), 0.35 (2) |
| Paper fields | trigger + invalidation + MAE populated | absent on skip |
| Graduation | 2 ETH graduations in calibration | 0 |

---

## 8. Issue classification

| Hypothesis | Assessment |
|------------|------------|
| Market condition / no edge | **PRIMARY** — consistent skip, low confidence, risk_factors cite unclear trend |
| Prompt / schema defect | **UNLIKELY** — field contract stable; no side/trigger missing on paper-intent rows elsewhere |
| Provider routing asymmetry | **SECONDARY OBSERVATION** — BTC all Groq; ETH valid watches all Cerebras; may warrant offline probe in 4.18-O2, not soak |
| Confidence floor | **N/A** — BTC never attempted watch |
| Sample size | **ADEQUATE** — 12 ticks over 60m; pattern is uniform, not sparse noise |

---

## 9. BTC prompt iteration recommendation

**`should_do_btc_prompt_iteration = false`** (for now)

Rationale:

- Tool primary cause is consistent skip with no watch intent — forcing prompt changes to elicit BTC watch would violate the "do not force BTC watch" gate.
- Skip when no edge is **correct behavior**.
- If operator later wants to probe whether Groq→Cerebras routing or BTC-specific examples change *intent distribution* (not graduation), that would be **Stage 4.18-O2** — offline prompt draft only, no soak until approved.

Suggested O2 directions (if ever approved — **not executed here**):

1. BTC examples: valid watch only with clear trend + side + trigger + MAE ≤ 0.35
2. BTC should `soft_skip` if no edge, not fake watch
3. BTC should not copy ETH behavior
4. BTC high-vol trend must still obey MAE cap
5. Confidence below floor should remain skip

---

## 10. Whether another 60m sample is justified

**No.**

- Pattern is uniform across all 12 BTC ticks (100% soft_skip).
- No near-watch candidates to suggest confirmation-window miss.
- Re-running 60m would not diagnose further without a code/prompt/routing change.
- Remain idle at gate.

---

## 11. Safety confirmation

| Check | Value |
|-------|-------|
| `offline_only` | **true** |
| `order_sent` | **false** |
| `exchange_private_api_called` | **false** |
| `mock_ai_used_count` (N-R2) | **0** |
| `order_sent_count` (N-R2) | **0** |
| `production_touched` | **false** |
| `btc_auto_touched` | **false** |
| demo / paper execution / ARM / radar | **not enabled** |
| New soak (30m/60m/6h/24h) | **not run** |
| Stage 4.19 | **not started** |

---

## 12. Final verdict

**`STAGE_4_18O_PASS`**

BTC `valid_watch=0` is explained by **consistent no-edge soft_skip** from Groq across 60m — not provider/schema regression from 418-N. Stage 4.19 remains **blocked**.

**Next step (gate):** Remain idle. Optional future **4.18-O2** offline BTC prompt/routing probe only if operator approves — **not** another 60m, **not** Stage 4.19, **not** RG threshold changes.

---

## 13. Commands run

```bash
python -m unittest tests.test_stage4_btc_specific_diagnostics -v

python tools/research/stage4_btc_specific_diagnostics.py \
  --input-dir /data/stage4_ai_decisions_418n_r2_provider_schema_60m \
  --paper-events-dir /data/stage4_paper_events_418n_r2_enforced \
  --calibration-dir /data/stage4_18n_r2_calibration \
  --failure-analysis-dir /data/stage4_18n_r2_failure_analysis \
  --output-dir /data/stage4_18o_btc_specific_diagnostics
```

Output artifacts on container:

- `/data/stage4_18o_btc_specific_diagnostics/stage4_btc_specific_diagnostics_summary.json`
- `/data/stage4_18o_btc_specific_diagnostics/stage4_btc_decision_rows.jsonl`

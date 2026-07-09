# Stage 4.18-O3 — Controlled Groq-vs-Cerebras BTC Provider Probe

**Date:** 2026-07-09 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Input (N-R2 frozen):** `/data/stage4_ai_decisions_418n_r2_provider_schema_60m`  
**Output:** `/data/stage4_18o3_controlled_provider_probe`  
**Mode:** diagnostic one-shot LLM probe — **no orders, no paper/calibration writes**

---

## 1. Executive summary

**Verdict: `STAGE_4_18O3_PASS`**

| Layer | Result |
|-------|--------|
| Controlled probe tool | **PASS** |
| Unit tests | **PASS** (6/6 O3 + 5/5 routing regression) |
| Live diagnostic probes | **6/6 executed** (3 contexts × 2 providers) |
| Groq BTC valid_watch | **0/3** |
| Cerebras BTC valid_watch | **1/3** (1 quota error) |
| `provider_divergence_detected` | **true** |
| Recommendation | `provider_routing_affects_btc_watch_yield` |
| Stage 4.19 | **BLOCKED** |

On **identical frozen BTC context**, Groq consistently `soft_skip` while Cerebras produced a **valid_watch** on context 1 (LONG/BUY, confidence 0.55, MAE 0.30). This confirms O2 routing asymmetry **materially affects BTC watch yield** — not purely market/no-edge.

**Do not** force BTC watch. **Do not** auto-change routing. Next: **Stage 4.18-P** provider routing design gate (operator approval).

---

## 2. O2 summary (why O3 was approved)

| Finding | Value |
|---------|-------|
| BTC provider | 100% Groq in N-R2 |
| ETH valid_watch | 100% Cerebras |
| `valid_watch_by_provider` | cerebras=6, groq=0 |
| `fallback_reason_counts` | groq_rate_limited=18 |
| `routing_asymmetry_detected` | true |

O3 was approved to answer: *on the same BTC context, would Groq and Cerebras diverge?*

---

## 3. Selected BTC contexts

| # | source_decision_id | original conf | original intent | regime | notes |
|---|-------------------|---------------|-----------------|--------|-------|
| 1 | `63dea621-...` | **0.20** | soft_skip | trend | typical low-conf skip |
| 2 | `eb05623b-...` | **0.35** | soft_skip | trend | highest BTC conf in N-R2 |
| 3 | `de975892-...` | **0.35** | soft_skip | trend | most recent BTC tick |

All contexts use **frozen** `market_context`, `account_context`, and `stage3_context_summary` from N-R2 — no new market fetch, no exchange private API.

---

## 4. Groq probe results

| Context | intent | confidence | bias | side | valid_watch |
|---------|--------|------------|------|------|-------------|
| 1 | soft_skip | 0.20 | NONE | NONE | **no** |
| 2 | soft_skip | 0.20 | NONE | NONE | **no** |
| 3 | soft_skip | 0.20 | NONE | NONE | **no** |

| Aggregate | Value |
|-----------|-------|
| `groq_probe_count` | **3** |
| `groq_soft_skip_count` | **3** |
| `groq_valid_watch_count` | **0** |
| `groq_avg_confidence` | **0.20** |
| `groq_directional_bias_distribution` | NONE=3 |

Groq is **uniformly conservative** on all three frozen BTC contexts — reproduces N-R2 behavior.

---

## 5. Cerebras probe results

| Context | intent | confidence | bias | side | MAE | valid_watch | notes |
|---------|--------|------------|------|------|-----|-------------|-------|
| 1 | **watch** | **0.55** | **LONG** | **BUY** | 0.30 | **yes** | trigger + invalidation present |
| 2 | soft_skip | 0.35 | NONE | NONE | — | no | agrees with Groq skip |
| 3 | — | — | — | — | — | no | `provider_quota_exhausted` |

| Aggregate | Value |
|-----------|-------|
| `cerebras_probe_count` | **3** |
| `cerebras_soft_skip_count` | **1** |
| `cerebras_valid_watch_count` | **1** |
| `cerebras_avg_confidence` | **0.30** (successful calls only) |
| `cerebras_directional_bias_distribution` | LONG=1, NONE=2 |

Cerebras **can** produce BTC valid_watch on identical context where Groq skipped.

---

## 6. Provider divergence result

| Metric | Value |
|--------|-------|
| `provider_divergence_detected` | **true** |
| `cerebras_btc_watch_possible` | **true** |
| `groq_btc_over_conservative_possible` | **true** |

**Key divergence (context 1):** Same prompt hash `b794831a6b4fa43e` — Groq `soft_skip` vs Cerebras `watch` with full paper fields and `would_be_valid_watch_under_current_rules=true`.

Context 2: both providers agree `soft_skip` — BTC no-edge **confirmed for that snapshot**.

Context 3: Cerebras quota exhausted — inconclusive for that tick.

---

## 7. Whether Cerebras BTC watch is possible

**Yes — under current rules, on at least one frozen N-R2 BTC context.**

Cerebras produced a schema-compliant valid_watch (LONG/BUY, MAE 0.30 ≤ 0.35 cap, trigger + invalidation). This was **diagnostic only** — not written to paper logger, calibration, or graduation.

---

## 8. Whether Groq appears over-conservative

**Yes — relative to Cerebras on context 1.**

Groq returned confidence 0.20 / NONE bias on all three probes. On context 1, Cerebras returned watch with 0.55 confidence. This supports `groq_btc_over_conservative_possible=true` **in comparison**, not as grounds to force watch.

---

## 9. Why BTC should still not be forced into watch

1. Only **1/3** Cerebras probes produced valid_watch; **2/3** were skip or error.
2. Context 2 shows **both providers agree skip** — genuine no-edge exists for some BTC snapshots.
3. Probe results are **not graduation evidence** — diagnostic only.
4. Routing change must go through **4.18-P design gate**, not ad-hoc threshold relaxation.
5. `should_force_btc_watch=false`, `should_change_rg_thresholds=false`.

---

## 10. Provider routing design gate recommendation

| Field | Value |
|-------|-------|
| `recommendation` | **`provider_routing_affects_btc_watch_yield`** |
| `proposed_next_stage` | **Stage 4.18-P provider routing design gate** |
| `should_change_provider_routing` | **false** (design only — no auto-change) |

O3 confirms: BTC `valid_watch=0` in N-R2 is **partially explained** by BTC always receiving Groq primary slot while valid_watch-capable responses come from Cerebras. Operator must approve any routing design before implementation.

---

## 11. Why Stage 4.19 remains blocked

| Criterion | Status |
|-----------|--------|
| BTC graduation in N-R2 calibration | **0** |
| Probe valid_watch → graduation | **not fed** (by design) |
| Operator approval for routing change | **not obtained** |
| `stage_419_readiness` | **false** |

---

## 12. Safety confirmation

| Check | Value |
|-------|-------|
| `diagnostic_only` | **true** |
| `paper_events_written` | **false** |
| `calibration_written` | **false** |
| `ai_decisions_appended` | **false** |
| `order_sent_count` | **0** |
| `mock_ai_used_count` | **0** |
| `exchange_private_api_called` | **false** |
| demo / paper execution / ARM / radar | **not enabled** |
| New soak (30m/60m/6h/24h) | **not run** |
| Stage 4.19 | **not started** |

---

## 13. Final verdict

**`STAGE_4_18O3_PASS`**

Controlled probe confirms **provider divergence on BTC**: Groq always skip; Cerebras can valid_watch on same context. BTC graduation=0 is **not purely market skip** — routing asymmetry is a contributing factor.

**Next step (gate):** Operator review **Stage 4.18-P** provider routing design. **Do not** auto-change routing. **Do not** start Stage 4.19.

---

## 14. Commands run

```bash
python -m unittest tests.test_stage4_controlled_provider_probe -v
python -m unittest tests.test_stage4_provider_routing_diagnostics -v

STAGE4_ORDER_ALLOWED=false python tools/research/stage4_controlled_provider_probe.py \
  --input-dir /data/stage4_ai_decisions_418n_r2_provider_schema_60m \
  --output-dir /data/stage4_18o3_controlled_provider_probe \
  --symbol BTCUSDT --providers groq,cerebras --max-contexts 3 --diagnostic-only
```

Output artifacts on container:

- `/data/stage4_18o3_controlled_provider_probe/stage4_controlled_provider_probe_summary.json`
- `/data/stage4_18o3_controlled_provider_probe/stage4_controlled_provider_probe_contexts.json`
- `/data/stage4_18o3_controlled_provider_probe/stage4_controlled_provider_probe_results.jsonl`

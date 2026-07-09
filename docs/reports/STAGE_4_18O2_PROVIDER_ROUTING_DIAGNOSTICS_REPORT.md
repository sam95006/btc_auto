# Stage 4.18-O2 — Provider Routing / BTC-vs-ETH Decision Probe

**Date:** 2026-07-09 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Input (N-R2 offline):** `/data/stage4_ai_decisions_418n_r2_provider_schema_60m`  
**Output:** `/data/stage4_18o2_provider_routing_diagnostics`  
**Mode:** offline replay only — **no LLM calls, no soak, no orders**

---

## 1. Executive summary

**Verdict: `STAGE_4_18O2_PASS`**

| Layer | Result |
|-------|--------|
| Routing diagnostics tool | **PASS** |
| Unit tests | **PASS** (5/5) |
| Offline N-R2 replay | **PASS** |
| `routing_asymmetry_detected` | **true** |
| `routing_asymmetry_likely_affected_btc` | **true** |
| Recommendation | `provider_routing_probe_recommended` |
| Stage 4.19 | **BLOCKED** |

418-O established BTC `valid_watch=0` as consistent Groq `soft_skip`. **418-O2 reveals this is not merely market/no-edge coincidence** — provider routing is structurally asymmetric: BTC and SOL are **100% Groq**; ETH and PEPE are **100% Cerebras** (all 18 Cerebras decisions followed `groq_rate_limited` fallback). All 6 `valid_watch` came from Cerebras; Groq produced **zero** valid_watch across all symbols.

**Do not** force BTC watch. **Do not** start Stage 4.19. **Do not** run O3 without operator approval.

---

## 2. 4.18-O summary (baseline)

| Metric | Value |
|--------|-------|
| Verdict | `STAGE_4_18O_PASS` |
| `btc_decision_count` | 12 |
| `btc_valid_watch_count` | 0 |
| `btc_soft_skip_count` | 12 |
| Primary cause | `btc_consistently_skip_intent_no_watch_signal` |
| ETH valid_watch | 5 (all Cerebras LONG/BUY) |

---

## 3. Why Stage 4.19 remains blocked

| Criterion | Status |
|-----------|--------|
| `calibration_eth_graduations > 0` | **yes** (2) |
| `calibration_btc_graduations > 0` | **no** (0) |
| BTC routing may suppress watch yield | **observed** — BTC never reached Cerebras |

Stage 4.19 requires BTC + ETH graduation > 0. Routing asymmetry means BTC graduation=0 may be **partially provider-routing-driven**, not purely market skip — but this does **not** justify forcing BTC watch or relaxing thresholds.

---

## 4. Provider routing by symbol

| Symbol | groq | cerebras | Dominant |
|--------|------|----------|----------|
| BTCUSDT | **12** | 0 | groq 100% |
| SOLUSDT | **12** | 0 | groq 100% |
| ETHUSDT | 0 | **7** | cerebras 100% |
| PEPEUSDT | 0 | **11** | cerebras 100% |

**Pattern:** Within each 12-tick soak, BTC and SOL always consumed the Groq primary slot. ETH and PEPE always arrived after Groq rate-limit fallback to Cerebras.

---

## 5. BTC provider concentration

| Metric | Value |
|--------|-------|
| `decision_count` | 12 |
| `dominant_provider` | **groq** |
| `dominant_share` | **1.0** |
| `btc_never_reached_cerebras` | **true** |

All BTC decisions: `soft_skip`, `directional_bias=NONE`, `confidence` avg **0.2125** (Groq bucket).

---

## 6. ETH provider concentration

| Metric | Value |
|--------|-------|
| `decision_count` | 7 |
| `dominant_provider` | **cerebras** |
| `dominant_share` | **1.0** |
| ETH valid_watch | **5** (all Cerebras) |
| `fallback_reason` | `groq_rate_limited` on all 7 |

ETH valid_watch rows: LONG/BUY, confidence avg **~0.51**, MAE avg **0.308** — only achievable via Cerebras path in this sample.

---

## 7. Groq vs Cerebras intent distribution

| Provider | decisions | soft_skip | watch | valid_watch | avg confidence |
|----------|-----------|-----------|-------|-------------|----------------|
| groq | **24** | **24** (100%) | 0 | **0** | **0.2125** |
| cerebras | **18** | 10 | 6 | **6** | **0.3517** |

| Field | groq | cerebras |
|-------|------|----------|
| `directional_bias=NONE` | 24/24 | 12/18 |
| `directional_bias=LONG` | 0 | 6/18 |
| MAE populated | 0 | 6 (avg 0.29) |

**Groq is uniformly conservative** across BTC+SOL — not BTC-specific conservatism alone. **Cerebras is the sole valid_watch source.**

---

## 8. Fallback reason distribution

| Reason | Count |
|--------|-------|
| `groq_rate_limited` | **18** |

All Cerebras decisions followed Groq rate-limit fallback. This confirms **provider chain exhaustion routing**, not random provider assignment.

---

## 9. Whether routing asymmetry likely matters

**Yes — strongly.**

| Evidence | Assessment |
|----------|------------|
| BTC 100% Groq, never Cerebras | **Routing slot order effect** |
| ETH/PEPE 100% Cerebras after fallback | **Fallback routing effect** |
| Groq 0 valid_watch globally | Groq path cannot graduate any symbol in N-R2 |
| Cerebras 6/18 valid_watch (33%) | Only fallback path produces watches |
| `fallback_reason_counts` = 18 | Groq exhausted before later symbols |

**Counterfactual (offline, no LLM rerun):** If BTC had received the Cerebras fallback slot on identical context, watch yield is **unknown** — but current `valid_watch=0` is **not explainable by market alone** because the only provider that produced watches never handled BTC.

`routing_asymmetry_likely_affected_btc` = **true**

---

## 10. O3 controlled provider probe recommendation

**`should_run_o3_controlled_provider_probe = true`** — **design only; operator approval required; not auto-executed.**

Stage 4.18-O3 candidate design (included in tool output):

- Same frozen BTC context from N-R2 tick
- Offline one-shot read-only LLM probe
- Compare Groq vs Cerebras BTC output side-by-side
- No orders, no paper execution, no watch promotion
- Output: `/data/stage4_18o3_btc_provider_probe`

---

## 11. Why BTC should not be forced into watch

1. Groq conservatism may be **correct** for BTC context — O3 must confirm before any prompt change.
2. Forcing watch via threshold relaxation would violate graduation gate integrity.
3. Routing fix (if any) must not auto-promote near-watch or bypass MAE cap.
4. Even if Cerebras would emit watch on BTC, operator must approve O3 before any provider probe.

**`should_force_btc_watch = false`**

---

## 12. Safety confirmation

| Check | Value |
|-------|-------|
| `offline_only` | **true** |
| `llm_providers_called` | **false** |
| `order_sent` | **false** |
| `exchange_private_api_called` | **false** |
| `mock_ai_used_count` (N-R2) | **0** |
| `order_sent_count` (N-R2) | **0** |
| demo / paper execution / ARM / radar | **not enabled** |
| New soak | **not run** |
| O3 probe | **not executed** |
| Stage 4.19 | **not started** |

---

## 13. Final verdict

**`STAGE_4_18O2_PASS`**

Provider routing asymmetry is **real and material**: BTC never reached Cerebras; all valid_watch came from Cerebras after Groq rate-limit fallback. BTC `valid_watch=0` is **partially routing-driven**, not purely market skip — but **do not force BTC watch**.

**Next step (gate):** Operator review O3 controlled provider probe design. **Do not** auto-run O3. **Do not** start Stage 4.19. **Do not** change RG thresholds.

---

## 14. Commands run

```bash
python -m unittest tests.test_stage4_provider_routing_diagnostics -v

python tools/research/stage4_provider_routing_diagnostics.py \
  --input-dir /data/stage4_ai_decisions_418n_r2_provider_schema_60m \
  --output-dir /data/stage4_18o2_provider_routing_diagnostics
```

Output: `/data/stage4_18o2_provider_routing_diagnostics/stage4_provider_routing_diagnostics_summary.json`

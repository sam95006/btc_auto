# Stage 4.18-P — Provider Routing Design Gate

**Date:** 2026-07-09 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Inputs:** N-R2 decisions, O2 routing diagnostics, O3 controlled probe  
**Output:** `/data/stage4_18p_provider_routing_design`  
**Mode:** design gate only — **no routing changes, no soak, no orders**

---

## 1. Executive summary

**Verdict: `STAGE_4_18P_PASS`**

| Layer | Result |
|-------|--------|
| Design gate tool | **PASS** |
| Unit tests | **PASS** (6/6) |
| `routing_problem_confirmed` | **true** |
| Recommended option | **Option 3 — BTC dual-provider shadow** |
| P1 implementation recommended | **true** (code-only; operator approval) |
| Stage 4.19 | **BLOCKED** |

O2 + O3 evidence confirms slot-order provider routing bias. P stage produces **four design options** and recommends **diagnostic-only BTC dual-provider shadow mode** (P1) — not aggressive Cerebras-first routing, not status quo as final fix.

**Do not** auto-implement P1. **Do not** auto-run soak. **Do not** start Stage 4.19.

---

## 2. O2 routing asymmetry summary

| Finding | Value |
|---------|-------|
| BTC provider | groq=12, cerebras=0 |
| ETH provider | cerebras=7 |
| `valid_watch_by_provider` | groq=0, cerebras=6 |
| `fallback_reason_counts` | groq_rate_limited=18 |
| `routing_asymmetry_detected` | true |
| `btc_never_reached_cerebras` | true |

BTC/SOL always consume Groq primary slot; ETH/PEPE receive Cerebras after rate-limit fallback.

---

## 3. O3 controlled provider divergence

| Metric | Groq | Cerebras |
|--------|------|----------|
| valid_watch | **0/3** | **1/3** |
| soft_skip | **3/3** | 1/3 |
| avg confidence | 0.20 | 0.30 |

`provider_divergence_detected=true` — same frozen BTC context: Groq skip vs Cerebras valid_watch on context 1.

---

## 4. Why Stage 4.19 remains blocked

| Criterion | Status |
|-----------|--------|
| BTC graduation (N-R2) | **0** |
| Non-shadow BTC valid_watch path | **not established** |
| Routing design implemented | **no** |
| Operator approval | **pending** |
| `stage_419_readiness` | **false** |

Stage 4.19 requires BTC + ETH graduation > 0 from **non-shadow** production decisions.

---

## 5. Routing problem statement

1. **Slot-order bias:** Symbol processing order binds BTC/SOL to Groq, ETH/PEPE to Cerebras fallback.
2. **Groq zero valid_watch:** All 6 N-R2 valid_watch from Cerebras only.
3. **BTC never reached Cerebras** in N-R2 soak.
4. **O3 confirms divergence** is not purely market — provider choice matters on identical context.
5. **Forcing BTC watch** would bypass edge validation — not acceptable.

---

## 6. Design options (4)

### Option 1 — Status quo (`groq,cerebras`)

| | |
|-|-|
| **Pros** | Minimal change; ETH path works via fallback |
| **Cons** | BTC/SOL slot bias persists |
| **Risk** | BTC graduation may stay 0 |
| **Role** | **Baseline only** — not final fix |

### Option 2 — Symbol-balanced rotation

| | |
|-|-|
| **Pros** | Eliminates permanent symbol-provider binding |
| **Cons** | Rate-limit complexity; needs regression soak |
| **Risk** | May destabilize working ETH path |
| **Role** | Gated experiment after shadow evidence |

### Option 3 — BTC dual-provider shadow (recommended)

| | |
|-|-|
| **Pros** | Safest; measures divergence without changing actual decision |
| **Cons** | Extra LLM cost when enabled |
| **Risk** | Shadow misuse if guards bypassed |
| **Role** | **P1 implementation target** |

### Option 4 — Cerebras-first BTC

| | |
|-|-|
| **Pros** | Directly tests BTC Cerebras path |
| **Cons** | Material routing change; O3 only 1/3 valid_watch |
| **Risk** | Provider overfitting; bypasses shadow phase |
| **Role** | Gated experiment only — not production default |

---

## 7. Recommended option

| Field | Value |
|-------|-------|
| `recommended_option` | **`option_3_btc_dual_provider_shadow`** |
| `recommended_next_stage` | **Stage 4.18-P1** |
| `p1_scope` | diagnostic-only BTC dual-provider shadow mode |

Priority rationale:
1. **Safety first** → Option 3 shadow
2. **Slot-order fix** → Option 2 only after shadow evidence
3. **Quick BTC proof** → Option 4 gated experiment only
4. **Status quo** → baseline, not improvement

---

## 8. Required safeguards

| Guard | Default |
|-------|---------|
| Shadow excluded from paper logger | **yes** |
| Shadow excluded from calibration | **yes** |
| Shadow excluded from graduation | **yes** |
| Shadow does not replace actual decision | **yes** |
| Shadow does not trigger order path | **yes** |
| `STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED` | **false** |
| `STAGE4_BTC_DUAL_PROVIDER_SHADOW` | **false** |
| Stage 4.19 must not use shadow results | **yes** |

---

## 9. P1 implementation recommendation

| Field | Value |
|-------|-------|
| `should_implement_p1` | **true** |
| `p1_scope` | diagnostic-only BTC dual-provider shadow mode |
| `should_run_soak_after_p1` | **false** (operator decides P1-R1 30m) |
| `should_start_419` | **false** |
| `requires_operator_approval` | **true** |

P1 is **code-only**. No soak auto-run. No routing auto-activation.

---

## 10. Why no new soak yet

- P stage is **design gate** — routing not implemented.
- Shadow mode does not exist until P1.
- Another soak without routing fix would reproduce N-R2 slot-order bias.
- Operator must approve P1 before any P1-R1 regression.

---

## 11. Safety confirmation

| Check | Value |
|-------|-------|
| `design_only` | **true** |
| `routing_changes_applied` | **false** |
| `llm_providers_called` | **false** |
| `order_sent_count` | **0** |
| `mock_ai_used_count` | **0** |
| demo / paper / ARM / radar / production / btc-auto | **not touched** |
| O3 probe fed to calibration | **no** |
| Stage 4.19 | **not started** |

---

## 12. Final verdict

**`STAGE_4_18P_PASS`**

Provider routing design gate complete. Recommended path: **P1 BTC dual-provider shadow** with strict guards. Remain at gate until operator approves P1 implementation.

---

## 13. Commands run

```bash
python -m unittest tests.test_stage4_provider_routing_design -v

python tools/research/stage4_provider_routing_design.py \
  --decisions-dir /data/stage4_ai_decisions_418n_r2_provider_schema_60m \
  --o2-dir /data/stage4_18o2_provider_routing_diagnostics \
  --o3-dir /data/stage4_18o3_controlled_provider_probe \
  --output-dir /data/stage4_18p_provider_routing_design
```

Output:

- `/data/stage4_18p_provider_routing_design/stage4_provider_routing_design_summary.json`
- `/data/stage4_18p_provider_routing_design/stage4_provider_routing_design_options.json`

# Stage 4.18-N — Provider-Specific JSON Schema / Output Repair Plan

**Date:** 2026-07-07 (UTC+8)  
**Trigger:** Stage 4.18-M-R1 **PARTIAL B** (`valid_watch_candidate_count=0`)  
**Mode:** code-only design — **no soak**, **no Stage 4.19**

---

## 1. M-R1 trigger summary

| Signal | M-R1 |
|--------|------|
| Technical soak | PASS (6/6, 23 effective) |
| `valid_watch_candidate_count` | **0** all symbols |
| `candidate_side_missing_rate` | BTC/SOL/ETH **1.0** |
| `missing_entry_trigger_rate` | ETH **1.0**, PEPE **1.0** |
| MAE within_cap | **3** (up from L-R1 **0**) but `within_cap > above_cap` still FAIL |
| Graduations | **0** |

**Decision:** Do **not** run 60m. Field contract must pass before longer samples.

---

## 2. Provider split (M-R1)

| Provider | Decisions | side_missing_rate | trigger_missing_rate | valid_watch |
|----------|-----------|-------------------|----------------------|-------------|
| Groq | **12** | **1.0** (12/12 paper intents) | **0.67** (8/12) | 0 |
| Cerebras | **11** | **0.17** (1/6 paper intents) | **1.0** (6/6) | 0 |

Both providers fail field contract. Groq dominates **side_missing**; Cerebras dominates **trigger_missing** when it handles paper intents.

---

## 3. Root cause hypothesis

1. **Prompt contract alone insufficient** — LLM still emits `candidate_side=NONE` with LONG/SHORT bias on majors.
2. **Groq** uses `json_object` mode — weaker field binding than strict JSON schema.
3. **Cerebras** uses `json_schema` but field omission persists on trigger/invalidation.
4. **MAE scale** — some improvement (within_cap 3) but still dominates blocks (`mae_above_cap=15`).

---

## 4. Stage 4.18-N goals

1. Analyze Groq vs Cerebras field compliance per decision (`stage4_provider_field_compliance_review.py`).
2. Provider-specific JSON schema / response format adjustments.
3. Post-parse **safe repair** policy:
   - **Allowed:** normalize empty containers, trim strings, fill missing nested dict shells
   - **Forbidden:** auto BUY/SELL from bias, MAE deflation, synthetic entry_trigger, watchlist promotion
4. Provider diagnostics in analyzer + review tool.
5. **No** new soak until N-R1 code pass.

---

## 5. Implementation plan

| Step | Deliverable |
|------|-------------|
| N-1 | `stage4_provider_field_compliance_review.py` (**done**) |
| N-2 | Groq: explore `response_format` / strict schema for watch fields |
| N-3 | Cerebras: tighten `json_schema` required properties (`candidate_side`, `entry_trigger`, `invalidation`) |
| N-4 | `stage4_schema_repair.py` — cosmetic repair only; explicit deny-list for side/MAE/trigger synthesis |
| N-5 | Tests + offline replay on M-R1 |
| N-R1 | Runtime-gated 30m after N code pass |

---

## 6. Repair policy (hard boundaries)

```text
ALLOWED:
  - normalize_empty_object_containers
  - coerce_string_trim
  - fill_missing_nested_dict_shells

FORBIDDEN:
  - auto_set_candidate_side_from_bias
  - deflate_mae_to_pass_cap
  - synthesize_entry_trigger_to_pass
  - promote_to_eligible_watchlist
```

---

## 7. Safety

- No orders, no RG threshold changes, no production/btc-auto
- Stage 4.19 remains blocked

---

## 8. Verdict

**`STAGE_4_18N_PLAN_READY`** — proceed with provider schema + safe repair implementation (code-only).

**Next:** Implement N-2..N-4, then **418-N-R1** 30m (operator-triggered).

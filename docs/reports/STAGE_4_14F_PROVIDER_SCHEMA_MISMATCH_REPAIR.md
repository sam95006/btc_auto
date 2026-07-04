# Stage 4.14f — Provider Schema Mismatch Repair

**Date:** 2026-07-05  
**Branch:** `stage3-demo-learning`  
**Prior session:** Stage 4.14d 6h clean validation — **PARTIAL PASS**

---

## 1. Stage 4.14d partial pass summary

| Metric | Value |
|--------|-------|
| output_dir | `/data/stage4_ai_decisions_414d_fixed_fleet_6h_clean` |
| duration | 360 min, 72/72 ticks, drift 0 |
| effective_decision_count | 268 (target 240) |
| parse_error_count | 1 |
| validator_passed | false |
| cerebras_truncation_retry | 6/6 success, 0 fail |

Operational layer: **PASS**. Validator blocked by 1 schema mismatch.

---

## 2. Decision 237 schema mismatch root cause

| Field | Value |
|-------|-------|
| decision_index | 237 (line 238) |
| decision_id | `7293461d-c787-4876-adfd-ded949a1f599` |
| symbol | **BTCUSDT** |
| provider | **cerebras** |
| finish_reason | **stop** (not truncation) |
| response_text_chars | 1257 |
| missing_fields | **`requires_manual_review`** only |
| invalid_fields | none |
| near_valid_json | **true** |
| truncation_retry | **not attempted** (unrelated) |

**Raw LLM response (excerpt):**
```json
{
  "final_action": "skip",
  "decision_intent": "watch",
  "symbol": "BTCUSDT",
  "candidate_side": "NONE",
  "confidence": 0.32,
  "why_enter": "...",
  "why_skip": "..."
}
```

Cerebras returned complete, valid JSON missing only the boolean `requires_manual_review`. All directional fields were already skip-safe.

---

## 3. Why truncation repair worked

414c repair handles `finish_reason=length` / `provider_response_truncated`. In 414d:
- 6 truncation events → 6 retries → 6 successes → **0 truncation parse errors**
- Decision 237 had `finish_reason=stop` — a different failure class

---

## 4. Schema mismatch repair policy

Two-tier repair in `stage4_schema_repair.py`:

### Tier 1: Cosmetic defaults (skip-safe only)
When `missing_fields` ⊆ non-directional fields AND response is skip-safe (`final_action=skip`, `candidate_side=NONE`):
- Fill `requires_manual_review=false`, empty strings, empty arrays
- Re-parse; preserve original watch/soft_skip intent

### Tier 2: Safe skip defaults (directional risk)
When missing directional fields OR `final_action=enter` OR `candidate_side=BUY/SELL`:
- Force `final_action=skip`, `decision_intent=hard_skip`, `confidence=0.0`, `candidate_side=NONE`
- Never repair into long/short/enter

---

## 5. Safe-skip-only defaults

```python
SAFE_SKIP_DEFAULTS = {
    "final_action": "skip",
    "decision_intent": "hard_skip",
    "candidate_side": "NONE",
    "confidence": 0.0,
    "risk_notes": ["provider_schema_mismatch_repaired_to_safe_skip"],
}
```

**Forbidden:** repairing malformed JSON into `enter`, `BUY`, `SELL`, or non-zero position size.

---

## 6. Why this does not change trading strategy

- `order_sent` remains `false` always
- Risk supervisor still evaluates all decisions
- Cosmetic repair preserves LLM skip/watch intent when already safe
- Directional repair only downgrades to hard_skip — never upgrades to trade
- No changes to fleet symbols, scheduler, provider chain, or prompt logic

---

## 7. 30m regression plan

- Output: `/data/stage4_ai_decisions_414f_schema_repair_30m_regression`
- PASS: tick 6/6, effective ≥ 20, parse_error=0, validator PASS
- If a schema mismatch occurs, `schema_mismatch_repair_success_count` should increment

---

## 8. Criteria for Stage 4.15

| Gate | Requirement |
|------|-------------|
| 414f 30m regression | validator PASS, parse_error=0 |
| Multi-session ops evidence | 414b + 414d 6h soaks (268+ effective each) |
| Truncation repair | validated (414c/414d) |
| Schema repair | validated (414f) |
| Safety | 0 orders, 0 mock across all sessions |

**Next:** Stage 4.15 decision-quality review (read-only analysis of existing datasets).

**Still forbidden:** demo order, ARM, radar, production, btc-auto, 6h re-soak unless operator requests.

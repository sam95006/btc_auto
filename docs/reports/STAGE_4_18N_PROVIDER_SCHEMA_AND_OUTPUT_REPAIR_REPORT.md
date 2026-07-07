# Stage 4.18-N — Provider Schema & Safe Repair Implementation Report

**Date:** 2026-07-07 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Mode:** code-only — **no soak**  
**Trigger:** Stage 4.18-M-R1 **PARTIAL B** (`valid_watch=0`)

---

## 1. M-R1 trigger summary

| Layer | M-R1 |
|-------|------|
| Technical | **PASS** (6/6, 23 effective) |
| Field contract | **FAIL** — `valid_watch=0` all symbols |
| Groq | `side_missing_rate=1.0`, `trigger_missing_rate=0.67` |
| Cerebras | `side_missing_rate=0.17`, `trigger_missing_rate=1.0` |
| Graduations | **0** |

---

## 2. Provider split diagnosis

| Provider | Primary failure | Root cause |
|----------|-----------------|------------|
| **Groq** | `candidate_side=NONE` with LONG/SHORT bias | `json_object` mode — weak field binding for side |
| **Cerebras** | `entry_trigger` missing / `type=none` | `json_schema` present but trigger not enforced |

---

## 3. Groq side contract (implemented)

- `GROQ_STRICT_OUTPUT_RULE` in `stage4_prompt_builder.py`
- Injected per Groq call via `inject_provider_strict_prompt()` in `stage4_provider_chain.py`
- Rules: watch/enter_candidate must have BUY/SELL; NONE only for skip; LONG→BUY, SHORT→SELL
- **No** auto-repair of NONE→BUY/SELL — block_reason preserved

---

## 4. Cerebras trigger contract (implemented)

- `CEREBRAS_STRICT_OUTPUT_RULE` in `stage4_prompt_builder.py`
- Injected per Cerebras call in provider chain
- `STAGE4_DECISION_JSON_SCHEMA` expanded: `entry_trigger`, `invalidation`, `directional_bias` required in `stage4_cerebras_payload.py`
- **No** synthetic entry_trigger repair

---

## 5. Safe repair policy (implemented)

`stage4_schema_repair.py` — cosmetic-only `apply_cosmetic_field_normalization()`:

| Allowed | Forbidden |
|---------|-----------|
| trim strings | auto_set_candidate_side_from_bias |
| normalize side/bias/trigger casing | synthesize_entry_trigger_to_pass |
| fill empty nested dict shells | deflate_mae_to_pass_cap |
| | promote_to_eligible_watchlist |

Repair metadata: `schema_repair_applied`, `schema_repair_safe_only`, `schema_repair_actions`, `schema_repair_forbidden_actions_detected`, `schema_repair_promoted_eligibility`

Offline probe CLI: `stage4_schema_repair.py --input-dir ... --output-dir ...`

---

## 6. Offline replay / probe (M-R1, no new soak)

| Tool | Output |
|------|--------|
| `stage4_provider_field_compliance_review.py` | `/data/stage4_18n_provider_field_compliance_review` |
| `stage4_paper_entry_failure_analyzer.py` | `/data/stage4_18n_m_r1_failure_analysis` |
| `stage4_schema_repair.py` (probe) | `/data/stage4_18n_schema_repair_probe_m_r1` |

Probe classifies forbidden repair needs on M-R1 — does **not** mutate source decisions.

---

## 7. Tests

| Module | Result |
|--------|--------|
| `test_stage4_provider_field_compliance_review` | PASS |
| `test_stage4_schema_repair` | PASS |
| `test_stage4_paper_entry_failure_analyzer` | PASS |
| `test_stage4_ai_decision_layer` (418-N additions) | PASS |

---

## 8. Why 60m remains blocked

M-R1 field contract failed (`valid_watch=0`). Longer samples cannot fix provider/schema output gaps. **60m not proposed.**

---

## 9. Why Stage 4.19 remains blocked

No valid watch candidates, no BTC/ETH graduations, `recommended_mode_for_419=none`. **Operator approval required** after N-R1 passes field contract.

---

## 10. Next regression plan

**Stage 4.18-N-R1:** Runtime-gated **30m** provider schema regression after code deploy/sync.

Pass criteria: `valid_watch_candidate_count > 0`, side/trigger rates down, `schema_repair_promoted_eligibility_count=0`.

If N-R1 still `valid_watch=0` → deeper provider JSON schema / model output layer changes; **not** longer soak.

---

## 11. Safety confirmation

| Check | Value |
|-------|-------|
| Orders / mock / exchange | **0 / 0 / false** |
| Production / btc-auto / ARM / radar | **not touched** |
| RG thresholds | **unchanged** |
| Stage 4.19 | **NOT started** |

---

## Verdict

**`STAGE_4_18N_CODE_PASS`** — stopped at gate. Next: **418-N-R1** 30m (operator-triggered).

# Stage 4.18-M — Structured Output / Schema Hardening

**Date:** 2026-07-07 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Mode:** code + offline L-R1 replay only — **no soak**  
**Input:** `/data/stage4_ai_decisions_418l_r1_field_compliance_30m`  
**Analyzer output:** `/data/stage4_18m_l_r1_failure_analysis`

---

## 1. L-R1 result summary

| Layer | L-R1 |
|-------|------|
| Technical | **PASS** (6/6 ticks, 24 effective, parse=0, order=0) |
| Field compliance | **PARTIAL** (side/trigger rates improved on some symbols) |
| `valid_watch_candidate_count` | **0** all symbols |
| MAE | **REGRESSED** (within_cap 0 vs J-R1 2; above_cap 18 vs 13) |
| Graduations | **0** |
| Verdict | **PARTIAL** |

Prompt-only iteration (418-L) insufficient. LLM still outputs inflated MAE (1.0–3.0%) and missing side on majors.

---

## 2. Why 60m is not recommended

- `valid_watch_candidate_count=0` on L-R1
- MAE scale drift (e.g. 0.30% written as 1.5–3.0%) dominates blocks
- Longer sample cannot fix structured field contract failures
- **60m deferred** until **418-M-R1** field contract passes

---

## 3. Why Stage 4.19 remains blocked

- `calibration_total_graduations=0`
- `recommended_mode_for_419=none`
- `within_cap > above_cap` not met
- Operator gate requires BTC **and** ETH graduation with quality PASS

**Stage 4.19 was NOT started.**

---

## 4. Structured output contract (418-M)

Added to `stage4_prompt_builder.py`:

1. `candidate_side` REQUIRED for watch / enter_candidate
2. LONG → BUY, SHORT → SELL; NONE only for skip intents
3. `entry_trigger.type` must not be `none`
4. `invalidation` required
5. MAE must match invalidation distance in percent
6. Bad vs corrected output examples

---

## 5. Schema enforcement changes

**Files:** `stage4_paper_readiness.py`, `stage4_decision_schema.py` (via enrich)

| Rule | Behavior |
|------|----------|
| A1 Side derivation | `derived_candidate_side_suggestion=BUY/SELL` diagnostic only; **no auto-fill**; block `directional_bias_without_candidate_side` |
| A2 Required fields | Strict: side != NONE, trigger type != none + condition, invalidation price or max_adv, MAE present |
| A3 MAE scale drift | BTC/ETH: mae ≥ 1.0 while max_adv ≤ cap → `mae_scale_drift_suspected` |
| A4 MAE cap | Unchanged — BTC/ETH 0.35%, SOL 0.25%, PEPE 0.20% |

Logger/simulator: incomplete decisions filtered via `is_eligible_decision` before graduation path.

---

## 6. MAE scale drift detection

- Does **not** normalize or deflate MAE
- Flags `mae_scale_drift_suspected=true` when LLM MAE implies 10× scale error vs invalidation distance
- Blocks paper readiness only; not `parse_error`

---

## 7. Analyzer changes (418-M)

**File:** `stage4_paper_entry_failure_analyzer.py`

New outputs:

- `derived_candidate_side_suggestion_count`
- `mae_scale_drift_suspected_count`
- `no_valid_watch_candidate_count`
- `field_contract_failure_by_symbol` (side/trigger/invalidation/mae/drift/above_cap)
- Recommendations: `structured_schema_side_required`, `structured_schema_trigger_required`, `mae_scale_contract_or_provider_specific_prompt`, `do_not_extend_sample_until_field_contract_passes`

---

## 8. Offline replay on L-R1

Commands (Zeabur container):

```bash
python tools/research/stage4_paper_entry_failure_analyzer.py \
  --input-dir /data/stage4_ai_decisions_418l_r1_field_compliance_30m \
  --paper-events-dir /data/stage4_paper_events_418l_r1_enforced \
  --calibration-dir /data/stage4_18l_r1_calibration \
  --output-dir /data/stage4_18m_l_r1_failure_analysis

python tools/research/stage4_paper_event_logger.py \
  --input-dir /data/stage4_ai_decisions_418l_r1_field_compliance_30m \
  --output-dir /data/stage4_paper_events_418m_enforced_l_r1 \
  --mode append-only

python tools/research/stage4_watchlist_followup_simulator.py \
  --calibration-replay \
  --input-dir /data/stage4_ai_decisions_418l_r1_field_compliance_30m \
  --paper-events-dir /data/stage4_paper_events_418m_enforced_l_r1 \
  --output-dir /data/stage4_18m_enforced_l_r1_calibration
```

Replay confirms L-R1 failures under **418-M** enforcement lens; does not increase graduations.

### Offline replay metrics (418-M on L-R1)

| Metric | Value |
|--------|-------|
| `derived_candidate_side_suggestion_count` | **13** |
| `mae_scale_drift_suspected_count` | **0** |
| `no_valid_watch_candidate_count` | **19** |
| `offline_logger_events_written` | **0** |
| `offline_logger_watchlist_count` | **0** |
| `offline_calibration_graduations` | **0** |
| `offline_recommended_mode_for_419` | **none** |

### field_contract_failure_by_symbol

| Symbol | side | trigger | invalidation | mae | drift | above_cap |
|--------|------|---------|--------------|-----|-------|-----------|
| BTCUSDT | 6 | 3 | 1 | 0 | 0 | 6 |
| ETHUSDT | 2 | 3 | 0 | 0 | 0 | 3 |
| SOLUSDT | 5 | 1 | 0 | 0 | 0 | 5 |
| PEPEUSDT | 1 | 5 | 0 | 0 | 0 | 5 |

**Analyzer recommendations:** `structured_schema_side_required`, `structured_schema_trigger_required`, `do_not_extend_sample_until_field_contract_passes`

---

## 9. Next step recommendation

**418-M-R1:** Runtime-gated **30m** structured-output regression after code pass.

- Success: `valid_watch_candidate_count > 0`, `mae_scale_drift_suspected_count` drops, field contract failures drop
- **60m** only if field contract passes but `no_consecutive_tick` blocks graduation — **operator approval required**

If M-R1 still fails field contract → **418-N** provider-specific JSON schema / repair path (not longer soak).

---

## 10. Safety confirmation

| Check | Value |
|-------|-------|
| 30m / 60m soak in this step | **NO** |
| Stage 4.19 started | **NO** |
| `order_sent_count` | 0 |
| RG thresholds changed | **NO** |
| Production / btc-auto / ARM / radar | **not touched** |

---

## 11. Verdict

**`STAGE_4_18M_CODE_PASS`** — structured output hardening complete; stopped at gate.

**Next:** **418-M-R1** 30m runtime-gated regression (operator-triggered).

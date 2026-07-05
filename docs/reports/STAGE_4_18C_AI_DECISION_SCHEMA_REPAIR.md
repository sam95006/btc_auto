# Stage 4.18-C — AI Decision Prompt / Schema Repair

**Date:** 2026-07-05  
**Branch:** `stage3-demo-learning`  
**Prerequisite:** Stage 4.18-B `d0ead7e` — `recommended_mode_for_419=none`  
**Mode:** **Schema / prompt / parser / validator only — no execution**

---

## 1. Executive summary

Stage 4.18-B confirmed that **MAE cap violation at 100%** blocks all 7 confirmed BTC/ETH watchlists. Side memory and confidence floors cannot produce hypothetical graduations. Root cause is **upstream AI decision quality**, not formal Risk Governor thresholds.

Stage 4.18-C adds **paper-readiness fields** to the Stage 4 LLM decision schema, prompt, parser enrichment, validator metrics, paper event logger, and watchlist simulator. Decisions missing required directional paper fields are marked `decision_quality_incomplete` (not `parse_error`) and are excluded from paper pipeline replay.

**Stage 4.19 remains NOT ready.** Next gate: **Stage 4.18-D** — 30m read-only schema regression soak.

---

## 2. Stage 4.18-B zero graduation root cause

| Finding | Detail |
|---------|--------|
| Confirmed watchlists | 7 BTC/ETH across fleet datasets |
| Graduations at MAE 75/90/100% | **0** |
| Primary blocker | `mae_cap_violation` even at 100% cap (228 blocks) |
| `candidate_side_none` in 4.18-B | **0** — MAE blocks before side resolution |
| Side memory | No effect |
| Confidence floor mode | No graduations |

Hypothesis: AI watch/enter outputs lack structured directional risk context; MAE proxy from market vol alone exceeds caps on graduation ticks.

---

## 3. Why formal RG MAE thresholds must NOT be loosened

- 4.18-B swept candidate caps to 100% offline — still 0 graduations.
- Loosening live RG MAE would mask poor decision quality and violate Phase 8 governance boundaries.
- SOL/PEPE remain unsuitable for graduation per fleet evidence.
- Correct fix path: **improve LLM output** → re-run read-only soak → re-run 4.18-B calibration.

---

## 4. New decision schema fields

```json
{
  "directional_bias": "LONG|SHORT|NONE",
  "side_confidence": 0.0,
  "watch_followup_required": true,
  "watch_confirmation_reason": "...",
  "entry_trigger": {
    "type": "price_breakout|pullback_confirm|momentum_confirm|none",
    "trigger_price": 0.0,
    "trigger_condition": "..."
  },
  "invalidation": {
    "invalidation_price": 0.0,
    "invalidation_reason": "...",
    "max_adverse_move_pct": 0.0
  },
  "mae_risk_estimate_pct": 0.0,
  "mfe_potential_estimate_pct": 0.0,
  "risk_reward_estimate": 0.0,
  "paper_readiness": {
    "eligible_for_watchlist": true,
    "eligible_for_hypothetical_entry": false,
    "block_reason": "..."
  },
  "decision_quality_incomplete": false
}
```

Module: `tools/research/stage4_paper_readiness.py`

---

## 5. Watch / enter_candidate requirements

### `watch`

Must include:

- `directional_bias` ≠ NONE
- `watch_confirmation_reason` (non-empty)
- `invalidation` (price or reason)
- `mae_risk_estimate_pct` > 0

Watch cannot become entry in the same tick.

### `enter_candidate`

Must include:

- `candidate_side` ≠ NONE
- `directional_bias` ≠ NONE
- `entry_trigger` (type ≠ none + condition)
- `invalidation`
- `mae_risk_estimate_pct` > 0
- `risk_reward_estimate` > 0

If direction unclear → use `soft_skip` / `hard_skip`, **not** `enter_candidate` with NONE side.

### Incomplete quality

- Missing directional fields → `decision_quality_incomplete=true`
- **Not** `parse_error` — decision still parses and is logged
- `paper_readiness.eligible_for_hypothetical_entry=false`
- Schema repair **never** fabricates trade direction

---

## 6. Component impact

| Component | Change |
|-----------|--------|
| `stage4_decision_schema.py` | Optional paper fields; post-parse enrichment |
| `stage4_prompt_builder.py` | Prompt + schema hint + instructions |
| `stage4_schema_repair.py` | Safe NONE defaults; no directional fabrication |
| `stage4_ai_decision_agent.py` | Persist paper fields on decision row |
| `validate_stage4_ai_decision_outputs.py` | Paper readiness metrics in validation JSON |
| `run_stage4_ai_decision_dry_run.py` | Summary includes paper readiness metrics |
| `stage4_paper_event_logger.py` | Blocks `decision_quality_incomplete` |
| `stage4_watchlist_followup_simulator.py` | Inherits eligibility via paper logger |

### Summary metrics added

```json
{
  "directional_bias_present_count": 0,
  "directional_bias_none_count": 0,
  "enter_candidate_missing_side_count": 0,
  "watch_with_directional_bias_count": 0,
  "paper_ready_watch_count": 0,
  "paper_ready_enter_candidate_count": 0,
  "decision_quality_incomplete_count": 0,
  "mae_risk_estimate_present_count": 0,
  "entry_trigger_present_count": 0,
  "invalidation_present_count": 0
}
```

---

## 7. Next step — Stage 4.18-D read-only regression plan

1. Deploy schema/prompt changes to Stage 3 demo-learning Zeabur service.
2. Run **30m fixed-fleet read-only dry-run** (`STAGE4_DRY_RUN_ONLY=true`, no orders).
3. Validate: `parse_error_count=0`, paper readiness metrics vs 4.17/4.18 baseline.
4. Re-run paper event logger + 4.18-B MAE calibration replay.
5. Gate: if `paper_ready_watch_count > 0` or improved MAE estimates → reconsider 4.19 path.

**Not started in this stage.**

---

## 8. Explicit prohibitions

- No orders, demo orders, paper order execution
- No ARM, radar, production, btc-auto
- No 6h / 24h soak (4.18-D only when operator approves)
- No formal Risk Governor threshold changes
- No `applied_patches` / reflection auto-apply
- Stage 4.19 **not** auto-started

---

**final_verdict:** `STAGE_4_18C_AI_DECISION_SCHEMA_REPAIR_COMPLETE`

**Stopped at gate — awaiting Stage 4.18-D operator approval.**

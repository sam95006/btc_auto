# Stage 4.18-P2D — ETH Follow-up Confirmation Prompt Review / Repair

**Verdict:** `STAGE_4_18P2D_PASS`  
**Mode:** code-only prompt / diagnostic repair (offline static review)  
**Date:** 2026-07-13  
**Output:** `/data/stage4_18p2d_eth_followup_confirmation_prompt_review`

---

## 1. P2C recap

P2C classified ETH LONG/BUY → NONE/NONE as `confirmation_prompt_too_strict`:

- tick gap = 1
- price Δ ≈ -0.127%
- regime trend→trend
- trend_strength 0.41→0.64 (improved)
- data_quality ok→ok
- invalidation / MAE not breached
- entry_trigger not rechecked
- market_valid=false / system_issue=true

---

## 2. Why ETH failure is a system confirmation issue

Follow-up ticks previously used the **same blank-slate decision prompt** with **no previous_watch_context**. The LLM could hard_skip to NONE/NONE without rechecking the prior watch’s trigger / invalidation / MAE / context continuity — even when market context was stable or improved.

---

## 3. Prompt repair scope

| File | Change |
|------|--------|
| `tools/research/stage4_prompt_builder.py` | P2D follow-up rules in SYSTEM_PROMPT; `previous_watch_context` kwarg; follow-up user instructions; diagnostic schema fields |
| `tools/research/stage4_ai_decision_agent.py` | Load last same-symbol watch from `STAGE4_OUTPUT_DIR/ai_decisions.jsonl` and inject into prompt; persist diagnostic fields on decision rows |
| `tools/research/stage4_eth_followup_confirmation_prompt_review.py` | Offline static coverage + P2C replay classification |

**Not changed:** Risk Governor thresholds, MAE caps, confidence floors, provider routing defaults, order path, Stage 4.19 gate.

---

## 4. Previous watch recheck requirement

When `previous_watch_context` is present, follow-up MUST:

- set `previous_watch_rechecked=true`
- set `entry_trigger_rechecked=true`
- fill `entry_trigger_status` / `invalidation_status` / `mae_status` / `context_continuity_status`
- treat the tick as follow-up confirmation, not a fresh decision

---

## 5. Direction collapse guard

LONG/BUY → NONE/NONE is allowed only with `direction_collapse_allowed=true` and an explicit reason:

- `invalidation_breached`
- `mae_breached`
- `regime_reversal`
- `data_quality_degraded`
- `entry_trigger_failed`
- `major_risk_factor_added`

Otherwise prefer `watch` (continuation / confirmation_pending) or `soft_skip` **retaining** prior bias/side.

---

## 6. Confidence collapse reason requirement

Confidence must not drop from a valid watch (e.g. 0.55 → 0.0) without `collapse_reason` / `confidence_reason`.

---

## 7. Static replay result

| Check | Result |
|-------|--------|
| `p2c_case_loaded` | true |
| `prompt_repair_added` | true |
| `direction_collapse_guard_added` | true |
| `confidence_collapse_reason_required` | true |
| `static_expected_followup_behavior` | `continuation_watch_or_confirmation_pending` |
| `would_prevent_unexplained_collapse` | **true** |
| `needs_next_runtime_regression` | **true** |

No LLM call. Existing decisions not rewritten.

---

## 8. Why no 30m / 60m now

Prompt text + wiring are repaired, but behavior must be proven on a **small runtime regression** after deploy/sync — not assumed from static review alone. Auto-running 30m/60m now is premature.

`should_run_30m_now=false` · `should_run_60m=false`

---

## 9. Why Stage 4.19 remains blocked

- ETH graduation still 0
- Prompt repair not yet runtime-validated
- Permanent routing still unsupported

`stage_419_readiness=false` · `should_start_419=false`

---

## 10. Safety confirmation

| Check | Result |
|-------|--------|
| Offline / static only for P2D review tool | yes |
| LLM called in P2D review | no |
| Orders / exchange private API | no |
| MAE cap / confidence floor / RG / routing defaults | unchanged |
| Stage 4.19 started | no |

---

## 11. Next recommended runtime regression

Operator-gated **short read-only regression** (after prompt sync to runtime):

Confirm ETH follow-up no longer collapses LONG/BUY → NONE/NONE without reversal / invalidation / MAE / explicit collapse reason.

Do **not** auto-start Stage 4.19. Do **not** permanently change routing.

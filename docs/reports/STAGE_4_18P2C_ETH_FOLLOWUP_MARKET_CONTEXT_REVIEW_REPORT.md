# Stage 4.18-P2C — ETH Follow-up Market Context / Confirmation Review

**Verdict:** `STAGE_4_18P2C_PASS`  
**Mode:** offline diagnostics / code-only  
**Date:** 2026-07-13  
**Source:** Stage 4.18-P2-R1 actual-only decisions + P2B + P2A  
**Output:** `/data/stage4_18p2c_eth_followup_market_context_review`

---

## 1. P2B recap

P2B established:

| Item | Value |
|------|--------|
| ETH valid_watch | 1 |
| ETH follow-up tick | 1 |
| ETH graduation | 0 |
| Watch | Cerebras / watch / 0.55 / LONG / BUY / MAE 0.3 cap passed |
| Follow-up | Cerebras / hard_skip / 0.0 / NONE / NONE |
| Failure | `eth_followup_direction_changed` |
| Invalidation / MAE breach | false / false |
| Recommendation | market-context / confirmation review |

P2C answers whether that collapse was **market-valid** or a **confirmation / reasoning system issue**.

---

## 2. ETH watch → follow-up timeline

| Field | Watch (tick 3) | Follow-up (tick 4) |
|-------|----------------|--------------------|
| Provider | cerebras | cerebras |
| Intent | watch | hard_skip |
| Confidence | 0.55 | 0.0 |
| Bias / side | LONG / BUY | NONE / NONE |
| MAE | 0.3 | — |
| Entry trigger rechecked | — | **false** |
| Tick gap | — | **1** |

Same provider, next tick, full directional collapse without invalidation or MAE breach.

---

## 3. Market context delta

| Metric | Before | After |
|--------|--------|-------|
| Price change % | — | **-0.127%** |
| Regime | trend | trend (unchanged) |
| Trend strength | 0.4095 | **0.6389** (stronger) |
| Data quality | ok | ok |
| Volatility / funding / OI / CVD | missing | missing |

Context did **not** degrade. Trend strength improved. Price move was tiny (~13 bps). No missing_data / edge_factors / risk_factors on follow-up.

---

## 4. Entry trigger / invalidation / MAE

| Check | Result |
|-------|--------|
| `entry_trigger_rechecked` | false |
| `entry_trigger_confirmed_by_context` | false |
| `invalidation_breached` | **false** |
| `mae_breached` | **false** |

Watch had a valid trigger + invalidation + MAE within cap. Follow-up did not re-validate the trigger; it jumped straight to hard_skip / NONE.

---

## 5. Why follow-up became hard_skip

Observed collapse:

- confidence 0.55 → 0.0
- LONG/BUY → NONE/NONE
- intent watch → hard_skip
- block_reason ≈ skip_intent
- no risk_factors, no edge_factors, no missing_data spike

Market context does **not** support a forced reversal narrative (regime stable, trend stronger, sub-0.15% move).

---

## 6. BTC success context comparison

Loaded **3** BTC watch-context patterns from P2-R1 actual-only rows.

Key contrast — successful retention pair (BTC watch idx 3 → follow 4):

| Field | Watch | Follow-up |
|-------|-------|-----------|
| Intent | watch | **watch** (retained) |
| Confidence | 0.58 | **0.66** (up) |
| Bias / side | LONG / BUY | **LONG / BUY** (retained) |
| Entry trigger | pullback_confirm | **price_breakout** (rechecked / updated) |
| Price Δ | — | +0.015% |

BTC success pattern: follow-up **keeps directional structure**, updates entry trigger, and can raise confidence.  
ETH failure pattern: follow-up **drops to hard_skip NONE** without trigger recheck and without adverse context.

(One earlier BTC watch also softened to soft_skip/NONE under a larger ~0.15% move; graduation still came from actual-only calibration path — the retained LONG/BUY pair is the instructive contrast for ETH.)

---

## 7. Root cause classification

**Primary:** `confirmation_prompt_too_strict`

Criteria matched:

- market_context not worsened (trend stronger)
- invalidation / MAE not breached
- follow-up hard_skip with confidence=0
- same provider collapse LONG/BUY → NONE/NONE

| Flag | Value |
|------|--------|
| `confirmation_failure_is_market_valid` | **false** |
| `confirmation_failure_is_system_issue` | **true** |
| Secondary note | entry trigger was also **not rechecked** |

Not classified as `real_market_reversal_or_no_edge` (insufficient adverse context).  
Not `followup_context_missing_or_degraded` (data_quality ok, no missing spike).

---

## 8. Recovery recommendation

`eth_followup_confirmation_prompt_review`

Suggested next (code-only / gated; **not auto-started**):

1. Review ETH follow-up confirmation prompt for over-strict skip when context is stable.
2. Optionally add follow-up entry-trigger recheck diagnostics.
3. Do **not** relax MAE cap or confidence floor in this step.
4. Do **not** change schema / state machine until prompt review scope is approved.

| Flag | Value |
|------|--------|
| `needs_eth_prompt_fix` | **true** |
| `needs_eth_schema_fix` | false |
| `needs_followup_state_machine_review` | false |
| `needs_context_quality_fix` | false |
| `needs_another_short_sample` | false |

---

## 9. Why 60m is not justified now

- Root cause is confirmation / prompt behavior, not sample-length scarcity.
- One clear ETH watch→follow-up pair already isolates the failure mode.
- Extending soak would not answer prompt-strictness vs market-reversal without a prompt review.

`should_run_60m=false`

---

## 10. Why Stage 4.19 remains blocked

- ETH graduation still 0.
- Confirmation path still fails on the only ETH valid_watch.
- Routing permanent change still unsupported.
- Operator approval still required for any routing experiment.

| Flag | Value |
|------|--------|
| `stage_419_readiness` | **false** |
| `should_start_419` | **false** |
| `routing_permanent_change_supported` | **false** |
| `operator_approval_required` | **true** |

---

## 11. Safety confirmation

| Check | Result |
|-------|--------|
| Offline only | yes |
| LLM called | no |
| Orders / exchange private API | no |
| Prompt / schema / state machine code changed | **no** (review only) |
| MAE / confidence floor changed | no |
| Permanent routing change | no |
| Stage 4.19 started | no |
| 30m / 60m soak run | no |

---

## 12. Final verdict

**`STAGE_4_18P2C_PASS`**

ETH LONG/BUY → NONE/NONE was **not** a clear market reversal. Context was stable-to-stronger; failure is a **system confirmation issue** classified as `confirmation_prompt_too_strict`, recommendation `eth_followup_confirmation_prompt_review`.

**Gate:** stop here. Do not auto-run 30m/60m. Do not start Stage 4.19. Do not permanently change routing.

**Next (operator-gated):** ETH follow-up confirmation prompt review (code-only), still without soak / 4.19 / routing enable.

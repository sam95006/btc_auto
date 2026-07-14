# Stage 4.18-P2H — Backend Hold State + Passive Gate Checker

**Verdict:** `STAGE_4_18P2H_PASS`  
**Mode:** code-only / docs-only (no runtime soak)  
**Date:** 2026-07-14  

---

## 1. Purpose

Freeze the P2G operator decision into a backend **HOLD** posture and add a passive checker that can evaluate *future* Stage4 outputs for ETH watch reappearance — without auto-starting regressions or Stage 4.19.

---

## 2. Backend hold state

| Field | Value |
|-------|--------|
| backend_hold_state | HOLD |
| reason | ETH watch conditions not present |
| next_short_regression_allowed_now | false |
| should_run_30m_now | false |
| should_run_60m | false |
| stage_419_readiness | false |
| should_start_419 | false |
| routing_permanent_change_supported | false |
| operator_action | wait_for_eth_watch_conditions_reappear |

This is intentional conditional waiting — not a failed system.

---

## 3. Passive gate checker

Tool: `tools/research/stage4_eth_future_regression_gate_checker.py`

Input: any future Stage4 output dir containing `stage4_ai_decision_summary.json` / `ai_decisions.jsonl` (and optional paper/calibration side files if present).

Checks ETH actual-only rows for:

1. watch or valid_watch  
2. directional_bias != NONE  
3. candidate_side != NONE  
4. confidence >= 0.45  
5. entry_trigger present  
6. invalidation present  
7. MAE cap passed  
8. data_quality ok  
9. regime not unknown  

---

## 4. Decision rules

| ETH conditions | Recommendation |
|----------------|----------------|
| not present | `continue_hold_no_regression` |
| present | `operator_may_approve_short_regression` |

Always:

- `should_run_30m_now=false` (never auto)  
- `should_run_60m=false`  
- `should_start_419=false`  
- `auto_start_regression=false`  
- `auto_start_419=false`  

Operator approval remains mandatory before any short regression.

---

## 5. Why no runtime now

P2G established ETH watch reappearance gate is not ready (`sample_market_no_edge` lineage). Running another soak would not exercise P2D prompt repair validation.

---

## 6. Why Stage 4.19 remains blocked

Actual non-shadow BTC + ETH graduation must both be > 0. Prior unilateral BTC evidence / readiness packs / checkers cannot open Stage 4.19.

---

## 7. Safety

Offline evaluation only; no LLM; no orders; no exchange private API; no MAE/RG/confidence/prompt/routing permanent changes; no production/btc-auto.

---

## 8. Tests

```text
python -m unittest tests.test_stage4_eth_future_regression_gate_checker -v
```

---

## 9. Final verdict

**`STAGE_4_18P2H_PASS`**

Backend entered HOLD with a passive future checker. Conditions, not impatience, gate the next short regression.

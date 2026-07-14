# Stage 4.18-P2F — ETH Watch Reappearance Gate + Regression Readiness

**Verdict:** `STAGE_4_18P2F_PASS`  
**Mode:** offline gate / code-only  
**Date:** 2026-07-14  
**Source:** P2E + P2B/P2C/P2D references + P2D-R1 decisions  
**Output:** `/data/stage4_18p2f_eth_watch_reappearance_gate`

---

## 1. P2E recap

| Item | Value |
|------|--------|
| Verdict | `STAGE_4_18P2E_PASS` |
| Commit | `907e5f2` |
| no_watch_root_cause | `sample_market_no_edge` |
| prompt_repair_over_conservative_suspected | false |
| needs_prompt_adjustment | false |
| should_run_60m | false |
| wait helper | fixed |

P2D repair remains on runtime; P2D-R1 never produced ETH watch, so repair effectiveness was unvalidated. P2E showed this was sample no-edge, not prompt over-conservative.

---

## 2. Why no 60m

Extending soak duration does not create ETH edge. Gate policy: wait for ETH watch-like conditions to reappear, then consider operator-approved **short** regression only. `should_run_60m=false` always for this stage.

---

## 3. P2B/P2C ETH watch reference

| Field | Reference |
|-------|-----------|
| provider | cerebras |
| intent | watch |
| confidence | 0.55 |
| directional_bias | LONG |
| candidate_side | BUY |
| mae_risk_estimate_pct | 0.3 |
| mae_cap_passed | true |

P2C context: historical follow-up collapse classified `confirmation_prompt_too_strict` (system issue) — retained as context, not current-sample failure mode.

---

## 4. P2D repair status

- `prompt_repair_added=true` (loaded from P2D review)
- Repair must still be proven on a real ETH watch→follow-up pair
- P2F does **not** change prompt / schema / state machine

---

## 5. ETH watch reappearance conditions (current sample)

From P2D-R1 actual ETH rows + P2E negative summary:

| Condition | Current |
|-----------|---------|
| has_eth_watch_or_valid_watch | **false** |
| has_long_buy_bias | **false** |
| confidence_near_reference (≥0.45) | **false** |
| entry_trigger_present | **false** |
| invalidation_present | **false** |
| mae_cap_passed | **false** |
| context_quality_ok | true (some rows) |
| regime_not_unknown | true (some rows) |

All eight required conditions must be true for readiness. Current sample fails.

Negative summary: decisions=5; soft_skip×3/hard_skip×2; conf mostly 0.20–0.35; bias/side NONE×5; skip_intent×5.

---

## 6. Current regression readiness

| Gate | Value |
|------|--------|
| regression_readiness | **false** |
| do_not_run_regression_now | **true** |
| operator_approved_short_regression_may_be_justified | **false** |
| should_run_60m | **false** |
| stage_419_readiness | **false** |
| should_start_419 | **false** |
| next_recommendation | `wait_for_eth_watch_conditions_reappear_no_60m` |

---

## 7. Wait helper robustness status

Cited from P2E fix (`wait_stage4_cloud_dry_run.py`) + static P2F check:

| Check | Result |
|-------|--------|
| import_ok | true |
| completed_needs_finalize exists | true |
| ticks reached ≠ pure timeout | true |
| stage_419_triggered | false |
| trading_state_mutated | false |
| status | **PASS** |

---

## 8. Why Stage 4.19 remains blocked

Actual non-shadow BTC + ETH graduation must both be >0. Shadow / static replay / unilateral BTC graduation cannot open this gate. Current: ETH graduation=0; BTC graduation=0 in this sample chain.

---

## 9. Safety confirmation

Offline-only; llm_called=false; order_sent=false; no exchange private API; no MAE/confidence/RG/routing permanent changes; no Stage 4.19 start; production/btc-auto untouched.

---

## 10. Final verdict

**`STAGE_4_18P2F_PASS`**

Reappearance gate is defined and currently closed (`do_not_run_regression_now=true`).

---

## 11. Next recommendation

Wait for ETH watch conditions to reappear (watch/valid_watch + LONG/SHORT bias + BUY/SELL side + conf≥0.45 + trigger + invalidation + MAE cap + quality/regime). Then operator-approved short runtime regression only — still no auto 60m / no Stage 4.19 / no permanent routing.

---

## Tools / tests

```text
python -m unittest tests.test_stage4_eth_watch_reappearance_gate -v
```

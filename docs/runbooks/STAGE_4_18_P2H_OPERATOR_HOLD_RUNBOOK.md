# Stage 4.18-P2H — Operator Hold Runbook

**Audience:** Private Operator  
**Mode:** docs / CLI usage hardening only  
**Backend state:** `HOLD`  
**Date:** 2026-07-14  

This runbook does **not** authorize runtime soaks, routing edits, prompt/MAE/Risk Governor changes, or Stage 4.19 start.

---

## 1. Current backend state = HOLD

| Field | Value |
|-------|--------|
| `backend_hold_state` | `HOLD` |
| `eth_watch_conditions_reappeared` | `false` |
| `may_justify_short_regression` | `false` |
| `should_run_30m_now` | `false` |
| `should_run_60m` | `false` |
| `should_start_419` | `false` |
| `auto_start` | `false` |
| `next_recommendation` | `continue_hold_no_regression` |

HOLD means: **conditional wait**, not a crash and not an automatic pause until someone clicks start.

---

## 2. Why backend is in HOLD

1. **P2D** added ETH follow-up prompt repair (previous_watch_context + collapse guards).
2. **P2D-R1** runtime was technically OK but produced **no ETH watch** (`PARTIAL_NO_ETH_WATCH`) — repair never exercised.
3. **P2E** diagnosed root cause as `sample_market_no_edge` (not prompt over-conservative).
4. **P2F** closed the reappearance gate: `regression_readiness=false`, `do_not_run_regression_now=true`.
5. **P2G** operator pack confirmed: next short regression **not** allowed now; Stage 4.19 dossier not allowed.
6. **P2H** formalized HOLD + a **passive** future gate checker that never auto-starts runs.

Blind 30m/60m soaks would waste quota without testing the repaired confirmation path.

---

## 3. What condition we are waiting for

ETH must again present a watch / valid_watch–quality candidate with full structure (bias, side, confidence, triggers, MAE/data quality). Until then:

- continue HOLD  
- no 30m  
- no 60m  
- no Stage 4.19  

---

## 4. How to run future gate checker manually

Passive checker only evaluates an existing Stage4 output directory. It does **not** launch a soak.

```bash
python tools/research/stage4_eth_future_regression_gate_checker.py \
  --input-dir /data/stage4_ai_decisions_<future_output> \
  --output-dir /data/stage4_future_gate_check_<date>
```

Related offline pack / gate tools (also non-starting):

- `tools/research/stage4_eth_watch_reappearance_gate.py` (P2F conditions)
- P2G operator readiness summary under the readiness pack output dir

---

## 5. What output means `do_not_run_regression_now`

When the checker (or P2F gate) reports conditions incomplete / reappearance false:

| Implication | Value |
|-------------|--------|
| Continue HOLD | yes |
| Run 30m now | **no** |
| Run 60m | **no** |
| Start Stage 4.19 | **no** |
| Auto-run anything | **no** |

Typical next: `continue_hold_no_regression` or `wait_for_eth_watch_conditions_reappear_no_60m`.

---

## 6. What output means `operator_may_approve_short_regression`

When **all** reappearance conditions are true, the checker may emit:

- `operator_may_approve_short_regression=true` (or equivalent justify flag)

This means **only**:

- An operator **may manually approve** a short regression later.
- It does **not** auto-run 30m.
- It does **not** unlock 60m by default.
- It does **not** start Stage 4.19.
- It does **not** change permanent routing.

Without explicit operator approval, remain in HOLD.

---

## 7. Why 60m is not allowed now

- Longer duration does not create edge when ETH has no watch candidate.
- Policy: never auto-propose 60m while reappearance gate is closed / HOLD stands.
- Even after a justified short regression, 60m remains a separate operator decision.

---

## 8. Why Stage 4.19 remains blocked

Stage 4.19 still requires **actual non-shadow BTC graduation > 0 AND ETH graduation > 0**.

Cannot substitute with:

- shadow outcomes  
- unilateral BTC graduation  
- readiness / HOLD packs alone  
- UI snapshots  

Even when a dossier later becomes allowed, Stage 4.19 must **not** auto-start.

---

## 9. Exact short-regression approval checklist

All of the following must be true before an operator may approve a **short** regression:

- [ ] ETH has watch or valid_watch  
- [ ] `directional_bias != NONE`  
- [ ] `candidate_side != NONE`  
- [ ] `confidence >= 0.45`  
- [ ] entry_trigger present  
- [ ] invalidation present  
- [ ] MAE cap passed  
- [ ] data_quality ok  
- [ ] regime not unknown  

If any item fails:

- continue HOLD  
- no 30m  
- no 60m  
- no Stage 4.19  

If all pass:

- request operator approval for short regression only  
- do not auto-run  
- do not start Stage 4.19  

---

## 10. Exact Stage 4.19 dossier checklist

Before preparing a Stage 4.19 dossier (still not an auto-start):

- [ ] technical PASS on the relevant actual runs  
- [ ] actual non-shadow BTC graduation > 0  
- [ ] actual non-shadow ETH graduation > 0  
- [ ] mock = 0  
- [ ] order = 0  
- [ ] `shadow_used_for_graduation=false`  
- [ ] provider override reset after any experiment  
- [ ] Stage 4.19 not auto-started  

Missing any item → dossier not allowed; Stage 4.19 remains blocked.

---

## 11. Safety invariants

- `orders=false` · `mock=false` · `ARM=false` · `production=false` · `btc_auto=false`  
- no permanent provider routing change  
- no prompt / MAE / confidence / Risk Governor edits under HOLD ops  
- future gate checker: **manual only** / **no auto-run**  
- Private Operator UI is read-only evidence — not a trading console  
- do not commit `/data` raw outputs, jsonl, logs, or secrets  

---

## Quick operator decision tree

```
ETH watch conditions reappeared?
  NO  → HOLD · no 30m · no 60m · no 4.19
  YES → operator_may_approve_short_regression only
          → approved? NO  → stay HOLD
          → approved? YES → short regression only (still no auto 4.19)
                → after run: still need actual BTC+ETH graduation for 4.19 dossier
```

---

## Related artifacts

- P2H report: `docs/reports/STAGE_4_18P2H_BACKEND_HOLD_AND_PASSIVE_GATE_CHECKER_REPORT.md`
- P2G pack: `docs/reports/STAGE_4_18P2G_OPERATOR_READINESS_PACK.md`
- Plan: `docs/stage4_ai_decision_layer_plan.md`
- Checker: `tools/research/stage4_eth_future_regression_gate_checker.py`

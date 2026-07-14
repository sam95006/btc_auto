# Stage 4.18-P2G — Operator Readiness Pack

**Verdict:** `STAGE_4_18P2G_PASS`  
**Mode:** docs / offline gate consolidation / code-only  
**Date:** 2026-07-14  
**Output:** `/data/stage4_18p2g_operator_readiness_pack`

---

## 1. Current status

| Item | Value |
|------|--------|
| BTC | Prior actual graduation evidence exists (P2-R1 / P2A: 3); latest regression graduation=0 |
| ETH | Prompt repair done; runtime not validated; watch reappearance gate not ready |
| Regression | `next_short_regression_allowed_now=false` |
| 30m / 60m | false / false |
| Stage 4.19 | blocked · dossier not allowed |
| Operator action | `wait_for_eth_watch_conditions_reappear` |

Machine-readable summary: `/data/stage4_18p2g_operator_readiness_pack/p2_operator_readiness_summary.json`

---

## 2. BTC status

- Historical Cerebras-first experiment produced **actual** BTC graduation=3 (P2A alignment evidence).
- Latest P2D-R1 regression BTC graduation=**0** (last-tick watch, no follow-up).
- Prior BTC graduation evidence **does not** open Stage 4.19 alone.

---

## 3. ETH status

- P2E root cause: `sample_market_no_edge`
- valid_watch=0 · graduation=0
- Not prompt over-conservative

---

## 4. Prompt repair status

- P2D repair **done** (previous_watch_context + collapse guards)
- Runtime validated: **false** (P2D-R1 had no ETH watch/follow-up sample)

---

## 5. Watch reappearance gate

From P2F:

| Condition | Value |
|-----------|--------|
| has_eth_watch_or_valid_watch | false |
| has_long_buy_bias | false |
| confidence_near_reference | false |
| entry_trigger_present | false |
| invalidation_present | false |
| mae_cap_passed | false |
| context_quality_ok | true |
| regime_not_unknown | true |
| gate ready | **false** |

---

## 6. Regression readiness

- `next_short_regression_allowed_now=false`
- `do_not_run_regression_now=true` (P2F)
- `operator_approved_short_regression_may_be_justified=false`

---

## 7. Why no 30m now

ETH watch conditions have not reappeared. Running another short soak would repeat the no-watch sample without exercising prompt repair. Gate requires watch-like ETH candidate first.

---

## 8. Why no 60m now

Longer duration does not create edge. Policy: never auto-propose 60m while reappearance gate is closed.

---

## 9. Why Stage 4.19 remains blocked

Must have **actual non-shadow BTC graduation > 0 AND ETH graduation > 0** in the graduation evidence chain for dossier prep. Shadow, unilateral BTC, static replay, and readiness-pack alone cannot substitute. Even if dossier becomes allowed later, Stage 4.19 must not auto-start.

---

## 10. Exact condition before next short regression

1. ETH has watch or valid_watch candidate  
2. directional_bias != NONE  
3. candidate_side != NONE  
4. confidence >= 0.45  
5. entry_trigger present  
6. invalidation present  
7. MAE cap passed  
8. data_quality ok  
9. regime not unknown  

Then: operator-approved short runtime regression only.

---

## 11. Exact condition before Stage 4.19 dossier

1. technical PASS  
2. actual non-shadow BTC graduation > 0  
3. actual non-shadow ETH graduation > 0  
4. mock=0  
5. order=0  
6. shadow_used_for_graduation=false  
7. provider override reset  
8. Stage 4.19 not auto-started  

---

## 12. Safety invariants

- orders=false · mock=false · arm=false · production=false · btc_auto=false  
- routing_permanent_change_supported=false  
- no prompt / MAE / confidence / RG edits in this pack  
- wait helper robustness: PASS (from P2E/P2F)

---

## Final verdict

**`STAGE_4_18P2G_PASS`** — operator decision pack consolidated; backend runtime regressions remain paused at gate.

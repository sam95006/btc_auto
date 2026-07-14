# Stage 4.18-P2H-REL — HOLD Release Checkpoint

**Release checkpoint name:** `stage4.18-p2h-hold-checkpoint`  
**Suggested git tag:** `stage4.18-p2h-hold-checkpoint` *(documented only; not auto-created)*  
**Date:** 2026-07-14  
**Backend state:** `HOLD`  
**Mode:** docs / release archival only — **no runtime**

This checkpoint freezes the P2H HOLD posture so operators can revisit a known-safe research state without reopening Stage 4.19 or blind soaks.

---

## 1. Release checkpoint name

| Field | Value |
|-------|--------|
| Name | Stage 4.18-P2H HOLD Release Checkpoint |
| Short id | `P2H-REL` / `stage4.18-p2h-hold-checkpoint` |
| QA basis | Stage 4.18-P2H-QA (`release_checkpoint_ready=true`) |
| UI basis | MVP-11 Report / Runbook Viewer + MVP-10 HOLD hardening |

---

## 2. Backend state = HOLD

| Field | Value |
|-------|--------|
| `backend_hold_state` | `HOLD` |
| `eth_watch_conditions_reappeared` | `false` |
| `should_run_30m_now` | `false` |
| `should_run_60m` | `false` |
| `should_start_419` | `false` |
| `auto_start` | `false` |
| `next_recommendation` | `hold_backend_and_continue_private_operator_ui` |

---

## 3. Latest backend commits

| Stage | Commit | Note |
|-------|--------|------|
| P2H-QA | `412b8a7` | Release health check PASS |
| P2H-OPS | `1c43b02` | Operator HOLD runbook |
| P2H | `94a13e1` | Passiveive future gate checker + HOLD |
| P2G | `346b47c` | Operator readiness pack |

---

## 4. Latest UI commits

| Stage | Commit | Note |
|-------|--------|------|
| MVP-11 | `e695fa8` | Report / Runbook / Gate Checklist viewers |
| MVP-10 | `bcc4937` | Private Operator HOLD hardening |
| MVP-9 | `b1f8c25` | Backend HOLD state display |

---

## 5. Why backend is held

1. ETH follow-up prompt repair (P2D) was never runtime-validated with an ETH watch sample (P2D-R1 = `PARTIAL_NO_ETH_WATCH`).
2. P2E root cause: `sample_market_no_edge` (not prompt over-conservative).
3. P2F reappearance gate closed: `do_not_run_regression_now=true`.
4. P2G/P2H formalized HOLD + passive checker — no blind 30m/60m while waiting for ETH watch conditions.

---

## 6. ETH watch reappearance condition

All must be true before operator may *consider* a short regression:

- ETH has watch or valid_watch  
- `directional_bias != NONE`  
- `candidate_side != NONE`  
- `confidence >= 0.45`  
- entry_trigger present  
- invalidation present  
- MAE cap passed  
- data_quality ok  
- regime not unknown  

Until then: continue HOLD · no 30m · no 60m · no Stage 4.19.

---

## 7. Future gate checker usage

```bash
python tools/research/stage4_eth_future_regression_gate_checker.py \
  --input-dir /data/stage4_ai_decisions_<future_output> \
  --output-dir /data/stage4_future_gate_check_<date>
```

Manual only. Never auto-starts 30m / 60m / Stage 4.19.  
`operator_may_approve_short_regression` still requires explicit operator approval.

Runbook: `docs/runbooks/STAGE_4_18_P2H_OPERATOR_HOLD_RUNBOOK.md`

---

## 8. Why no 30m / 60m

- No ETH watch/valid_watch candidate to exercise repair path.
- Longer duration does not create edge while gate is closed.
- Policy: never auto-propose 60m under HOLD.

---

## 9. Why Stage 4.19 remains blocked

Requires **actual non-shadow BTC graduation > 0 AND ETH graduation > 0**.

Cannot substitute with shadow, unilateral BTC, readiness packs, or UI snapshots. Even when a dossier later becomes allowed, Stage 4.19 must **not** auto-start.

---

## 10. Safety invariants

- orders=false · mock=false · ARM=false · production=false · btc_auto=false  
- no permanent provider routing change  
- no prompt / MAE / confidence / Risk Governor edits under HOLD ops  
- Private Operator UI read-only · no trade/order/ARM/4.19-start routes  
- no billing / customer accounts / API key collection  
- do not commit `/data` raw outputs, jsonl, logs, or secrets  

QA report: `docs/reports/STAGE_4_18P2H_QA_RELEASE_HEALTH_CHECK_REPORT.md`

---

## 11. What must happen before next short regression

1. Future gate checker (or equivalent) shows ETH reappearance conditions true.  
2. Operator explicitly approves short regression.  
3. Still: no auto-run · no 60m by default · no Stage 4.19.

---

## 12. What must happen before Stage 4.19 dossier

1. technical PASS on relevant actual runs  
2. actual non-shadow BTC graduation > 0  
3. actual non-shadow ETH graduation > 0  
4. mock=0 · order=0  
5. `shadow_used_for_graduation=false`  
6. provider override reset  
7. Stage 4.19 not auto-started  

---

## Suggested git tag

```
stage4.18-p2h-hold-checkpoint
```

Not created automatically in this release step (tag policy left to operator). Use after confirming working tree intent.

---

## Final posture

**Backend HOLD remains active.**  
**Next runtime only after ETH watch conditions reappear.**  
Continue Private Operator UI hardening under read-only constraints.

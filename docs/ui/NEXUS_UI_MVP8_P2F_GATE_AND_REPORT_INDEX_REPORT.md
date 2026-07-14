# NEXUS / EATI UI MVP-8 — P2F Gate Display + Report Index

**Verdict:** PASS  
**Mode:** Private Operator read-only sanitized snapshot  
**Date:** 2026-07-14  
**Audience:** Internal operators / researchers only  
**Public SaaS:** Future architecture only — not implemented

---

## 1. MVP-7 recap

MVP-7 showed P2E `sample_market_no_edge` with RegressionReadinessCard. No 60m. Stage 4.19 blocked.

---

## 2. P2F snapshot update

Added `frontend/src/demo/snapshots/p2fPrivateOperatorSnapshot.ts`:

- stage `4.18-P2F` / verdict `STAGE_4_18P2F_PASS`
- regression_readiness=false
- do_not_run_regression_now=true
- ETH watch condition checklist
- wait_helper_robustness_status=PASS
- no 60m · Stage 4.19 blocked
- next=`wait_for_eth_watch_conditions_reappear_no_60m`

Adapter prefers P2F over P2E/….

---

## 3. WatchReappearanceGateCard

Checklist UI for ETH watch conditions + readiness=false + do not run now + wait helper PASS.

---

## 4. ReportIndexCard

Lists P2D / P2D-R1 / P2E / P2F with stage, verdict, one-line conclusion, report path, next action.

---

## 5. Pages updated

| Page | Update |
|------|--------|
| `/overview` | P2F stage/verdict · readiness=false · WatchReappearanceGateCard |
| `/risk-evidence` | watch gate checklist · no 30m / no 60m / no 4.19 |
| `/paper-lab` | next condition before regression |
| `/evidence` | ReportIndexCard |
| `/provider-shadow` | no permanent routing · p2fSummary |

---

## 6. Why no 30m / 60m

Gate closed — ETH watch conditions incomplete. UI mirrors backend: do not run now.

---

## 7. Stage 4.19 blocked display

Shown on overview / risk / gate card. No start button.

---

## 8. Future public SaaS still not implemented

No billing / accounts / API key collection / copy trading / managed accounts.

---

## 9. Safety checks

```text
python tools/research/check_nexus_ui_mvp8_safety.py
```

---

## 10. Trading backend untouched

UI commit excludes trading logic, routing, RG, ARM, production, btc-auto.

---

## 11. Next UI step

Later MVP may surface P2G operator pack snapshot (still read-only). Stop at P2F gate + report index for now.

# NEXUS / EATI UI MVP-7 — P2E Snapshot + Regression Readiness

**Verdict:** PASS  
**Mode:** Private Operator read-only sanitized snapshot  
**Date:** 2026-07-14  
**Audience:** Internal operators / researchers only  
**Public SaaS:** Future architecture only — not implemented

---

## 1. MVP-6 recap

MVP-6 showed P2D-R1 `PARTIAL_NO_ETH_WATCH` with RuntimeRegressionStatusCard (technical PASS, repair not validated due sample). Stage 4.19 blocked. No trading surfaces.

---

## 2. P2E snapshot update

Added `frontend/src/demo/snapshots/p2ePrivateOperatorSnapshot.ts`:

- latest stage `4.18-P2E` / verdict `STAGE_4_18P2E_PASS`
- ETH no_watch_root_cause=`sample_market_no_edge`
- ETH decisions=5 · soft_skip×3/hard_skip×2 · conf buckets · NONE×5 bias/side
- watch/graduation=0/0
- prompt_repair_over_conservative=false · needs_prompt_adjustment=false
- should_run_60m=false · wait_helper_fixed=true
- Stage 4.19 blocked
- regression readiness=false · next gate P2F

Adapter prefers P2E over P2D-R1/P2D/….

---

## 3. RegressionReadinessCard

Shows readiness=false, reason=ETH watch conditions not present, no 60m, wait for ETH watch/valid_watch, prompt not over-conservative, next gate=P2F.

---

## 4. Pages updated

| Page | Update |
|------|--------|
| `/overview` | P2E stage/verdict · sample_market_no_edge · RegressionReadinessCard |
| `/risk-evidence` | no 60m · Stage 4.19 blocked · wait helper fixed |
| `/paper-lab` | readiness=false · ETH watch conditions absent |
| `/evidence` | P2D repair → P2D-R1 no ETH watch → P2E sample_market_no_edge |
| `/provider-shadow` | no permanent routing · p2eSummary |

---

## 5. Why no 60m

UI mirrors gate: sample no-edge does not justify longer soak. Wait for ETH watch conditions.

---

## 6. Stage 4.19 blocked display

Shown on overview / risk / paper-lab / readiness card. No start button.

---

## 7. Future public SaaS still not implemented

Membership remains Future only / no billing / no customer accounts / no API key collection.

---

## 8. Safety checks

```text
python tools/research/check_nexus_ui_mvp7_safety.py
```

---

## 9. Trading backend untouched

UI commit excludes trading logic, routing, RG, ARM, production, btc-auto.

---

## 10. Next UI step

After backend P2F lands in operator awareness, later MVP may mirror P2F gate summary (still read-only). Stop at P2E/P2F readiness display for now.

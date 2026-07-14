# NEXUS / EATI UI MVP-9 — Backend Hold State + Future Gate Checker Display

**Verdict:** PASS  
**Mode:** Private Operator read-only sanitized snapshot  
**Date:** 2026-07-14  
**Audience:** Internal operators / researchers only  
**Public SaaS:** Future architecture only — not implemented

---

## 1. MVP-8 recap

MVP-8 showed P2F watch reappearance gate + Report Index. Ready for HOLD-state framing.

---

## 2. P2G / P2H snapshot

Added `frontend/src/demo/snapshots/p2gPrivateOperatorSnapshot.ts`:

- Current backend state: **HOLD**
- Reason: ETH watch conditions not present
- Next allowed action: wait for ETH watch/valid_watch reappearance
- 30m now / 60m / Stage 4.19 / permanent routing: all false / blocked
- Future checker: manual only / no auto-run
- Report index includes P2G + P2H

---

## 3. BackendHoldStateCard

Shows HOLD posture clearly — not a failure, conditional wait.

---

## 4. FutureRegressionGateCard

Shows passive/manual checker; never implies auto-run of 30m/60m/4.19.

---

## 5. Pages updated

overview / risk-evidence / paper-lab / evidence / provider-shadow

---

## 6. Why this is not “stuck”

UI language: wait-for-condition. When ETH watch conditions reappear, operator may approve a short regression — not auto-started.

---

## 7. Stage 4.19 blocked display

Retained across pages. No start button.

---

## 8. Future public SaaS still not implemented

No billing / accounts / API keys / copy trading / managed accounts.

---

## 9. Safety checks

```text
python tools/research/check_nexus_ui_mvp9_safety.py
```

---

## 10. Trading backend untouched

UI commit excludes trading logic, routing, RG, ARM, production, btc-auto.

---

## 11. Next UI step

Remain on HOLD display until an operator-fed future output flips the passive checker recommendation.

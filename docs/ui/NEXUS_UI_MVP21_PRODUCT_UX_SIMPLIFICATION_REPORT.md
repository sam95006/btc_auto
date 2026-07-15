# NEXUS UI MVP-21 — Product UX Simplification + Feature Completion Blueprint

**Date:** 2026-07-15  
**Branch:** `stage3-demo-learning`  
**Prior sign-off:** UI-LIVE-SIGNOFF-1 → **NEED_POLISH_FIXES**  
**Backend:** HOLD · UI read-only · Stage 4.19 blocked  

---

## 1. MVP-20 live signoff result

`NEED_POLISH_FIXES` — Live MVP-20 passed deploy checks, but product clarity was not yet “3-second understandable” vs DataHunterX-class market intelligence UX.

## 2. Why MVP-21

Not a redesign for novelty. Goal: simplify language and path so a non-engineer can see:

1. Market / HOLD state  
2. Which symbols matter  
3. Why regression cannot run  
4. Why Stage 4.19 is blocked  
5. Where Evidence / Gate / Risk live  
6. Next action = **Wait**, never trade  

## 3. Simplification strategy

- First screen = headline + four decision cards  
- “What should I look at first?” guided entry  
- Candidate / Signal / Decision Radar use meaning-first copy  
- Evidence Center → four zones  
- Feature Completeness Map (Future = NOT IMPLEMENTED)  
- Risk “Why this is safe”  
- Provider “What this means”  
- Mobile shows HOLD / Wait / ETH / 4.19 first  

## 4. Overview changes

- `HoldDecisionStrip` + HOLD headline  
- Four cards: Backend · Market Readiness · Regression Gate · Next Action  
- `LookFirstSection` (ETH Gate · Stage 4.19 · Evidence)  
- Feature map below boards  
- MCC retained desktop; hidden on narrow mobile  

## 5. Candidate / Signal / Decision Radar

- Candidate: status / meaning / next (table desktop, cards mobile)  
- Signal: severity + meaning + next action  
- AnomalyRadar retitled **Decision Radar** with what / why / next  

## 6. Evidence Center

`EvidenceZoneTabs`: Start Here · Gate Reports · Evidence & Regression · Release / Runbook. MVP-16 search/filter kept on Start Here.

## 7. Feature Completeness Map

Completed vs waiting vs future-only stubs (billing / accounts / API keys / live trading = NOT IMPLEMENTED).

## 8. Risk Center why-safe

`WhySafeSection`: no orders / live trading / API keys / ARM / production / Stage 4.19 / read-only nav.

## 9. Provider explanation layer

Plain English for Groq vs Cerebras history, Cerebras-first experiment, permanent routing=false, shadow ≠ graduation.

## 10. Mobile simplification

Narrow layout prioritizes HOLD strip + Look First; MCC / secondary checklists collapse; candidate cards instead of wide tables.

## 11. Safety checks

`python tools/research/check_nexus_ui_mvp21_safety.py`

## 12. Build / typecheck

`cd frontend && npm run typecheck && npm run build`  
`python tools/deploy/sync_operator_ui_into_zeabur_stage3.py`

## 13. Backend HOLD unchanged

No 30m / 60m / Stage 4.19 / runtime.

## 14. Trading backend untouched

No provider routing / RG / prompt / MAE / confidence changes.

## 15. Future public SaaS

Still NOT IMPLEMENTED.

## 16. Next recommendation

After Zeabur redeploy: operator re-run visual sign-off. Prefer **APPROVE_MVP20_VISUAL / MVP-21 clarity** before more feature volume. No trading work while HOLD.

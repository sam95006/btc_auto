# NEXUS UI MVP-20 — Live Market Intelligence Polish

**Date:** 2026-07-15  
**Branch:** `stage3-demo-learning`  
**Prior live gate:** UI-DEPLOY-2 (`8502fba`) PASS  
**Scope:** Frontend visual polish only · Backend HOLD  

---

## 1. UI-DEPLOY-2 recap

Zeabur live already served Market Intelligence SPA via `nexus-web` (`static/operator_ui`). Marker `NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60` verified. `/nexus` kept legacy Stage 3. Backend remained HOLD.

## 2. Live screenshot issues

1. Top bar horizontal overflow / too many chips  
2. Market Command felt raw / debug  
3. AI Commander duplicated (main + right rail)  
4. Fleet cards narrow with awkward wraps  
5. HOLD / BLOCKED / DEMO DATA badge noise  
6. Sidebar engineering-ish  
7. Mixed CN/EN without strategy  
8. Candidate / Signal / Anomaly not dashboard-dense enough  

## 3. Top bar polish

- Primary chips only: Backend HOLD · Stage 4.19 BLOCKED · Mode READ ONLY · UI Build MVP-19 · live  
- Secondary row / tooltip: P2H · paused · no auto-run · disclaimer · DEMO DATA  
- Full marker moved to footer  
- No horizontal scrollbar (`overflow-x: hidden`, wrap layout)  

## 4. AI Commander de-dup

- Desktop: full `AICopilotPanel` in **right rail only**  
- Main: `AIPromptChipStrip` (compact static chips)  
- Removed embedded `AICopilotPanel` from Market Command Center  
- Mobile: bottom dock compact panel  
- Still static prompts · no live AI API · no trade actions  

## 5. Fleet card polish

Copy cleaned (no raw “NONE (latest regen)”):

| Symbol | Status | AI stance | Intent | Graduation | Next |
|--------|--------|-----------|--------|------------|------|
| BTC | HOLD | Prior evidence only | None | prior yes / latest 0 | View Evidence |
| ETH | WAIT | Watch condition not reappeared | None | 0 | View Gate |
| SOL / PEPE | HOLD | Skip / waiting | Skip | n/a | Ask AI / Open Risk Card |

Fleets page cards share the same trading-summary layout.

## 6. Badge noise reduction

Priority:

- High: HOLD · Stage 4.19 BLOCKED · READ ONLY (top bar / section heads)  
- Medium: DEMO DATA / SANITIZED / PASS / WAIT (sparingly)  
- Low: NOT INVESTMENT ADVICE · static prompts → footer / secondary  

Removed repeated DEMO DATA from Overview header / MCC / boards.

## 7. Layout / responsive fixes

- Fleet grid: 4 columns desktop · 2 tablet · 1 mobile  
- Fixed AI rail width · `minmax(0,1fr)` main column to stop overflow  
- Consistent card padding · Candidate/Signal/Anomaly in Overview lower stack  
- Ghost action chips for drilldowns  

## 8. Sidebar polish

Groups:

- Operator Console: Overview · Market Command · Evidence · Risk  
- Research: Validation Lab · Provider Intelligence · Reports · Runbooks  
- Future: Academy · Membership · Public SaaS  

## 9. Language strategy

- Main UI labels: English  
- Status tokens: HOLD / BLOCKED / WAIT / READ ONLY / Evidence / Risk / Provider  
- AI prompt chip labels may stay Chinese (問目前頁 / 找風險 / 找機會 / 今日簡報)  
- Per-block consistency preferred over mixed lines  

## 10. Safety checks

`python tools/research/check_nexus_ui_mvp20_safety.py`

Asserts: no Run 30m / 60m / Start Stage 4.19 · marker present · no quick order / trade routes / billing / accounts / API key collection · AI static · READ ONLY / NOT INVESTMENT ADVICE present.

## 11. Build / typecheck

`cd frontend && npm run typecheck && npm run build`  
`python tools/deploy/sync_operator_ui_into_zeabur_stage3.py`  
Marker grep on `frontend/dist`, `static/operator_ui`, deploy package.

## 12. Backend HOLD unchanged

No 30m · no 60m · Stage 4.19 not started · no new runtime.

## 13. Trading backend untouched

No provider routing / Risk Governor / prompt / MAE / confidence floor changes.

## 14. Future public SaaS

Still not implemented · Membership / Academy remain stubs.

## 15. Next UI step

After Zeabur redeploy of this polish commit: hard-refresh and confirm density. Candidate next: MVP-21 light theme tokens or Evidence UX — **not** trading controls.

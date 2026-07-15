# NEXUS UI MVP-22 — Simplified Market Dashboard

**Date:** 2026-07-15  
**Branch:** `stage3-demo-learning`  
**Prior:** MVP-21 (`3d19cc0`) still NEED_POLISH_FIXES (too much engineer prose)  
**Backend:** HOLD · UI read-only · Stage 4.19 blocked  

---

## 1. MVP-21 recap

MVP-21 added “3-second” copy (HOLD headline, look-first, feature map). Clarity improved, but the home page still read like a system manual.

## 2. Why MVP-21 still felt too complex

- Too much HOLD / Gate / Evidence prose on first paint  
- Right rail AI stole horizontal space  
- Cards felt like documents, not a market board  
- Users had to read before scanning  

## 3. Comparison target

DataHunterX-style simplicity (not a clone):

- Left: functions  
- Top: market prices + status  
- Center: recommendation boards + gauge  
- Below: alerts  
- Corner: AI assistant  

NEXUS difference remains Evidence / Gate / Risk / HOLD safety — not order placement.

## 4. Simplification strategy

- Subtract homepage text  
- MarketTopTicker replaces chip-heavy top bar  
- Remove permanent AI rail → FloatingAIAssistant  
- Long/Short boards + readiness gauge  
- Compact safety strip only  
- Gate checklists behind “Show gate details”  

## 5. Homepage changes

`SimplifiedMarketDashboard` is Overview first paint. One-liner only: read-only research mode; no regression.

## 6. Recommendation boards

Long Watchlist (BTC/ETH/SOL/PEPE demo). Short Watchlist empty with monitoring note. Actions: View Evidence / View Gate only.

## 7. Market readiness gauge

`NEXUS Market Readiness Score` demo 48.1 · Neutral / Waiting · HOLD / ETH Gate / 4.19 lines.

## 8. Decision alerts

Zones: Confirmed Breakout · Waiting for Breakout · Gate Warning · Provider Divergence.

## 9. AI assistant simplification

Floating FAB + small panel. Five static English prompts. No API.

## 10. Safety boundaries

No Buy/Sell/Execute/Quick Order/Run 30m/60m/Start 4.19/trade routes/billing/accounts/API keys. Evidence filters + Risk why-safe + Provider explain retained on their pages.

## 11. Build / typecheck

- `check_nexus_ui_mvp22_safety.py` → **PASS** (109 files)
- `npm run typecheck` → **PASS**
- `npm run build` → **PASS** (`index-DtVt2AEO.js` / `index-BJsuFuLr.css`)
- `sync_operator_ui_into_zeabur_stage3.py` → **PASS** (`static/operator_ui` + deploy package; marker retained)

## 12–14. HOLD / trading / SaaS

Backend HOLD unchanged. Trading backend untouched. Public SaaS still NOT IMPLEMENTED.

## 15. Next recommendation

Redeploy → visual sign-off. Prefer APPROVE if first paint answers: prices, which coin to watch (ETH), long/short boards, readiness, alerts — without reading Gate essays.

## 16. First-paint polish (same MVP-22)

After `dd0ac05`, live still felt status-heavy. Polish pass:

- Single status line (not pill wall)
- Ticker prices larger; HOLD/READ ONLY plain text; 4.19 mini badge
- Focus line: ETH WAIT
- Removed board footnotes / secondary link row
- Gate checklists collapsed under `<details>`
- Mobile: gauge before watchlists

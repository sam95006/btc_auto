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
- `npm run build` → **PASS** (`index-DlS-3yea.js` / `index-DXC1RwAR.css` after polish)
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

## 17. Redeploy + live visual sign-off (2026-07-16)

- Source of truth: `9aa4ffc` on `stage3-demo-learning` (includes `dd0ac05`)
- Zeabur deployment: `commitSHA=9aa4ffc…` · `status=RUNNING` · ref `stage3-demo-learning`
- Live asset: `/assets/index-DlS-3yea.js` (+ `index-DXC1RwAR.css`)
- Service restart refreshed containers; `/health` ok; `/api/nexus/ui-build` ok; root=`operator_ui`
- Visual markers PASS: ticker → single Status → Focus ETH → Long/Short + Gauge → Alerts
- Verdict: **PASS — MVP-22 9aa4ffc LIVE AND VISUALLY SIGNED OFF**

## 18. MVP-22A — Live Market Data Truth Layer

**Audit root cause:** Homepage BTC/ETH/SOL prices were static fixtures in `frontend/src/demo/marketDashboard.ts` (hardcoded 64,943 / 1,882 / 148.2). No REST, no WebSocket, no Mainnet feed. Current price and signal reference were the same demo numbers.

**Fix:**
- Display environment: Bybit **Mainnet public** linear lastPrice (REST bootstrap via `/api/market/tickers` proxy + browser WS `wss://stream.bybit.com/v5/public/linear`)
- Research/execution environment unchanged: HOLD / read-only / no Stage 4.19 / no private API
- Types: `LiveMarketPrice` vs `SignalReference` separated
- Freshness: LIVE / DELAYED / STALE / RECONNECTING / REST_FALLBACK / DISCONNECTED
- Cache: `/api/market/*` → `no-store`; no service worker; no localStorage market source
- Version: public name **NEXUS — Live Market Intelligence**; ui-build **MVP-22A** (`NEXUS_UI_MVP22A_LIVE_MARKET_DATA`) with legacy marker retained for sync compatibility

**Checks:** `check_nexus_ui_mvp22a_safety.py` · `verify_mvp22a_live_market_truth.py` · typecheck · build · static sync

**Redeploy / Live sign-off (2026-07-16):**
- Live Source of Truth: `3c84f42` (includes MVP-22A `a702e66` + freshness age fix)
- Live asset: `index-C8nn6s0J.js` (supersedes `index-JoznSR-n.js`)
- `/api/market/tickers` vs official Bybit Mainnet: **3-round PASS** (≤ max(2 ticks, 5 bps)); `Cache-Control: no-store`
- Browser Playwright on `/overview`: WS `wss://stream.bybit.com/v5/public/linear` connected; BTC/ETH/SOL lastPrice updates; no hardcoded 64,943/1,882/148.2 as ticker; Current vs Signal separated; mobile gauge `order:-1`; no overflow; FAB only; gate `<details>` collapsed
- Freshness: LIVE/DELAYED **browser live verified**; STALE/RECONNECTING/REST_FALLBACK/DISCONNECTED **automated state transition verified**; recovery to LIVE **browser live verified**
## 19. MVP-22B — Derivatives Market Context Layer

**Audit:** Bybit Mainnet linear tickers already include `openInterest`, `openInterestValue`, `fundingRate`, `nextFundingTime`, `volume24h`, `turnover24h`. Gap was that REST proxy / WS parser / TS types dropped them; UI had no presentation.

**Fix (no new private API):**
- Preserve derivative fields through `/api/market/tickers` + WS ticker merge (never wipe missing delta fields)
- In-memory OI 1m/5m/15m rolling samples (`Collecting` until window ready)
- Funding % conversion via single `FUNDING_CONFIG` (decimal → percent)
- Compact `Market Context` under Focus ETH (OI · Funding · Volume)
- Evidence labels supportive/neutral/conflicting/unavailable — **not** in recommendation scoring
- Units: OI coin vs USDT value; Volume coin vs Turnover USDT separated

**Checks:** `check_nexus_ui_mvp22b_safety.py` · `verify_mvp22b_derivatives_context.py` · typecheck · build · static sync

**Redeploy / Live sign-off (2026-07-16):** see §20.

## 20. MVP-22B Redeploy + Live Derivatives Context Sign-off (2026-07-16)

**Source of Truth drift (pre-redeploy):** Repo `56066e8` / `index-YrejgD0N.js` vs prior Live `3c84f42` / `index-C8nn6s0J.js`.

**Live code commit:** `c1f46e0` (`NEXUS_UI_MVP22B_DERIVATIVES_CONTEXT`; MVP-22A marker retained)  
**Live asset:** `index-BHA1syR8.js` (supersedes `index-YrejgD0N.js`; old `index-C8nn6s0J.js` absent)  
**Zeabur:** GitHub remote `stage3-demo-learning` → RUNNING `c1f46e0` (not dirty local tree)  
**Sign-off docs commit:** `ded0646` (+ follow-up if needed)

**Verified on Live:**
- `/api/market/tickers` vs official Bybit Mainnet linear: **3-round PASS** (OI / OI value / funding / nextFundingTime / volume24h / turnover24h); `Cache-Control: no-store`; `private_api=false`
- Browser Playwright `/overview`: WS `wss://stream.bybit.com/v5/public/linear`; Market Context OI·Funding·Volume; funding `0.0001` → `+0.0100%`; scoring disclaimer; Collecting on fresh load; no overflow; FAB only; mobile gauge `order:-1`; 0 page errors
- OI rolling: initial 1m/5m/15m **Collecting**; after ~75s **1m → numeric** while 5m/15m remain Collecting — **no fake history**
- `oi_5m` / `oi_15m` live windows: **duration_pending** (automated Collecting logic PASS)
- Recommendation algorithm unchanged; context not in scoring

**Verdict:** `PASS — MVP-22B DERIVATIVES CONTEXT DEPLOYED AND VERIFIED`  
**remaining_issues:** `oi_15m live duration pending` (and `oi_5m` when soak &lt; 5m)

**Safety:** mvp22 / mvp22a / mvp22b PASS · typecheck PASS · build PASS · operator UI static sync PASS · forbidden trade/ARM/billing/4.19 paths absent

## 21. MVP-22C — Read-only Market Anomaly Radar (code)

**Scope:** detect + rank + explain market anomalies from existing Mainnet public feed. **No** recommendation scoring change · **no** redeploy this round.

**Data:** reuses live ticker fields + in-memory price/OI/volume rolling buffers (`Collecting` until window ready). No DB · no private API.

**Anomaly types:** PRICE_ACCELERATION · OI_SURGE/DROP · PRICE_OI_DIVERGENCE · FUNDING_EXTREME · VOLUME_EXPANSION · SPREAD_WIDENING · MULTI_FACTOR_ANOMALY.

**Lifecycle:** dedup by symbol+type · NEW→ACTIVE→COOLING→RESOLVED · cooldown · no per-tick spam.

**UI:** `/anomalies` full list + filters; homepage Decision Alerts shows up to 3 **Market anomaly** summaries (separate from research alerts).

**Thresholds:** centralized `ANOMALY_CONFIG` · UI: *Research threshold — not a trade trigger* · score ranks attention only.

**Version semantics:**
- MVP-22C initial implementation: `0e6c985` · asset `index-CpBPYA6d.js`
- MVP-22C live deployment fix: `fac292d` · asset `index-DI2woa9V.js`
- **Current Live Source of Truth:** `fac292d2acaedbb64378a672ce75560f726c1612`

**Live deploy (fac292d):** `/anomalies` SPA fallback · turnover semantics (`Turnover expansion` label) · static sync · marker `NEXUS_UI_MVP22C_MARKET_ANOMALY_RADAR`.

**MVP-22B duration follow-up:** fresh Live page load → all OI windows **Collecting** (in-memory reset expected). **5m/15m** remain **duration_pending** until uninterrupted soak — no fabricated window values.

**Verdict (Live):** `PASS — MVP-22C MARKET ANOMALY RADAR DEPLOYED AND VERIFIED`  
**remaining_issues:** `oi_5m` / `oi_15m` live duration pending (Collecting on fresh load; expected)

## 22. POST-MVP-22C repo reconciliation + SPA cache resilience (code)

**Repo SoT (pre-Live):** `a1fc958` · expected asset `index-DuAW9484.js`.

**Repo fixes:**
- Reconciled local MVP-22C semantic regressions (`Turnover expansion`, `/anomalies` SPA, MVP-22C markers).
- HTML shell: `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`.
- Hashed assets: `public, max-age=31536000, immutable`.
- Static sync retains previous hashed JS/CSS generation (max 2) instead of deleting all old assets.
- Asset-load recovery + fallback error UI (no infinite reload).

**Live root-cause fix (follow-up):** recovery inside the hashed JS bundle cannot run when that bundle 404s. Moved primary one-shot reload + error UI into **inline `frontend/index.html` bootstrap** (`00a0075` · `index-klwOjLAR.js`).

## 23. SPA Cache Resilience Redeploy + Live Sign-off (2026-07-17)

**Live Source of Truth:** `00a007511df08e5a437313e683976b746c589ca3`  
**Live asset:** `index-klwOjLAR.js` (+ CSS `index-D_BggeCB.css`)  
**Retained previous:** `index-DuAW9484.js` (200) · older `index-DI2woa9V.js` pruned (404; 2-generation retention)

**HTTP:** HTML `/` `/overview` `/anomalies` → `no-store, no-cache, must-revalidate, max-age=0` + Pragma/Expires · hashed JS/CSS → `public, max-age=31536000, immutable`

**Playwright Live:**
- Current HTML + current asset: mount PASS
- Stale HTML + retained previous asset: mount PASS
- Missing asset → one-shot reload → current HTML: PASS
- Persistent missing → fallback error UI, guard=`failed`, no empty root, no loop: PASS
- Desktop/tablet/mobile overview+anomalies: PASS · no horizontal overflow

**Regression:** MVP-22～22C feed/anomaly/turnover PASS · market tickers public-only · safety PASS

**Verdict:** `PASS — SPA CACHE RESILIENCE DEPLOYED AND LIVE VERIFIED`  
**remaining_issues:** `oi_5m` / `oi_15m` live duration pending (unchanged; not blocking)

## 24. MVP-22D — Anomaly Outcome Tracking & Research Validation (code)

**Scope:** read-only forward outcome tracking for detected anomalies (5m / 15m / 30m / 60m). **No** Recommendation / confidence / Gauge / trading changes · **no** redeploy this round.

**Model:** one `AnomalyOutcome` per `anomalyId` · windows PENDING→COMPLETE|MISSED|STALE · timestamp tolerance 15s · MFE/MAE + forward return · bounded in-memory store.

**UI:** `/anomaly-outcomes` research page · Anomaly Radar link “View outcome tracking” · aggregations labeled *Observed research outcomes* / *Insufficient sample*.

**Safety:** mvp22～22d PASS · SPA cache resilience verify PASS · synthetic outcome state-machine PASS.

**Verdict (code):** `PASS — MVP-22D ANOMALY OUTCOME RESEARCH VERIFIED IN CODE`  
**remaining_issues:** redeploy and live outcome-duration verification pending · OI 5m/15m duration pending

## 25. MVP-22D Redeploy + Live Outcome Research Sign-off (2026-07-17)

**Live Source of Truth:** `4e62f2e78d840aa33e2a6603bd9ca2ca1094fbc6`
**Live asset:** `index-BLh5ikEO.js` (+ CSS `index-BMXNpqmh.css`)
**Core feature commit:** `6322582` · **Live polish:** session banner + overflow + retain `index-klwOjLAR.js`

**Verified Live:**
- `/anomaly-outcomes` mounts · Session-based research observation banner visible
- HTML no-store · hashed assets immutable · previous `klwOjLAR` + `BOIvB-zY` retained (200)
- MVP-22~22C regression PASS · market tickers public-only
- Synthetic outcome state-machine PASS
- Desktop/mobile: page horizontal overflow absent; table internal scroll on <=768px
- No natural Live anomaly during sign-off -> real 5m/15m/30m/60m duration **pending** (not fabricated)

**Verdict:** `PASS — MVP-22D ANOMALY OUTCOME RESEARCH DEPLOYED AND VERIFIED`
**remaining_issues:** real outcome window duration pending (no_live_event_available) · oi_5m/oi_15m duration pending

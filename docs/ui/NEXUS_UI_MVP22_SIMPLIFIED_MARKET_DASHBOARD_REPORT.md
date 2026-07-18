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

## 26. NEXUS Product Transformation Phase 1 (code — 2026-07-17)

**Closed Live baseline (do not confuse with this code commit):**
- Current Live code SoT: `4e62f2e78d840aa33e2a6603bd9ca2ca1094fbc6` · asset `index-BLh5ikEO.js`
- Sign-off docs head: `d371c8d` (docs only, not Live code)
- Core MVP-22D: `6322582`

**Product shift:** fixed BTC/ETH/SOL research dashboard → decision-first market opportunity product.

**Architecture:**
```
Bybit Public Market Data → NEXUS Read-only Market Scanner (server)
→ Bounded Rolling State → Candidate Engine → Ranking Snapshot
→ Public Read-only API → UI
```

**Delivered in code (no Redeploy this round):**
- Dynamic Market Universe (Bybit Mainnet linear USDT, turnover/OI/spread filters, limit 80)
- Centralized server scanner + rolling history + stale/overlap guards
- Long/Short Candidate Engine (Opportunity / Confirmation / Risk 0–100, lifecycle stages)
- Ranking + candidate event stream (dedup/cooldown/bounded)
- APIs: `/api/market/scanner/{status,universe,candidates,symbol,events,charts}`
- New `/overview` (Market Pulse, Top Long/Short, breadth + turnover charts, events)
- `/scanner` filters/sort · `/market/:symbol` detail + sparkline
- Preserved: anomalies, outcomes, evidence, freshness, Signal Reference, SPA cache resilience, AI FAB
- Research/trading isolation: scores ≠ Recommendation/confidence/sizing/leverage

**Smoke:** live universe ~742 tickers → 80 eligible · scanner refresh produces real Long/Short candidates (`researchOnly=true`)

**Build asset (repo, not Live at time of code commit):** `index-CCe0pwCY.js`

**Verdict (code):** `PASS — NEXUS PRODUCT TRANSFORMATION PHASE 1 VERIFIED IN CODE`

**remaining_issues (at code commit):**
- redeploy and live scanner/product sign-off pending
- real anomaly outcome duration pending
- oi_5m/oi_15m duration pending

## 27. Phase 1 Redeploy + Live Sign-off (2026-07-17)

**Live Source of Truth:** `df0a519a106d5aa8e6cda45beca5dfa6cc82a525`  
**Live asset:** `index-9zfXgtWz.js`  
**Prior Phase 1 code:** `a7b5b86` · Live polish path: `e9836ed` (register scanner on `run.py`) → `4e245c8` (no collecting Top-5 fill) → `df0a519` (overview declutter)

**Root cause found during Live:** Zeabur serves monorepo `gunicorn app:app` / `run.py` (nexus-web), not `stage3_readonly_web_app.py`. Scanner routes were initially only on the deploy-package entrypoint → `/api/market/scanner/*` 404 until `e9836ed`.

**Live verified:**
- Universe: ~742 tickers → ~97 eligible → 80 limit; exclusions include `LOW_LIQUIDITY` / `UNSUPPORTED`
- Scanner: ~20.6s average cycle · overlap blocked · `historyCapacity=72` · gunicorn workers default 1
- After ~5m window: real Long/Short with non-null `priceChange5mPct` / `oiChange5mPct`; collecting symbols do not fill Top 5
- Cadence copy: 「候選約每 20 秒重新掃描」
- Charts: Market Breadth sum=80 · Turnover Top 10 · Price/OI quadrant points only when 5m ready
- Playwright: `/overview` `/scanner` `/market/BTCUSDT` `/anomalies` `/anomaly-outcomes` mount · 0 page errors · no horizontal overflow at 1440/1280/1024/768/430/390/375/360
- Three-second cues PASS (Pulse · Long/Short · cadence · research/no-trading · no Buy/Sell CTA)
- SPA: HTML `no-store` · hashed assets immutable · previous `C-Rjc6Iz` / `BLh5ikEO` retained 200
- Toast observed (rank up / overextended) · sound/notification default OFF
- Recommendation/trading isolation unchanged · private_api=false

**Verdict:** `PASS — NEXUS PRODUCT TRANSFORMATION PHASE 1 DEPLOYED AND LIVE VERIFIED`

**remaining_issues:**
- real anomaly outcome 5m/15m/30m/60m duration pending
- MVP-22B oi_5m/oi_15m duration pending (BTC/ETH/SOL browser feed)
- full-market WebSocket adapter deferred
- chrome still shows compact Backend HOLD / 4.19 chip in top bar (not overview body); deeper chrome declutter is Phase 2 polish

## 28. Product Transformation Phase 2 — Decision Experience (code, no Redeploy)

**Repo base:** `8999298855bc94cd01c78b349f8db2b1e7448e0d` (Phase 1 sign-off docs head on `stage3-demo-learning`)  
**Current Live SoT (unchanged this round — no Redeploy):** `df0a519a106d5aa8e6cda45beca5dfa6cc82a525` · asset `index-9zfXgtWz.js`  
**Phase 2 built asset (repo / deploy package, not Live):** `index-BkeSH4cj.js`

**Goals:** make decision experience primary — Market Regime Hero, Top Long/Short spotlight, declutter top bar, Event Center, Watchlist, Simple language, scanner/detail productization. No scanner scoring/ranking rewrite.

**Delivered in code:**
- Design tokens: `frontend/src/styles/phase2Tokens.css` (+ Phase 2 layout CSS in `global.css`)
- Top bar: brand · scanner freshness · coverage · Simple/Advanced · Event bell · System Status · AI — HOLD / 4.19 moved to System Status drawer
- Nav: 主要產品 / 研究工具 / 系統資訊 (+ `/watchlist`)
- Overview: regime hero + data-driven summary (`marketSummary.ts`) · spotlight #1 Long/Short · compact #2–5 · Long/Short balance · chart narratives
- Event Center drawer (toast/sound/browser notify prefs; sound & browser default OFF; high-priority toast filter)
- Local Watchlist (localStorage v1, max 30, no account)
- Scanner desktop sticky table + row expand; mobile candidate cards
- Symbol detail: Why candidate · support/risk · score bars · price/OI charts
- Shared `MarketScannerProvider` polling for top bar + overview
- SPA prefix `watchlist`; build marker `NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE2_DECISION_EXPERIENCE`
- Previous Live asset `index-9zfXgtWz.js` retained in static package

**Verifies (stdout):** phase2 visual · event/watchlist · product UI · market universe · MVP-22A–D · SPA cache resilience · frontend typecheck/build

**Verdict (code):** `PASS — NEXUS PRODUCT TRANSFORMATION PHASE 2 VERIFIED IN CODE`

**remaining_issues:**
- redeploy and live Phase 2 visual/product sign-off pending
- full-market WebSocket fast-lane deferred
- real anomaly outcome duration pending
- oi_5m/oi_15m duration pending

## 29. Phase 2 Redeploy + Live Decision Experience Sign-off (2026-07-17)

**Live Source of Truth:** `7dfc87886b2adcd0af93bc1073e434d5e5b0a1bf`  
**Live asset:** `index-BkeSH4cj.js`  
**UI marker:** `NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE2_DECISION_EXPERIENCE`  
**Deployment:** Zeabur GitHub auto-deploy from `stage3-demo-learning` · status `RUNNING` · served_by `nexus-web`  
**URL:** https://nexus-stage3-bybit-demo-learning.zeabur.app/

**Predeploy:** remote head = `7dfc878` · expected asset reproducible from commit tree · unrelated dirty tree preserved · no dirty deploy

**Live API (real data, post-window):**
- Scanner: `freshness=LIVE` · `symbolCount=80` · `cycleCount` advancing ~1 / 20s · `loopOverlapBlocked=true` · `threadAlive=true` · `private_api=false`
- Breadth sum = 80 · Long/Short candidates non-empty after 5m window · no collecting Top-5 fill
- Events stream live (NEW_TOP / RANK_UP observed)
- Charts: Turnover Top 10 · Price/OI quadrant points from real 5m windows

**Live UI (Playwright, real data — not stubs):**
- Top bar: no Backend HOLD / 4.19 chips; System Status drawer retains HOLD + 4.19 BLOCKED
- Overview 3s: regime（偏多／偏空／混合／累積中）· coverage 80 · Top Long/Short spotlight · 持倉 plain language · stage 產品語 · cadence ~20s · research/no-trading
- Event Center: unread badge · drawer · sound/browser notify default OFF
- Scanner: desktop sticky + mobile cards · no page horizontal overflow at audited sizes
- Symbol detail: 「為什麼是候選」· no「完整生命週期時間線」claim (partial status only)
- Watchlist: `/watchlist` hard refresh 200 · localStorage · no account
- SPA: HTML `no-store` · previous `index-9zfXgtWz.js` retained 200 · current HTML only references `BkeSH4cj`

**Perf (bounded observation):** overview scanner hits ≈5 on first settle · scanner ≈7 · symbol ≈6 · no duplicate topbar/overview provider · JS 448190 B · HTML ~2.8 KB

**Verdict:** `PASS — NEXUS PRODUCT TRANSFORMATION PHASE 2 DEPLOYED AND LIVE VERIFIED`

**remaining_issues:**
- Full candidate stage transition timeline deferred
- Full-market WebSocket fast-lane deferred
- Real anomaly outcome duration pending
- OI 5m／15m duration pending (BTC/ETH/SOL feed)

## 30. Phase 3 — Sector / Chart / Equities Foundation (code verified)

**Code commit (foundation):** `8f68e269be06bd6cf0d6cbcdaeeb911fe49ade93` · asset `index-ChR5GS_H.js`  
**Honesty fix commit (Live):** `3d213c8a480f822664e286010fe45a817f8ae415` · asset `index-BZTA1-bM.js`

### Delivered in code
- Crypto Sector Taxonomy (NEXUS curated, multi-membership, provenance/confidence)
- Server-side Sector Aggregation Engine + `/api/market/sectors*` (breadth dynamic ~642–748 + deep ~80)
- `/crypto/sectors`, `/crypto/sectors/:slug`, `/crypto/oi`, `/crypto/funding`, `/crypto/price-oi`
- Sector detail → `/crypto/price-oi?sector=` filtered deep link (inline Price／OI chart deferred)
- NEXUS Chart Data Layer: `/api/market/charts/ohlcv|open-interest|funding` (Bybit public; funding history honest unavailable)
- Symbol detail SVG chart via NEXUS datafeed; chart marker scope declared as current-state only
- Equities foundation: `/equities/tokenized` · `/equities/analysis` · provider-pending (no fake quotes)
- Watchlist schema v2 (`assetClass`) with v1 migration
- Hierarchical nav: product / crypto / equities / research / system

**Architecture note:** `docs/ui/NEXUS_PHASE3_SECTOR_CHART_EQUITIES_ARCHITECTURE.md`

## 31. Phase 3 Live State Discovery + Sign-off (2026-07-18)

**Live Source of Truth:** `3d213c8a480f822664e286010fe45a817f8ae415`  
**Live asset:** `index-BZTA1-bM.js`  
**UI marker:** `NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE3_SECTOR_CHART_EQUITIES`  
**Deployment:** Zeabur GitHub auto-deploy from `stage3-demo-learning` · status `RUNNING` · served_by `nexus-web` · runtime `run.py`  
**URL:** https://nexus-stage3-bybit-demo-learning.zeabur.app/

### Live State Discovery
- First probe after Phase 3 push: already auto-deployed `8f68e269` / `index-ChR5GS_H.js` / Phase 3 marker / sector+chart APIs live → **no unnecessary repeat Redeploy**
- Honesty fix push `3d213c8` auto-deployed → current Live SoT
- Retained previous assets: `index-ChR5GS_H.js`, `index-BkeSH4cj.js` (200)

### Live truth (post 5m warmup)
- Breadth `642` · Deep scan `80/80` · Sector count `19` · freshness LIVE
- Classified ~109 / unclassified ~533 (not forced into Other)
- Scanner `cycleCount` advancing · `loopOverlapBlocked=true` · Long/Short candidates non-empty after window
- Price／OI quadrant real points (no zero-fill) · Sector OI 5m uses sample counts / null when insufficient
- Layer1 candidate counts matched ranked scanner membership
- OHLCV Live == Bybit public for BTC/ETH/SOL (timestamp+close) · intervals 1m–1d
- Funding history API `available=false` · `fabricatedHistory=false`
- Equities pages: provider pending · no fake quotes (Playwright)
- SPA: HTML `no-store` · hashed assets immutable · hard refresh on sector/equities routes 200
- Playwright responsive viewports 1440→360: overflow failures `0`

### Honesty scope (explicit)
- Sector Price／OI: filtered deep link (not inline chart)
- Candidate／Anomaly／Signal Reference chart markers: current-state only (not full history)
- Historical funding series: unavailable
- Equity／tokenized providers: not connected

**Verdict:** `PASS — NEXUS PRODUCT TRANSFORMATION PHASE 3 DEPLOYED AND LIVE VERIFIED`

**remaining_issues:**
- Licensed equity market data provider selection pending
- Tokenized equity provider selection pending
- Inline sector Price／OI chart deferred (filtered deep link available)
- Full candidate／anomaly historical chart markers deferred
- Historical funding series unavailable
- Full-market WebSocket fast-lane deferred
- Full candidate stage transition timeline deferred
- Real anomaly outcome duration pending


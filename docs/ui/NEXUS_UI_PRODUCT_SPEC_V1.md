# NEXUS / EATI UI Product Spec v1

**Status:** Spec only (no live trading UI implementation in this stage)  
**Mode:** Research-only / read-only  
**Audience:** Operators, researchers, future SaaS members  

---

## 1. Product positioning

NEXUS / EATI is an **AI research + risk governance + reflection + evidence audit** platform for multi-fleet crypto market observation — not a signal tip site and not a live order terminal.

Core pillars:

1. AI research platform  
2. Risk governance  
3. Trade reflection  
4. Evidence audit  
5. Multi-AI fleet observation  
6. Provider Shadow Governance  
7. Future enterprise SaaS  

Hard product rules:

- No guaranteed profit claims  
- No direct investment advice  
- No live order execution in v1 UI  
- No ARM / production / btc-auto controls in UI  
- All actionable-looking states are **observe / watch / skip / blocked** language  

---

## 2. Visual system

- Dark fintech dashboard background  
- Card-based layout with clear hierarchy  
- Left sidebar navigation  
- Top market ticker / status bar  
- Right AI Assistant rail (desktop)  
- Mobile-first PWA; desktop supports multi-panel evidence views  
- Every signal shows reason, risk, invalidation — never direction-only  

---

## 3. Global chrome

### Top Status Bar

| Element | Purpose |
|---------|---------|
| NEXUS / EATI logo | Brand |
| System Mode | Research-only / Paper / Testnet |
| Safety | No ARM / No Live Trading / Defensive ON |
| Last Update Time | Freshness |
| Stage Readiness | Current Stage 4.x readiness flags |
| Current Gate | e.g. 4.18-P2 design gate |

### Layout shell

```
┌─────────────────────────────────────────────────────────────┐
│ Top Status Bar + Market Ticker                              │
├──────────┬──────────────────────────────────┬───────────────┤
│ Sidebar  │ Main content (page)              │ AI Assistant  │
│ nav      │                                  │ (tabs)        │
└──────────┴──────────────────────────────────┴───────────────┘
```

---

## 4. Page inventory (v1)

### 4.1 Market Overview

Cards for BTC / ETH / SOL / PEPE:

- price, 24h change  
- market regime, risk score  
- status: `observe` / `would_enter` / `would_skip` / `blocked`  
- provider, confidence, last decision time  

### 4.2 AI Fleet Center

Per-fleet (BTC / ETH / SOL / PEPE):

- current intent, confidence  
- valid_watch / soft_skip / hard_skip  
- MAE, entry trigger, invalidation  
- provider, graduation status  

### 4.3 AI Round Table

Roles: Trend AI, Risk AI, News AI, Reflection AI  

- Final consensus  
- Disagreement notes  
- Why not trade now  
- What confirmation is needed  

### 4.4 Signal / Anomaly Center

Taxonomy (no buy/sell labels):

`observe` · `building` · `watch` · `valid_watch` · `confirmed` · `overheated` · `blocked_by_risk`

Each row: reason, risk, invalidation, MAE, confidence, data quality, provider, evidence link.

### 4.5 Visual Screener (four quadrants)

- X: AI confidence · Y: risk score  
- Q1 high conf / low risk → priority observation  
- Q2 high conf / high risk → observe only, do not chase  
- Q3 low conf / low risk → wait for data  
- Q4 low conf / high risk → trade forbidden  

### 4.6 Risk & Evidence Center

Flags and gate results:

- `order_allowed=false`, `mock=false`, `ARM=false`, `production=false`, `paper execution=false`  
- validator / calibration / graduation  
- provider health, reset status, safety logs  

### 4.7 Evidence Vault

Recent AI decisions: symbol, decision, confidence, risk, reason, data quality, skip reason, timestamp, provider, stage marker, report link.

### 4.8 Reflection Center

Mistakes, repeated errors, confidence penalty, size adjustment, behavior change, next patch recommendation, applied / not applied.

### 4.9 Provider Shadow Center

Actual vs shadow provider, divergence, comparable / uncomparable, quota / truncated / unknown intent, **shadow excluded from paper/calibration/graduation**, shadow must not affect Stage 4.19.

### 4.10 Paper Trading Lab (read-only)

`would_enter` / `would_skip` / watchlist / calibration / graduation / why not graduated / paper logger status.

### 4.11 AI Assistant (tabs)

Ask current page · Find risk · Find opportunity · Daily brief · Explain decision · Ask reflection · Ask evidence · Why can’t we trade now?

### 4.12 Learning Center / NEXUS Academy

Free / Standard / Pro curriculum (risk literacy, round table, paper trading, OI/CVD, reflection, shadow governance).

### 4.13 Risk Calculator

Account size, max risk/trade, max daily loss, stop distance, leverage warning, liquidation buffer, suggested size, stop-after-3-losses guidance.

### 4.14 Notification Center

Daily brief, risk elevated, round table done, market/fleet anomaly, provider divergence, paper result, reflection report, consecutive error warning.

### 4.15 Membership Center

Tiers: Free → Standard → Pro → Elite → Team → Enterprise (see permission matrix).

---

## 5. Non-goals (v1)

- Live order tickets / ARM arming  
- Editing Risk Governor thresholds  
- Changing provider routing  
- Starting Stage 4.19  
- Guaranteed PnL dashboards  

---

## 6. Data & demo policy

UI reads summary / reports / JSON outputs only.  
If live data missing: show **DEMO DATA / READ-ONLY / NOT INVESTMENT ADVICE**.

---

## 7. Related docs

- [Sitemap](./NEXUS_UI_SITEMAP_V1.md)  
- [Permission matrix](./NEXUS_UI_PERMISSION_MATRIX_V1.md)  
- [Data source mapping](./NEXUS_UI_DATA_SOURCE_MAPPING_V1.md)  
- [MVP roadmap](./NEXUS_UI_MVP_ROADMAP_30_90_DAYS.md)  

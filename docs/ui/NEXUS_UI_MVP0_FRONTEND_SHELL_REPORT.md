# NEXUS / EATI UI MVP-0 Frontend Shell Report

**Status:** Complete (read-only shell)  
**Date:** 2026-07-11  
**Mode:** Research-only / DEMO DATA  
**Location:** `frontend/`

---

## 1. Summary

MVP-0 delivers a Vite + React + TypeScript dark fintech dashboard shell with left sidebar, top status bar, and right AI rail. All pages consume a demo-only adapter. No live trading, ARM, or routing-edit surfaces exist.

---

## 2. Pages

| Route | Page | Notes |
|-------|------|-------|
| `/` | redirect | → `/overview` |
| `/overview` | OverviewPage | BTC/ETH/SOL/PEPE cards + round-table summary |
| `/fleets` | FleetsPage | Fleet cards; membership lock stub |
| `/signals` | SignalsPage | observe/watch/skip/blocked taxonomy |
| `/risk-evidence` | RiskEvidencePage | Safety flags (`order_allowed=false`, `ARM=false`, …) |
| `/evidence` | EvidencePage | Evidence vault list |
| `/reflection` | ReflectionPage | Reflection summary card |
| `/provider-shadow` | ProviderShadowPage | Shadow compare; excluded from paper/calibration/graduation |
| `/paper-lab` | PaperLabPage | would_enter / would_skip counts (read-only) |
| `/assistant` | AssistantPage | Full-page AI stub (+ desktop rail) |
| `/academy` | AcademyPage | Free / Standard / Pro curriculum stubs |
| `/calculator` | CalculatorPage | Educational risk sizing stub |
| `/membership` | MembershipPage | Free→Enterprise tiers |

**Explicitly absent routes:** `/trade`, `/orders`, `/arm`, `/routing-edit`, `/production`, `/btc-auto`.

---

## 3. Components

| Component | Role |
|-----------|------|
| `SafetyBanner` | Fixed: READ-ONLY · RESEARCH MODE · NOT INVESTMENT ADVICE · NO LIVE TRADING |
| `TopStatusBar` | NEXUS/EATI, Research-only, No ARM / No Live Trading / Defensive ON, Stage 4.18-P2 / P2-R1 candidate, Last Update, Not Investment Advice |
| `SidebarNav` | Research nav only |
| `DemoDataBadge` | `DEMO DATA` label |
| `FleetCard` | Fleet observation card |
| `MarketStatusCard` | Market overview card |
| `SignalStatusBadge` | Status chip |
| `RiskScoreBadge` | Risk score chip |
| `EvidenceItemCard` | Evidence row card |
| `ProviderComparisonCard` | Actual vs shadow |
| `ReflectionSummaryCard` | Reflection summary |
| `MembershipLockBadge` | Upgrade to Pro/Elite/Team (UI lock only) |
| `AICommanderPanel` | Right rail / assistant tabs |

---

## 4. Adapter

`src/data/nexusDataAdapter.ts` exposes read-only getters:

- `getMarketOverview`
- `getFleetStatus`
- `getSignals`
- `getEvidence`
- `getReflectionSummary`
- `getProviderShadowSummary`
- `getPaperLabSummary`
- `getMembershipTiers`

(+ helpers: `getSystemStatus`, `getRoundTable`, `getRiskEvidenceFlags`)

All return demo fixtures. **No write methods. No order / ARM / routing APIs.**

---

## 5. Demo policy

- Every demo object sets `demo: true`.
- Canonical `source`: `DEMO DATA - READ ONLY - NOT INVESTMENT ADVICE`.
- UI surfaces show `DemoDataBadge` and SafetyBanner.
- Copy uses observe / watch / skip / blocked language only.
- **Forbidden copy:** guaranteed profit, must buy, must sell.

---

## 6. Permission stub

`MembershipLockBadge` compares Free/Standard/Pro/Elite/Team/Enterprise ranks and shows **Upgrade to Pro / Elite / Team** CTAs. Buttons are no-ops (UI lock only). No billing or entitlement backend.

---

## 7. Safety

Runnable check:

```bash
python tools/research/check_nexus_ui_mvp0_safety.py
```

Optional Node mirror:

```bash
cd frontend && npm run check:safety
```

Scanner verifies:

- No forbidden Route paths (`/trade`, `/orders`, `/arm`, `/routing-edit`)
- No forbidden marketing / write API strings
- DEMO DATA labels and SafetyBanner text present
- Required research routes registered in `App.tsx`

---

## 8. Backend untouched

This MVP-0 work did **not** modify:

- `backend/` trading, governance, or execution modules
- Stage 4 trading / research runners (except adding the UI safety script under `tools/research/`)
- Risk Governor, ARM, provider routing, or order paths

---

## 9. How to run (local)

```bash
cd frontend
npm install
npm run dev
```

---

## 10. Next step

Wire adapter getters to read-only JSON/report summaries (Stage 4.x artifacts) behind the same interfaces, keep DEMO fallback when live data is missing, and expand Evidence detail / Round Table layouts — still without any write or ARM controls.

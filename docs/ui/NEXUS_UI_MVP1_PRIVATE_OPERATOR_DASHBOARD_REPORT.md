# NEXUS / EATI UI MVP-1 — Private Operator Dashboard Report

**Status:** Complete (read-only Private Operator Dashboard)  
**Date:** 2026-07-13  
**Mode:** Private Operator Mode ON / DEMO DATA / Research-only  
**Location:** `frontend/`  
**Safety check:** `python tools/research/check_nexus_ui_mvp1_safety.py`

---

## 1. Summary

MVP-1 extends the MVP-0 shell into a **Private Operator Dashboard**: Stage Gate, Safety Status, P2-R1 graduation/evidence surfaces, and Future Public SaaS membership labels only. All data remains demo fixtures under `frontend/src/demo/`. No live trading, ARM, routing edit, billing, or customer-account surfaces.

---

## 2. Product boundary

See `docs/ui/NEXUS_PRIVATE_VS_PUBLIC_PRODUCT_BOUNDARY.md`.

| Now | Future (label only) |
|-----|---------------------|
| Private Operator UI (read-only) | Public SaaS membership tiers |
| Stage / safety / graduation flags | Billing / customer accounts |
| DEMO DATA adapter | Copy trading / managed accounts |

Membership page copy: **Future only / Not implemented / No billing**.

---

## 3. Demo fixture (P2-R1)

| Field | Value |
|-------|-------|
| Stage | `4.18-P2-R1` · `PARTIAL_BTC_ONLY` |
| P2A | pending |
| BTC graduation (actual-only) | **3** |
| ETH graduation (actual-only) | **0** |
| `stage_419_readiness` | **false** |
| `should_start_419` | **false** |
| `order_allowed` | **false** |
| ARM | **false** |
| production | **false** |
| Shadow → graduation | **excluded** |
| Private Operator Mode | **ON** |

Canonical source string: `DEMO DATA - READ ONLY - NOT INVESTMENT ADVICE`.

---

## 4. Types added (`frontend/src/types/nexus.ts`)

- `StageGateStatus`
- `ProviderStatusSummary`
- `LatestReportMeta`
- `GraduationStatusSummary`
- `SafetyStatusSummary`
- `PrivateOperatorMode`

All extend `DemoMeta` (`demo: true`, DEMO DATA `source`).

---

## 5. Adapter getters (`frontend/src/demo/nexusDataAdapter.ts`)

| Getter | Role |
|--------|------|
| `getSystemStatus` | Top bar / mode |
| `getStageGateStatus` | Stage Gate card |
| `getProviderStatus` | Provider health summary |
| `getLatestReports` | Latest report metas |
| `getEvidenceVault` | Evidence vault list |
| `getEvidence` | Alias → `getEvidenceVault` |
| `getGraduationStatus` | Actual-only graduation |
| `getSafetyStatus` | Safety Status card |
| `getPrivateOperatorMode` | Operator Mode banner |

Existing getters retained (`getMarketOverview`, `getFleetStatus`, `getSignals`, `getReflectionSummary`, `getProviderShadowSummary`, `getPaperLabSummary`, `getMembershipTiers`, `getRoundTable`, `getRiskEvidenceFlags`).

**No write methods. No order / ARM / routing APIs.**

---

## 6. Pages updated

| Page | MVP-1 change |
|------|----------------|
| `OverviewPage` | Private Operator Mode banner; Stage Gate + Safety Status + latest reports (4.18-P2-R1 / P2A pending) |
| `RiskEvidencePage` | `order_allowed=false`, `ARM=false`, `production=false`, `stage_419_readiness=false`, `should_start_419=false` |
| `ProviderShadowPage` | P1C / P2 design / P2-R1 summary cards; shadow excluded; actual-only graduation |
| `PaperLabPage` | BTC graduation=3, ETH=0, Stage 4.19 blocked |
| `MembershipPage` | Future Public SaaS tiers with Future only / Not implemented / No billing |

---

## 7. CSS

`frontend/src/styles/global.css` adds lightweight Private Operator banner / card styles (dark fintech; no gambling styling).

---

## 8. Safety scanner

`tools/research/check_nexus_ui_mvp1_safety.py` scans `frontend/src` and fails on:

- Billing product surfaces (allows “No billing” documentation)
- Customer accounts / API key collection UI
- Copy trading / managed accounts / guaranteed profit
- Live trade routes; order/ARM APIs; routing editor

Requires Private Operator labels + `SafetyBanner` + DEMO DATA policy + MVP-1 types/getters/fixtures.

**Explicitly absent routes:** `/trade`, `/orders`, `/arm`, `/routing-edit`, `/production`, `/btc-auto`.

---

## 9. Test command

```bash
python tools/research/check_nexus_ui_mvp1_safety.py
```

Expected: **PASS**.

---

## 10. Files touched

**Added**

- `docs/ui/NEXUS_PRIVATE_VS_PUBLIC_PRODUCT_BOUNDARY.md`
- `docs/ui/NEXUS_UI_MVP1_PRIVATE_OPERATOR_DASHBOARD_REPORT.md`
- `tools/research/check_nexus_ui_mvp1_safety.py`

**Modified**

- `frontend/src/types/nexus.ts`
- `frontend/src/demo/demoNexusData.ts`
- `frontend/src/demo/nexusDataAdapter.ts`
- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/pages/RiskEvidencePage.tsx`
- `frontend/src/pages/ProviderShadowPage.tsx`
- `frontend/src/pages/PaperLabPage.tsx`
- `frontend/src/pages/MembershipPage.tsx`
- `frontend/src/styles/global.css`
- `frontend/src/App.tsx` (comment only)

---

## 11. Prohibited areas left untouched

- Backend trading / strategy / order execution / leverage modules  
- Risk Governor editors  
- Provider routing editors  
- ARM / production / Stage 4.19 start controls  
- Billing / customer account / copy-trading / managed-account product code  

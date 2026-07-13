# NEXUS / EATI UI MVP-2 — Private Operator Data Snapshot Wiring Report

**Status:** Complete (read-only Private Operator snapshot wiring)  
**Date:** 2026-07-13  
**Mode:** Private Operator Mode ON / SANITIZED SNAPSHOT / Research-only  
**Location:** `frontend/`  
**Safety check:** `python tools/research/check_nexus_ui_mvp2_safety.py`

---

## 1. MVP-1 recap

MVP-1 delivered the Private Operator Dashboard shell: Stage Gate, Safety Status, graduation/evidence surfaces, and Future Public SaaS membership labels. Data lived in `frontend/src/demo/demoNexusData.ts` with adapter getters and MVP-1 safety scanning. No live trading, ARM, routing edit, billing, or customer-account surfaces.

MVP-2 builds on that shell by wiring a **sanitized backend-stage snapshot** so Overview / Risk / Shadow / Paper Lab reflect Stage **4.18-P2A** without connecting to live APIs or `/data` logs.

---

## 2. Snapshot schema

Schema file: `frontend/src/types/nexusSnapshot.ts`

| Field | Role |
|-------|------|
| `systemStatus` | Mode / safety line / gate chrome |
| `safetyStatus` | order/ARM/production/4.19 flags (all false) |
| `stageGate` | Stage label + verdict + notes |
| `latestBackendStage` | e.g. `4.18-P2A` |
| `latestVerdict` | e.g. `STAGE_4_18P2A_PASS` |
| `btcStatus` | Actual-only BTC graduation summary |
| `ethStatus` | Actual-only ETH status + root cause |
| `providerRoutingStatus` | Experiment routing labels; permanent change unsupported |
| `providerShadowStatus` | Shadow excluded; actual-only graduation |
| `paperLabStatus` | BTC passed / ETH blocked + next diagnostic |
| `reports` | Report metas (docs paths only) |
| `uiMode` | `"demo"` \| `"private_operator_snapshot"` |

---

## 3. Sanitized snapshot policy

**Path note:** Snapshots live under `frontend/src/demo/snapshots/` — **not** `frontend/src/data/`.

Root `.gitignore` matches any `data/` folder and would block commits of `frontend/src/data/`. The MVP-2 fixture is therefore:

`frontend/src/demo/snapshots/p2aPrivateOperatorSnapshot.ts`

| Policy | Value |
|--------|-------|
| Source string | `SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE` |
| Secrets | Forbidden |
| API keys | Forbidden |
| `/data` raw paths | Forbidden |
| Latest stage | `4.18-P2A` |
| Latest verdict | `STAGE_4_18P2A_PASS` |
| BTC graduation (actual) | **3** |
| ETH graduation (actual) | **0** |
| ETH root cause | `eth_followup_confirmation_failed` |
| `stage_419_readiness` | **false** |
| `should_start_419` | **false** |
| `routing_permanent_change_supported` | **false** |
| `uiMode` | `private_operator_snapshot` |

---

## 4. Adapter updates

File: `frontend/src/demo/nexusDataAdapter.ts`

| Addition | Role |
|----------|------|
| `getNexusSnapshot()` | Active snapshot-shaped payload |
| `getCurrentUiMode()` | `demo` \| `private_operator_snapshot` |
| `getLatestBackendVerdict()` | Backend verdict string |
| `getStage419Status()` | Blocked / readiness / should_start flags |
| `getPrivateOperatorSnapshot()` | Canonical P2A sanitized fixture |
| `setNexusUiMode()` | Switch demo vs snapshot (default: snapshot) |

Existing getters (`getStageGateStatus`, `getSafetyStatus`, `getGraduationStatus`, `getPaperLabSummary`, `getProviderShadowSummary`, `getProviderStatus`, `getLatestReports`, `getRiskEvidenceFlags`, …) **prefer the sanitized snapshot** when `uiMode === private_operator_snapshot`.

**No write methods. No order / ARM / routing APIs.**

---

## 5. Pages updated

| Page | MVP-2 change |
|------|----------------|
| `OverviewPage` | `latestBackendStage`, `latestVerdict`, BTC grad=3, ETH grad=0, Stage 4.19 blocked |
| `RiskEvidencePage` | safetyStatus; no order / no ARM / no production; `should_start_419=false` |
| `ProviderShadowPage` | P2-R1 BTC Cerebras-first; permanent routing not supported; actual-only graduation |
| `PaperLabPage` | BTC passed / ETH blocked; next diagnostic = P2B ETH confirmation diagnostics |
| `MembershipPage` | Future only / customer SaaS not implemented / No billing |

---

## 6. Current backend stage displayed

Overview Stage Gate card shows:

- `latestBackendStage: 4.18-P2A`
- Stage gate label `4.18-P2A`
- Source: sanitized snapshot (default UI mode)

---

## 7. BTC/ETH graduation status displayed

| Symbol | Actual graduation | UI label |
|--------|-------------------|----------|
| BTC | **3** | passed (actual-only) |
| ETH | **0** | blocked; root cause `eth_followup_confirmation_failed` |

Surfaces: Overview graduation card, Provider Shadow P2-R1 card, Paper Lab flags.

---

## 8. Stage 4.19 blocked display

Across Overview, Risk Evidence, Provider Shadow, and Paper Lab:

- `stage_419_readiness=false`
- `should_start_419=false`
- Stage 4.19 = **blocked**
- No Stage 4.19 start button (forbidden; safety-scanned)

---

## 9. Future public SaaS still not implemented

Membership Center remains architecture labels only:

- **Future only / Not implemented / No billing**
- **customer SaaS not implemented**
- No billing portal, customer accounts, API key collection, copy trading, or managed accounts

---

## 10. Safety checks

```bash
python tools/research/check_nexus_ui_mvp2_safety.py
```

Scanner verifies:

1. Snapshot source contains `SANITIZED SNAPSHOT`
2. No secrets / API key literals in snapshot
3. No `/data` raw paths in frontend snapshots
4. No billing implementation
5. No customer accounts
6. No API key collection
7. No copy trading
8. No managed accounts
9. No trade routes
10. No order API
11. No ARM API
12. No routing editor
13. No Stage 4.19 start button
14. Private Operator label present
15. READ ONLY / NOT INVESTMENT ADVICE present

Expected: **PASS**.

---

## 11. Trading backend untouched

Intentionally left unmodified:

- Backend trading / strategy / order execution / leverage modules  
- Provider routing runtime / env chains  
- Risk Governor thresholds / MAE / confidence floor  
- ARM / production / btc-auto controls  
- Stage 4.19 start tooling  

UI remains read-only research chrome only.

---

## 12. Next UI step

Suggested (gated; not started here):

1. Optional Snapshot vs Demo toggle in chrome (still read-only)  
2. Wire additional sanitized stage snapshots as backend gates advance (P2B+)  
3. Evidence Vault links to report metas (docs paths only)  
4. Keep Public SaaS / billing / accounts out of scope until product decision  

**Stop at gate.** Do not start Stage 4.19 from UI.

---

## Files touched

**Added**

- `frontend/src/types/nexusSnapshot.ts`
- `frontend/src/demo/snapshots/p2aPrivateOperatorSnapshot.ts`
- `tools/research/check_nexus_ui_mvp2_safety.py`
- `docs/ui/NEXUS_UI_MVP2_PRIVATE_OPERATOR_DATA_SNAPSHOT_REPORT.md`

**Modified**

- `frontend/src/demo/nexusDataAdapter.ts`
- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/pages/RiskEvidencePage.tsx`
- `frontend/src/pages/ProviderShadowPage.tsx`
- `frontend/src/pages/PaperLabPage.tsx`
- `frontend/src/pages/MembershipPage.tsx`

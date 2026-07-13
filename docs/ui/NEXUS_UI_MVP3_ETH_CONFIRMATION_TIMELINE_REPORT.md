# NEXUS / EATI UI MVP-3 — ETH Confirmation Timeline Report

**Status:** Complete (read-only Private Operator P2B snapshot + ETH confirmation timeline)  
**Date:** 2026-07-13  
**Mode:** Private Operator Mode ON / SANITIZED SNAPSHOT / Research-only  
**Location:** `frontend/`  
**Safety check:** `python tools/research/check_nexus_ui_mvp3_safety.py`

---

## 1. MVP-2 / P2A recap

MVP-2 wired a sanitized **4.18-P2A** Private Operator snapshot (`p2aPrivateOperatorSnapshot.ts`) with BTC graduation=3, ETH graduation=0, root cause `eth_followup_confirmation_failed`, and Stage 4.19 blocked. Adapter defaulted to `private_operator_snapshot` mode under `frontend/src/demo/snapshots/` (not `src/data/`).

MVP-3 advances the UI to **Stage 4.18-P2B** ETH watchlist follow-up confirmation diagnostics without live APIs, `/data` paths, or trading controls.

---

## 2. P2B snapshot

**Path:** `frontend/src/demo/snapshots/p2bPrivateOperatorSnapshot.ts`

| Field | Value |
|-------|--------|
| Source | `SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE` |
| `uiMode` | `private_operator_snapshot` |
| Latest stage | `4.18-P2B` |
| Latest verdict | `STAGE_4_18P2B_PASS` |
| BTC graduation (actual) | **3** |
| ETH valid_watch | **1** |
| ETH graduation (actual) | **0** |
| ETH failure reason | `eth_followup_direction_changed` |
| ethDetail | `LONG/BUY → NONE/NONE` |
| `invalidation_breached` | **false** |
| `mae_breached` | **false** |
| `stage_419_readiness` | **false** |
| `should_start_419` | **false** |
| `routing_permanent_change_supported` | **false** |

Includes `ethConfirmationTimeline` with watch + follow-up tick fields matching P2B diagnostics.

**Secrets / API keys / `/data` raw paths:** forbidden (safety-scanned).

---

## 3. ETH confirmation timeline UI

**Component:** `frontend/src/components/EthConfirmationTimelineCard.tsx`

| Section | Display |
|---------|---------|
| Watch tick | provider=cerebras, intent=watch, confidence=0.55, LONG/BUY, MAE 0.30, triggers present |
| Follow-up tick | intent=hard_skip, confidence=0.0, NONE/NONE, no MAE/invalidation breach |
| Conclusion | confirmation failed · `eth_followup_direction_changed` · next = **P2C market context review** |
| Labels | `DemoDataBadge` + `SANITIZED` badge |

---

## 4. Adapter updates

**File:** `frontend/src/demo/nexusDataAdapter.ts`

| Change | Role |
|--------|------|
| Default snapshot | Prefers **P2B** over P2A (`ACTIVE_PRIVATE_OPERATOR_SNAPSHOT`) |
| `getEthConfirmationTimeline()` | Returns sanitized ETH watch → follow-up timeline |
| Existing getters | Continue to prefer Private Operator snapshot when `uiMode === private_operator_snapshot` |

**No write methods. No order / ARM / routing APIs.**

---

## 5. Pages updated

| Page | MVP-3 change |
|------|----------------|
| `OverviewPage` | P2B stage/verdict; ETH blocker = `eth_followup_direction_changed` |
| `RiskEvidencePage` | ETH follow-up failure risk card (no MAE/invalidation breach; LONG/BUY → NONE/NONE) |
| `PaperLabPage` | Embeds `EthConfirmationTimelineCard`; next diagnostic = P2C |
| `EvidencePage` | ETH watch / follow-up evidence summaries |
| `ProviderShadowPage` | BTC Cerebras-first **experiment supported** vs **permanent routing not supported** |

---

## 6. Safety checks

```bash
python tools/research/check_nexus_ui_mvp3_safety.py
```

Scanner verifies (among others):

1. Snapshot source contains `SANITIZED SNAPSHOT`
2. No secrets / API key literals
3. No `/data` raw paths in frontend snapshots
4. No billing / customer accounts / API key collection
5. No copy trading / managed accounts
6. No trade / order / ARM / routing-editor routes
7. No Stage 4.19 start button
8. Private Operator + READ ONLY / NOT INVESTMENT ADVICE
9. `STAGE_4_18P2B_PASS` + `eth_followup_direction_changed` present in frontend source
10. Adapter prefers P2B; `EthConfirmationTimelineCard` present

Expected: **PASS**.

---

## 7. Trading backend untouched

Intentionally left unmodified:

- Backend trading / strategy / order execution / leverage modules  
- Provider routing runtime / env chains  
- Risk Governor thresholds / MAE / confidence floor  
- ARM / production / btc-auto controls  
- Stage 4.19 start tooling  

UI remains read-only research chrome only.

---

## 8. Next UI step

Suggested (gated; not started here):

1. Optional Snapshot vs Demo toggle in chrome (still read-only)  
2. Wire P2C market-context review snapshot when backend gate lands  
3. Keep Public SaaS / billing / accounts out of scope  

**Stop at gate.** Do not start Stage 4.19 from UI.

---

## Files touched

**Added**

- `frontend/src/demo/snapshots/p2bPrivateOperatorSnapshot.ts`
- `frontend/src/components/EthConfirmationTimelineCard.tsx`
- `tools/research/check_nexus_ui_mvp3_safety.py`
- `docs/ui/NEXUS_UI_MVP3_ETH_CONFIRMATION_TIMELINE_REPORT.md`

**Modified**

- `frontend/src/types/nexusSnapshot.ts`
- `frontend/src/demo/nexusDataAdapter.ts`
- `frontend/src/pages/OverviewPage.tsx`
- `frontend/src/pages/RiskEvidencePage.tsx`
- `frontend/src/pages/PaperLabPage.tsx`
- `frontend/src/pages/EvidencePage.tsx`
- `frontend/src/pages/ProviderShadowPage.tsx`

# NEXUS / EATI UI MVP-5 — P2D Prompt Repair Status Report

**Status:** Complete (read-only Private Operator P2D snapshot + prompt repair status display)  
**Date:** 2026-07-13  
**Mode:** Private Operator Mode ON / SANITIZED SNAPSHOT / Research-only  
**Location:** `frontend/`  
**Safety check:** `python tools/research/check_nexus_ui_mvp5_safety.py`

---

## 1. MVP-4 recap

MVP-4 wired a sanitized **4.18-P2C** Private Operator snapshot showing ETH failure as `confirmation_prompt_too_strict` (SYSTEM ISSUE / NOT MARKET REVERSAL) with next = P2D confirmation prompt review.

MVP-5 advances to **Stage 4.18-P2D** so operators can see **prompt repair status** and that the next step is **P2D-R1 runtime regression** — not Stage 4.19.

---

## 2. P2D snapshot update

**Path:** `frontend/src/demo/snapshots/p2dPrivateOperatorSnapshot.ts`

| Field | Value |
|-------|--------|
| Source | `SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE` |
| `uiMode` | `private_operator_snapshot` |
| Latest stage | `4.18-P2D` |
| Latest verdict | `STAGE_4_18P2D_PASS` |
| BTC graduation | **3** |
| ETH graduation | **0** |
| ETH previous failure | `confirmation_prompt_too_strict` |
| SYSTEM ISSUE | preserved historically |
| Stage 4.19 | blocked (`stage419Readiness=false`, `shouldStart419=false`) |
| Permanent routing | not supported |
| Next | **P2D-R1 runtime regression** |

Adapter prefers **P2D → P2C → P2B → P2A**.

---

## 3. Prompt repair status object

| Flag | Value |
|------|--------|
| `promptRepairAdded` | true |
| `previousWatchContextInjected` | true |
| `entryTriggerRecheckRequired` | true |
| `invalidationRecheckRequired` | true |
| `maeRecheckRequired` | true |
| `contextContinuityCheckRequired` | true |
| `directionCollapseGuardAdded` | true |
| `confidenceCollapseReasonRequired` | true |
| `staticExpectedFollowupBehavior` | `continuation_watch_or_confirmation_pending` |
| `wouldPreventUnexplainedCollapse` | true |
| `needsNextRuntimeRegression` | true |
| `nextStep` | `P2D-R1 runtime regression` |

---

## 4. PromptRepairStatusCard

`frontend/src/components/PromptRepairStatusCard.tsx` shows all repair flags plus next runtime regression.

Embedded on **Paper Lab**. Risk Evidence shows a compact Prompt Repair Safety card. Evidence Vault shows P2C issue → P2D repair timeline.

---

## 5. Pages updated

| Page | MVP-5 change |
|------|----------------|
| Overview | P2D stage/verdict; next = P2D-R1 |
| Risk Evidence | Prompt repair safety + Stage 4.19 blocked |
| Paper Lab | PromptRepairStatusCard; awaiting runtime regression |
| Evidence | P2C issue → P2D repair timeline |
| Provider Shadow | Permanent routing still unsupported |

---

## 6. Stage 4.19 blocked display

All operator surfaces keep `stage_419_readiness=false`, `should_start_419=false`, and no start button.

---

## 7. Future public SaaS still not implemented

Membership remains **Future only / No billing / customer SaaS not implemented**.  
No billing, customer accounts, API key collection, copy trading, or managed accounts.

---

## 8. Safety checks

`python tools/research/check_nexus_ui_mvp5_safety.py` → **PASS**

Requires:

- P2D markers / `STAGE_4_18P2D_PASS`
- `PromptRepairStatusCard`
- `previous_watch_context` / direction collapse guard
- No trade / billing / ARM / Stage 4.19 start

---

## 9. Trading backend untouched

UI did not modify trading logic, provider routing defaults, Risk Governor, ARM, production, btc-auto, order APIs, billing, accounts, API keys, or Stage 4.19 gates.

---

## 10. Next UI step

After operator-gated **P2D-R1 runtime regression** confirms ETH follow-up no longer collapses without reversal / invalidation / MAE / explicit collapse reason: wire a **P2D-R1 sanitized snapshot** into Private Operator UI. Do not start Stage 4.19. Do not permanently change routing.

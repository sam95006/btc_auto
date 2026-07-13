# NEXUS / EATI UI MVP-4 — P2C Confirmation Prompt Issue Report

**Status:** Complete (read-only Private Operator P2C snapshot + confirmation prompt issue display)  
**Date:** 2026-07-13  
**Mode:** Private Operator Mode ON / SANITIZED SNAPSHOT / Research-only  
**Location:** `frontend/`  
**Safety check:** `python tools/research/check_nexus_ui_mvp4_safety.py`

---

## 1. MVP-3 recap

MVP-3 wired a sanitized **4.18-P2B** Private Operator snapshot with ETH Confirmation Timeline (LONG/BUY → NONE/NONE, `eth_followup_direction_changed`) and Stage 4.19 blocked.

MVP-4 advances to **Stage 4.18-P2C** so operators can see the failure is a **system confirmation issue**, not a market reversal.

---

## 2. P2C snapshot update

**Path:** `frontend/src/demo/snapshots/p2cPrivateOperatorSnapshot.ts`

| Field | Value |
|-------|--------|
| Source | `SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE` |
| `uiMode` | `private_operator_snapshot` |
| Latest stage | `4.18-P2C` |
| Latest verdict | `STAGE_4_18P2C_PASS` |
| BTC graduation | **3** |
| ETH valid_watch | **1** |
| ETH graduation | **0** |
| ETH blocker | `confirmation_prompt_too_strict` |
| ethDetail | `LONG/BUY → NONE/NONE without market reversal` |
| market_valid | **false** |
| system_issue | **true** |
| Context delta | price -0.127%; regime trend→trend; trend_strength 0.41→0.64; data_quality ok→ok |
| Stage 4.19 | blocked (`stage419Readiness=false`, `shouldStart419=false`) |
| Permanent routing | not supported |

Adapter prefers **P2C → P2B → P2A**.

---

## 3. Confirmation prompt issue display

`EthConfirmationTimelineCard` now shows:

- SYSTEM ISSUE / NOT MARKET REVERSAL badges
- Market Context Delta (price / regime / trend_strength / data_quality)
- `confirmation_failure_is_market_valid=false`
- `confirmation_failure_is_system_issue=true`
- Next diagnostic = **P2D confirmation prompt review**

---

## 4. Market context delta display

Shown on:

- EthConfirmationTimelineCard
- Risk Evidence system-issue card
- Evidence Vault ETH market context delta card

---

## 5. Pages updated

| Page | MVP-4 change |
|------|----------------|
| Overview | P2C stage/verdict; ETH blocker=`confirmation_prompt_too_strict` |
| Risk Evidence | System issue card; not market reversal; no MAE/invalidation breach |
| Paper Lab | ETH confirmation prompt issue; next = P2D |
| Evidence | Market context delta evidence |
| Provider Shadow | Permanent routing still unsupported |

---

## 6. Stage 4.19 blocked display

All operator surfaces keep `stage_419_readiness=false`, `should_start_419=false`, and no start button.

---

## 7. Future public SaaS still not implemented

Membership remains **Future only / No billing / customer SaaS not implemented**.  
No billing, customer accounts, API key collection, copy trading, or managed accounts.

Reference direction for a later visual upgrade (not implemented in MVP-4): market-dashboard / signal-zone patterns similar to [datahunterx.com](https://datahunterx.com/) — denser market board, anomaly priority, and signal history — while staying Private Operator / research-only first.

---

## 8. Safety checks

`python tools/research/check_nexus_ui_mvp4_safety.py` → **PASS**

---

## 9. Trading backend untouched

UI did not modify trading logic, provider routing defaults, Risk Governor, ARM, production, btc-auto, order APIs, or Stage 4.19 gates.

---

## 10. Next UI step

After backend P2D prompt repair + a small runtime regression confirming ETH follow-up no longer collapses without reversal: wire a **P2D sanitized snapshot** (prompt-repair status + expected continuation behavior) into Private Operator UI.

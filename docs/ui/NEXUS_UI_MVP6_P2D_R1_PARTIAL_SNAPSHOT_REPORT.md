# NEXUS / EATI UI MVP-6 — P2D-R1 Partial Snapshot

**Verdict:** PASS  
**Mode:** Private Operator read-only sanitized snapshot  
**Date:** 2026-07-14  
**Audience:** Internal operators / researchers only  
**Public SaaS:** Future architecture only — not implemented

---

## 1. MVP-5 recap

MVP-5 displayed Stage 4.18-P2D prompt repair status (`PromptRepairStatusCard`), prior SYSTEM ISSUE timeline, and next-step P2D-R1 runtime regression. Stage 4.19 remained blocked. No trading / routing / ARM / billing surfaces.

---

## 2. P2D-R1 snapshot update

Added:

`frontend/src/demo/snapshots/p2dR1PrivateOperatorSnapshot.ts`

- source: `SANITIZED SNAPSHOT - READ ONLY - NOT INVESTMENT ADVICE`
- latest stage: `4.18-P2D-R1`
- latest verdict: `STAGE_4_18P2D_R1_PARTIAL_NO_ETH_WATCH`
- technical_valid=true · tick=6 · effective=18 · parse=0
- BTC valid_watch=1 (last tick, no follow-up) · BTC graduation=0
- ETH valid_watch=0 · followup_cases=0 · graduation=0
- prompt_repair_runtime_present=true
- previous_watch_context_seen=false · direction_collapse_guard_seen=false
- eth_confirmation_prompt_repair_effective=false (sample insufficient)
- stage_419_readiness=false · should_start_419=false
- next: P2E ETH no-watch diagnostics + wait helper fix
- uiMode: `private_operator_snapshot`

Adapter prefers P2D-R1 over P2D/P2C/P2B/P2A.

---

## 3. RuntimeRegressionStatusCard

New component shows:

- technical PASS
- prompt repair runtime present
- ETH watch not observed
- repair not validated due sample
- BTC last-tick watch no follow-up
- Stage 4.19 blocked
- next diagnostic P2E

---

## 4. Pages updated

| Page | Update |
|------|--------|
| `/overview` | P2D-R1 latest stage/verdict · technical PASS but no ETH watch · RuntimeRegressionStatusCard |
| `/risk-evidence` | Stage 4.19 blocked · no order / no mock / no production · repair not validated |
| `/paper-lab` | BTC last-tick watch · ETH no-watch · no graduation · RuntimeRegressionStatusCard |
| `/evidence` | P2D static repair → P2D-R1 runtime insufficient sample timeline |
| `/provider-shadow` | no permanent routing change · p2dR1Summary |

---

## 5. Why repair not validated

UI mirrors backend gate language: repair is present on runtime, but ETH prior watch never occurred in the P2D-R1 sample, so collapse-guard validation could not be exercised.

---

## 6. Stage 4.19 blocked display

Shown across overview / risk / paper-lab / evidence cards. No Stage 4.19 start button.

---

## 7. Future public SaaS still not implemented

Membership page remains “Future only / customer SaaS not implemented / No billing”. No customer accounts, API key collection, copy trading, or managed accounts.

---

## 8. Safety checks

```text
python tools/research/check_nexus_ui_mvp6_safety.py
```

Checks include: SANITIZED SNAPSHOT; PARTIAL_NO_ETH_WATCH; technical PASS; no ETH watch; Stage 4.19 blocked; no secrets; no `/data` raw paths in snapshots; no billing/accounts/keys/trade/order/ARM/routing-editor/4.19-start.

---

## 9. Trading backend untouched

UI commit must not include backend trading logic, provider routing, Risk Governor, ARM, production, or btc-auto changes.

---

## 10. Next UI step

After backend P2E lands, a later MVP may surface the `sample_market_no_edge` diagnostic snapshot (still read-only). Until then, Private Operator stops at P2D-R1 PARTIAL gate display.

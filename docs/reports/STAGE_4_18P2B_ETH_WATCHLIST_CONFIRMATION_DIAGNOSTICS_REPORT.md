# Stage 4.18-P2B — ETH Watchlist Follow-up Confirmation Diagnostics

**Date:** 2026-07-13  
**Branch:** `stage3-demo-learning`  
**Mode:** Offline diagnostics only — **no 30m / 60m / routing change / Stage 4.19**  
**Source:** `/data/stage4_ai_decisions_418p2_r1_btc_cerebras_first_30m` + P2A/P2-R1 analysis  
**Output:** `/data/stage4_18p2b_eth_watchlist_confirmation_diagnostics`

---

## 1. P2-R1 recap

- Technical PASS; BTC graduation=3 (actual-only); ETH graduation=0  
- BTC Cerebras-first experiment; ETH routing unchanged  

## 2. P2A recap

- ETH valid_watch=1, follow-up available=1, confirmation_failed=1  
- Root cause class: `eth_followup_confirmation_failed`  

## 3. ETH watch candidate timeline

| Field | Watch | Follow-up |
|-------|-------|-----------|
| provider | cerebras | cerebras |
| intent | watch | **hard_skip** |
| confidence | 0.55 | **0.0** |
| directional_bias | LONG | **NONE** |
| candidate_side | BUY | **NONE** |
| entry_trigger | present | collapsed |
| invalidation | present | not breached |
| mae | 0.30 (cap passed) | not breached |

## 4. Confirmation failure reason

**`eth_followup_direction_changed`**

Detail: `Bias/side collapsed after watch (LONG/LONG -> NONE/NONE)`  
Follow-up intent=`hard_skip`, same provider (not a cross-provider flip).

Not primary: MAE/invalidation breach, provider inconsistency, missing trigger on the watch itself.

## 5. BTC success comparison

BTC had 3 Cerebras watches (avg conf ~0.56, all BUY):

- One continued watch→watch with rising confidence (0.58→0.66)  
- One watch→soft_skip on Groq follow-up still graduated via actual-only calibration path  
- Triggers were concrete (`pullback_confirm` / `price_breakout` with prices)

ETH watch quality looked comparable on the open (trigger+invalidation+MAE OK), but the **next ETH tick fully abandoned direction** (hard_skip / NONE / conf 0).

## 6. Root cause

ETH confirmation failed because the follow-up decision **dropped directional bias and side to NONE under hard_skip**, not because MAE/cap/schema fields were missing on the original watch.

## 7. Recovery recommendation

`eth_followup_market_context_or_confirmation_review`

- Review why Cerebras follow-up hard_skipped after a structured BUY watch  
- Code-only comparison of ETH vs BTC confirmation/calibration path differences  
- Optional later: operator-approved **short** sample — **not** auto 60m  

Flags: prompt/schema/state-machine fixes **not** required as first step (`needs_eth_prompt_fix=false`, `needs_eth_schema_fix=false`, `needs_followup_state_machine_review=false`).

## 8. Why 60m is not justified now

Failure is a single-watch confirmation collapse with clear classification. N-R1/N-R2 already showed ETH can graduate. Prefer targeted confirmation review before another long soak. `should_run_60m=false`.

## 9. Why Stage 4.19 remains blocked

ETH graduation still 0; need BTC+ETH actual non-shadow graduation >0.  
`stage_419_readiness=false`, `should_start_419=false`.

## 10. Safety confirmation

Offline only; no orders/ARM/radar/production/btc-auto; no permanent routing; no RG/MAE/confidence changes.

## 11. Final verdict

**`STAGE_4_18P2B_PASS`**

Stopped at gate.

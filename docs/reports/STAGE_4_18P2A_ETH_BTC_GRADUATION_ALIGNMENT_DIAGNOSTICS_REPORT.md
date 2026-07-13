# Stage 4.18-P2A — ETH+BTC Actual Graduation Alignment Diagnostics

**Date:** 2026-07-13  
**Branch:** `stage3-demo-learning`  
**Mode:** Offline diagnostics only — **no 30m / 60m / routing change / Stage 4.19**  
**Source:** `/data/stage4_ai_decisions_418p2_r1_btc_cerebras_first_30m`  
**Output:** `/data/stage4_18p2a_eth_btc_graduation_alignment`

---

## 1. P2-R1 recap

| Metric | Value |
|--------|-------|
| Technical | PASS (6 ticks, 20 effective, parse=0) |
| BTC chain | cerebras,groq (experiment) |
| BTC valid_watch / graduation | **3 / 3** (actual-only) |
| ETH graduation | **0** |
| Shadow → graduation | excluded |
| Flags reset | yes |
| Stage 4.19 | not started |

---

## 2. BTC success analysis

BTC Cerebras-first override produced actual non-shadow watches and graduations:

- `btc_actual_valid_watch_count=3`
- `btc_actual_graduation_count=3`
- Shadow excluded from paper/calibration/graduation
- ETH/SOL/PEPE routing was **not** overridden

This supports continued **experiment-mode** BTC Cerebras-first research — not permanent production routing.

---

## 3. ETH zero-graduation analysis (P2-R1)

| Metric | Value |
|--------|-------|
| ETH decisions | **6** |
| ETH valid_watch | **1** |
| ETH watchlist (paper) | **0** |
| ETH graduation | **0** |
| Provider | cerebras×4, groq×2 |
| Intent | hard_skip×3, soft_skip×2, watch×1 |
| Confidence | min 0.0 / max 0.55 / avg ~0.16 |
| Block reasons | skip_intent×5 |
| MAE above cap | **0** |
| Follow-up tick available | **1** |
| No follow-up tick | **0** |
| Confirmation failed | **1** |

**Root cause:** `eth_followup_confirmation_failed`  
**Recommendation:** `eth_watchlist_followup_diagnostics`

ETH did open one actual valid_watch, but the subsequent tick did not confirm into graduation (later intent collapsed to skip / no paper watchlist progression).

---

## 4. Comparison with previous ETH-good sessions

| Session | ETH graduations (known) | Notes |
|---------|-------------------------|-------|
| 4.18-N-R1 | **2** | ETH/Cerebras valid_watch path |
| 4.18-N-R2 | **2** | ETH valid_watch=5; BTC graduation=0 |
| 4.18-P2-R1 | **0** | ETH valid_watch=1; confirmation failed |

P2-R1 ETH provider mix remains Cerebras-heavy (4/6). This does **not** look like BTC override poisoned ETH routing. More consistent with **sample variance + weak ETH confirmation** in a short 30m window than a permanent ETH regression from P2 routing.

---

## 5. Root cause

`eth_root_cause = eth_followup_confirmation_failed`

Not primary:

- eth_no_actual_valid_watch (false — had 1)
- eth_mae_cap_failure (mae_above_cap=0)
- eth_provider_distribution_shift (still Cerebras-majority)

---

## 6. Recommendation

1. Run **ETH watchlist follow-up diagnostics / short alignment review** (offline or operator-approved short sample) — not 60m by default.  
2. Keep BTC Cerebras-first as **experiment-supported**, not permanent.  
3. Do **not** start Stage 4.19 (ETH graduation still 0).  
4. Do **not** change Risk Governor / MAE cap / confidence floor.

---

## 7. Why 60m is not automatically justified

- Root cause is confirmation failure on a single ETH watch, not systemic MAE/schema collapse.
- N-R1/N-R2 already showed ETH can graduate under normal chain.
- `should_run_60m=false` until ETH follow-up diagnostics clarify whether a short sample is enough.

---

## 8. Why Stage 4.19 remains blocked

- Requires actual non-shadow **BTC + ETH** graduation > 0
- ETH graduation = 0
- `stage_419_readiness=false`, `should_start_419=false`

---

## 9. Safety confirmation

- Offline only; no LLM / exchange private API from this tool  
- No orders / ARM / radar / production / btc-auto  
- No permanent routing change  
- No RG / MAE / confidence changes  

---

## 10. Final verdict

**`STAGE_4_18P2A_PASS`**

Diagnostics complete. Next gated step: ETH follow-up confirmation diagnostics / optional short operator-approved sample — **stop at gate**.

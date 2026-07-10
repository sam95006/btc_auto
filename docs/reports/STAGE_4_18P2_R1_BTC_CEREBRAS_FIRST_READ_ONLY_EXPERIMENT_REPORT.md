# Stage 4.18-P2-R1 — BTC Cerebras-first Read-only Routing Experiment

**Date:** 2026-07-11 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Mode:** Operator-approved 30m read-only experiment — **no permanent routing, no Stage 4.19**  
**Output:** `/data/stage4_ai_decisions_418p2_r1_btc_cerebras_first_30m`  
**Analysis:** `/data/stage4_18p2_r1_analysis`

---

## 1. P2 design recap

P2 design gate (`204098a`) recommended **Option 2**: BTC Cerebras-first read-only experiment when:

- `STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED=true`
- `STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED=true`
- `STAGE4_BTC_PROVIDER_CHAIN=cerebras,groq`

Default-off; BTC-only; no orders; no production routing change.

---

## 2. Runtime safety gate

| Check | Result |
|-------|--------|
| `/health` preflight | 200 |
| DRY before run | 0 |
| Override default off | true |
| Override code present (`resolve_provider_chain_for_symbol`) | true |
| Order / mock / ARM / radar / production | false / off |
| Stage 4.19 | not started |

---

## 3. Provider override confirmation

During run:

- `experiment_mode=true`
- `btc_provider_override_active=true`
- BTC `provider_chain=['cerebras','groq']`
- ETH/SOL/PEPE remained on normal `['groq','cerebras']` (`eth_sol_pepe_routing_unchanged=true`)

---

## 4. 30m technical result

| Metric | Value |
|--------|-------|
| tick_count | **6** |
| effective_decision_count | **20** |
| parse_error_count | **0** |
| validator | PASS (paper_ready_watch=5 overall) |
| mock_ai_used_count | **0** |
| order_sent_count | **0** |
| provider_success_distribution | cerebras=13, groq=7 |
| technical_valid | **true** |

---

## 5. BTC actual provider distribution

| Provider | BTC decisions |
|----------|---------------|
| cerebras | **3** |
| groq | **2** (fallback after primary) |

`cerebras_first_observed=true` (chain primary = cerebras on all BTC rows).

---

## 6. BTC actual valid_watch / graduation

| Metric | Value |
|--------|-------|
| BTC intent | watch×3, soft_skip×2 |
| BTC actual valid_watch | **3** |
| BTC watchlist | **3** |
| BTC actual graduation (actual-only calibration / followup) | **3** |
| Shadow used for graduation | **false** |

---

## 7. ETH actual graduation status

| Metric | Value |
|--------|-------|
| ETH actual graduation | **0** |

---

## 8. Actual-only paper / calibration

- Paper logger: actual-only (`/data/stage4_paper_events_418p2_r1_actual_only`)
- Calibration replay: actual-only
- Shadow excluded from paper / calibration / graduation
- Note: calibration helper may emit internal `stage_419_readiness=true` when BTC graduates; **operator gate forces `stage_419_readiness=false` / `should_start_419=false`** until ETH also graduates and operator approves.

---

## 9. Why Stage 4.19 remains blocked

- ETH graduation = 0
- Stage 4.19 requires actual non-shadow **BTC + ETH** graduation > 0
- No auto-start
- `routing_auto_change_allowed=false`

---

## 10. Flags reset confirmation

| Flag | After reset |
|------|-------------|
| `STAGE4_CLOUD_DRY_RUN_MINUTES` | **0** |
| `STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED` | **false** |
| `STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED` | **false** |
| `STAGE4_BTC_PROVIDER_CHAIN` | empty |
| `/health` | **200** |

---

## 11. Safety confirmation

- order=0, mock=0  
- no demo/paper execution  
- no ARM / radar / production / btc-auto  
- no Risk Governor / MAE / confidence floor changes  
- no permanent routing change  

---

## 12. Final verdict

**`STAGE_4_18P2_R1_PARTIAL_BTC_ONLY`**

Technical PASS + Cerebras-first BTC path produced actual non-shadow valid_watch and BTC graduation, but ETH graduation remains 0.

---

## 13. Next step recommendation

1. **Do not** start Stage 4.19.  
2. **Do not** make Cerebras-first permanent production routing.  
3. Next gated step: **ETH + BTC actual graduation alignment** (read-only), or operator-approved follow-up sample focused on ETH yield under current chain — still no 60m auto, no 4.19.

**Stopped at gate.**

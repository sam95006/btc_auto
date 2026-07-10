# Stage 4.18-P2 Provider Routing Design Gate Report

**Verdict:** `STAGE_4_18P2_PASS`  
**Mode:** Design-only (no routing enable, no soak, no Stage 4.19)

---

## 1. P1C clean shadow evidence

| Metric | Value |
|--------|-------|
| Technical | PASS (6/6 ticks, 23 effective, parse=0) |
| Actual BTC provider | Groq ×6 |
| Actual BTC intents | 6/6 soft_skip |
| Actual BTC valid_watch | **0** |
| Shadow BTC provider | Cerebras ×6 |
| Shadow BTC valid_watch | **5** |
| Comparable pairs | 5 |
| Uncomparable | 1 (truncation only) |
| `provider_skill_comparison_valid` | **true** |
| Shadow → paper/calibration/graduation/4.19 | **excluded** |
| Actual-only graduations | 0 |
| `stage_419_readiness` | false |

P1C shows a clean, quota-aware sample where Cerebras shadow BTC watch yield is materially higher than the actual Groq path.

---

## 2. Why a routing experiment is supported

- Skill comparison is valid (comparable pairs dominate; uncomparable is truncation-only).
- Shadow yield advantage is directional and BTC-specific.
- This is enough evidence to **design** an operator-approved, read-only P2-R1 experiment.

---

## 3. Why production routing change is not supported

- Shadow is diagnostic-only and must never graduate.
- No actual non-shadow BTC graduation exists yet.
- Auto-changing live provider preference would bypass governance.
- `routing_auto_change_allowed = false`.

---

## 4. Why Stage 4.19 remains blocked

- Stage 4.19 requires actual non-shadow BTC **and** ETH graduation > 0.
- P1C actual BTC valid_watch = 0; graduations = 0.
- Shadow watches do not count.
- `stage_419_readiness = false`; `should_start_419 = false`.

---

## 5. Design options

| Option | Summary | Recommended |
|--------|---------|-------------|
| **1** Status quo baseline | Keep groq,cerebras; safest; may leave BTC on Groq soft_skip | No |
| **2** BTC Cerebras-first read-only experiment | Flag-gated BTC chain `cerebras,groq`; ETH/SOL/PEPE unchanged | **Yes** |
| **3** Symbol-balanced rotation | Tick/symbol rotation; removes slot bias; complex RL mgmt | No |
| **4** Dual-decision arbitration | Both providers; agree-to-watch only; costly / conservative | No |

---

## 6. Recommended option

`recommended_option = option_2_btc_cerebras_first_read_only_experiment`

**Why:** P1C clean sample (Cerebras shadow valid_watch=5 vs Groq actual=0) justifies a **read-only** experiment design — not production routing.

**Limits:**
- Design P2-R1 only; do not auto-execute.
- P2-R1 must not place orders or start Stage 4.19.
- Only actual non-shadow BTC graduation may feed later gates.
- P1C shadow results must not count as graduation.

---

## 7. P2-R1 experiment design (not executed)

**Stage 4.18-P2-R1:** BTC Cerebras-first Read-only Routing Experiment

**Env (operator-approved only):**
```
STAGE4_PROVIDER_ROUTING_EXPERIMENT_ENABLED=true
STAGE4_BTC_PROVIDER_OVERRIDE_ENABLED=true
STAGE4_BTC_PROVIDER_CHAIN=cerebras,groq
STAGE4_ORDER_ALLOWED=false
STAGE4_DRY_RUN_ONLY=true
STAGE4_ALLOW_MOCK_FALLBACK=false
STAGE4_REQUIRE_REAL_LLM=true
NEXUS_ARM_ALLOWED=false
NEXUS_RADAR_AUTO_TRADE=0
ZEABUR_PRODUCTION_RUNNER_ALLOWED=false
```

**Output dir:** `/data/stage4_ai_decisions_418p2_r1_btc_cerebras_first_30m`

**Success criteria:** technical PASS; actual BTC Cerebras-first; actual BTC valid_watch > 0; graduation from non-shadow only; order=0; mock=0; flags reset; Stage 4.19 not auto-started.

**This gate does not run P2-R1.**

---

## 8. Safety guards

1. Env flags default off  
2. Override only when experiment flag = true  
3. Override limited to BTCUSDT  
4. No order path  
5. No production path  
6. No ARM path  
7. No Risk Governor threshold changes  
8. No MAE cap changes  
9. No confidence floor changes  
10. Summaries label `experiment_mode=true`  
11. Reset flags after run  
12. Stage 4.19 readiness never auto-starts  

---

## 9. Operator approval requirement

`operator_approval_required = true`  
No automatic routing change. No automatic P2-R1 soak.

---

## 10. Final verdict

**`STAGE_4_18P2_PASS`**

- Routing experiment design supported.
- Production routing change not supported.
- Stage 4.19 remains blocked.
- Next step (manual): operator-approved **4.18-P2-R1** only when explicitly requested.

**Stopped at gate.**

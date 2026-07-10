# Stage 4.18-P1A — BTC Shadow Paired-Comparison Export

**Date:** 2026-07-10 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Mode:** offline export only — **no LLM, no soak, no routing change, no orders**  
**Input:** `/data/stage4_ai_decisions_418p1_r1_btc_shadow_30m`  
**Output:** `/data/stage4_18p1a_btc_shadow_pair_compare`

---

## 1. P1-R1 summary

| Metric | Value |
|--------|-------|
| Verdict | `STAGE_4_18P1_R1_PASS` |
| ticks / effective | 6 / 20 |
| shadow rows | 6 |
| `btc_shadow_valid_watch_count` | 0 |
| `actual_btc_valid_watch_count` | 1 |
| graduations (BTC/ETH/total) | 0 / 0 / 0 |
| Stage 4.19 | blocked |

Shadow isolation worked; opposite-provider shadow did **not** beat actual path on yield.

---

## 2. Actual vs shadow paired comparison

| Metric | Value |
|--------|-------|
| `pair_count` | **6** |
| `actual_valid_watch_count` | **1** |
| `shadow_valid_watch_count` | **0** |
| `actual_graduation_count` | **0** |
| `shadow_graduation_count` | **0** (by design) |
| `divergence_count` | **5** |
| `shadow_unknown_intent_count` | **4** |
| `actual_watch_shadow_not_watch_count` | **1** |
| `shadow_watch_actual_not_watch_count` | **0** |
| `actual_provider_distribution` | groq=1, cerebras=5 |
| `shadow_provider_distribution` | cerebras=1, groq=5 |

### Per-tick pairs

| tick | actual | shadow | valid(a/s) | why_shadow |
|------|--------|--------|------------|------------|
| 1 | groq / soft_skip | cerebras / watch | F/F | `shadow_provider_error:provider_response_truncated` |
| 2 | cerebras / soft_skip | groq / unknown | F/F | `shadow_provider_error:tokens` |
| 3 | cerebras / soft_skip | groq / unknown | F/F | `shadow_provider_error:tokens` |
| 4 | cerebras / soft_skip | groq / unknown | F/F | `shadow_provider_error:tokens` |
| 5 | cerebras / soft_skip | groq / soft_skip | F/F | `shadow_intent_soft_skip` |
| 6 | cerebras / **watch** | groq / unknown | **T**/F | `shadow_provider_error:tokens` |

---

## 3. Shadow valid_watch=0 root cause

**Primary cause: opposite-provider call failures / quota — not MAE/side/trigger field contract.**

`why_shadow_not_valid_watch_counts`:

| Reason | Count |
|--------|------:|
| `shadow_provider_error:tokens` | 4 |
| `shadow_provider_error:provider_response_truncated` | 1 |
| `shadow_intent_soft_skip` | 1 |

Answers to analysis questions:

1. **Why shadow valid_watch=0?** 4/6 Groq shadow calls hit TPM/`tokens`; 1 Cerebras shadow returned watch but was truncated (incomplete fields); 1 soft_skip.
2. **Unknown intent?** Yes — **4/6** shadow intents are `unknown`, driven by provider errors (counted before field checks).
3. **Missing side/trigger/invalidation/MAE?** Not the dominant failure mode in this sample; errors short-circuit before field scoring.
4. **MAE above cap?** No evidence as primary cause.
5. **Confidence too low?** Not the primary cause.

**Structural insight:** When actual path already fell back to Cerebras (Groq rate-limited), shadow’s “opposite” provider is **Groq** — which is still exhausted. Shadow therefore often cannot produce a fair quality comparison; it measures quota collision more than provider skill.

---

## 4. Actual BTC valid_watch=1 but graduation=0

- Tick 6: actual Cerebras `watch` → **valid_watch=true**.
- Calibration replay on actual-only paper events: **0 graduations** (watchlist created but not confirmed/graduated).
- `why_actual_not_graduated` for that pair: `watchlist_followup_no_graduation`.

So the BTC yield gap to Stage 4.19 is **follow-up / confirmation**, not “no BTC watch ever.”

---

## 5. Is P2 routing justified?

| Gate | Result |
|------|--------|
| `routing_change_supported` | **false** |
| `p2_routing_experiment_recommended` | **false** |
| `shadow_watch_actual_not_watch_count` | 0 |

**No.** Shadow did not produce any valid_watch advantage. Case 2/3 not met. Do **not** design or enable P2 routing.

---

## 6. Is another soak justified?

| Gate | Result |
|------|--------|
| `should_run_another_60m` | **false** |

**No 60m.** Case 1 applies: fix shadow provider parse/quota behavior before collecting more shadow samples. Another soak would mostly re-hit Groq TPM on the opposite path.

---

## 7. Is Stage 4.19 ready?

| Gate | Result |
|------|--------|
| `stage_419_readiness` | **false** |
| `should_start_419` | **false** |
| BTC + ETH graduations | 0 |

**No.** Stage 4.19 remains blocked.

---

## 8. Safety confirmation

| Guard | Status |
|-------|--------|
| LLM called by P1A tool | false |
| Exchange private API | false |
| Orders / demo / paper execution | false |
| ARM / radar / production / btc-auto | not touched |
| Shadow into paper/calibration/graduation/4.19 | excluded |
| Routing / MAE cap / confidence floor | unchanged |

---

## Recommendation

**Primary:** `fix_shadow_provider_parse_or_prompt_before_more_shadow_samples`

Focus on making opposite-provider shadow calls succeed when Groq is in TPM cooldown (e.g. shadow skip-if-quota, or shadow-only Cerebras when actual already used Cerebras due to Groq 429 — design only, not implemented here).

**Secondary (Case 4):** `analyze_btc_watchlist_followup_failure` for the one actual BTC valid_watch that did not graduate.

**Stop at gate.** No P2. No 60m. No Stage 4.19.

---

## Final verdict

**`STAGE_4_18P1A_PASS`**

# Stage 4.18-P1B — Quota-Aware Shadow Call + BTC Watchlist Follow-up Diagnostics

**Date:** 2026-07-10 (UTC+8)  
**Branch:** `stage3-demo-learning`  
**Mode:** code fix + offline replay only — **no soak, no P2 routing, no Stage 4.19**

---

## 1. P1A summary

| Metric | Value |
|--------|-------|
| Verdict | `STAGE_4_18P1A_PASS` |
| pair_count | 6 |
| shadow_valid_watch | 0 |
| actual_btc_valid_watch | 1 |
| Root cause (P1A) | quota collision / truncation — not provider skill |

---

## 2. Why P2 routing is not supported

Offline P1B reclassification of the same P1-R1 rows:

| Metric | Value |
|--------|------:|
| `shadow_comparable_pair_count` | **1** |
| `shadow_uncomparable_pair_count` | **5** |
| `provider_skill_comparison_valid` | **false** |
| `routing_change_supported` | **false** |
| `p2_routing_experiment_recommended` | **false** |

With only **1** comparable pair, provider skill cannot be judged. P2 remains blocked.

---

## 3. Quota-aware shadow fix

Implemented in:

- `stage4_btc_dual_provider_shadow.py`
- `stage4_provider_quota_governor.py`
- `stage4_provider_chain.py` (`shadow_groq_call_blocked_reason`)

Behavior:

1. If actual `fallback_reason=groq_rate_limited` → shadow **does not** hard-call Groq; writes `shadow_call_skipped=true`, `shadow_skip_reason=actual_fallback_groq_rate_limited`, intent=`not_called`.
2. If Groq TPM governor cooldown active → same skip with `groq_tpm_cooldown_active`.
3. Skipped / token / truncated / unknown rows are **excluded** from provider skill comparison.
4. Actual decision path and provider routing unchanged.

---

## 4. Shadow uncomparable classification

New outcome classes:

- `shadow_call_skipped`
- `shadow_provider_unavailable`
- `shadow_provider_rate_limited`
- `shadow_provider_token_limited`
- `shadow_provider_response_truncated`
- `shadow_parse_unknown_intent`
- `shadow_valid_decision_but_not_watch`
- `shadow_valid_watch`

P1-R1 offline reclass (`/data/stage4_18p1b_btc_shadow_pair_compare`):

| Reason | Count |
|--------|------:|
| `shadow_provider_token_limited` | 4 |
| `shadow_provider_response_truncated` | 1 |
| comparable soft_skip | 1 |

Note: historical rows still show `shadow_call_skipped_count=0` because P1-R1 hard-called Groq before this fix. Future runs will skip instead of colliding.

---

## 5–6. Comparable pair count / skill validity

| Field | Value |
|-------|-------|
| `shadow_total_rows` | 6 |
| `shadow_called_count` | 6 (historical) |
| `shadow_call_skipped_count` | 0 (historical; fix applies going forward) |
| `shadow_comparable_pair_count` | **1** |
| `shadow_uncomparable_pair_count` | **5** |
| `provider_skill_comparison_valid` | **false** |

---

## 7. BTC actual valid_watch follow-up

Output: `/data/stage4_18p1b_btc_watchlist_followup_diagnostics`

| Field | Value |
|-------|-------|
| `btc_actual_valid_watch_count` | 1 |
| `btc_graduation_count` | 0 |
| `followup_tick_available` | **false** |
| `no_consecutive_confirmation` | true |
| `reason_no_graduation` | `watchlist_opened_but_no_followup_tick` |
| `recommendation` | `need_longer_sample_for_btc_watchlist_followup` |

The sole BTC valid_watch landed on the **last tick** of the 30m window, so confirmation/graduation could not occur inside that sample.

---

## 8. Are more clean shadow samples justified later?

**Yes, later — after this quota-aware fix is live in a future approved sample.**  
Not now as a 60m soak. Recommendation path:

1. Deploy/use quota-aware shadow skip.
2. Collect a short clean shadow sample when Groq is not in TPM collision with opposite calls.
3. Only then re-evaluate provider skill.

---

## 9. Why 60m is not justified now

- Skill comparison still invalid on existing evidence.
- Need clean comparable pairs first, not a longer polluted soak.
- `should_run_another_60m=false`.

---

## 10. Why Stage 4.19 remains blocked

- BTC graduation = 0, ETH graduation = 0 in this sample path.
- `stage_419_readiness=false`.
- Shadow never feeds 4.19 readiness.

---

## 11. Safety confirmation

| Guard | Status |
|-------|--------|
| Actual routing unchanged | yes |
| Shadow excluded from paper/calibration/graduation/4.19 | yes |
| Orders / demo / paper execution | none |
| ARM / radar / production / btc-auto | untouched |
| Exchange private API | not called by P1B tools |
| Soak | not run |

---

## Cerebras truncation retry (shadow-only)

If Cerebras shadow returns truncated: one compact-prompt retry using `STAGE4_CEREBRAS_RETRY_MAX_TOKENS`.  
Retry never writes `ai_decisions.jsonl` and never enters paper/calibration/graduation.

---

## Final verdict

**`STAGE_4_18P1B_PASS`**

**Next step recommendation:**  
Stop at gate. Prefer a **future short clean shadow sample** under quota-aware skip; in parallel, BTC watchlist follow-up needs a sample where the valid_watch is **not** on the final tick. **No P2. No 60m now. No Stage 4.19.**

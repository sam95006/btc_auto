# Stage 4.12c — Provider Yield + Shadow Quality Review

**Date:** 2026-06-30  
**Scope:** Read-only diagnosis of Stage 4.12b (`/data/stage4_ai_decisions_412b_180m`)  
**Verdict:** Root causes identified; **Cerebras fix implemented locally**; **Groq TPM pressure confirmed**; **no soak rerun this round**

---

## Executive Summary

| Area | Finding | Action |
|------|---------|--------|
| Cerebras fallback 0/14 | **HTTP 400** — `max_tokens` + `max_completion_tokens` sent together (`wrong_api_format`) | Fixed in `stage4_llm_client.py` (Cerebras uses `max_tokens` only) |
| Groq 429 (14 ticks) | **TPM token quota** (`last_error_type=tokens`, rate limit after ~22 successes) | Prompt compression + lower `max_tokens`; optional dual-provider after Cerebras deploy |
| Shadow quality | 5× `bad_watch` (watch + high MAE), 1× `missed_opportunity` (hard_skip + rally) | Calibration review; no strategy/order changes |
| Dataset | 22/36 effective (PARTIAL) | Retry only after Cerebras fix deployed + token budget validated |

**Do not:** demo order, ARM, radar, Stage 4.13 fleet expansion until 4.12b-retry ≥30/36.

---

## 1. Cerebras Fallback Diagnosis (0% success)

### 1.1 Evidence from 412b `llm_client_debug.jsonl`

All **14** Cerebras attempts during soak returned **HTTP 400**:

```text
error_message_safe: Setting "max_tokens" and "max_completion_tokens" at the same time is not supported.
error_type: wrong_api_format / http_400
model: gpt-oss-120b
base_url: https://api.cerebras.ai/v1/chat/completions
Authorization: Bearer [present — not a key issue]
```

**Root cause:** Stage 4 `_openai_compat()` used the legacy OpenAI-shaped payload for non-Groq providers, duplicating `max_tokens` and `max_completion_tokens` (700 each). Groq was already fixed in 4.12a-5; Cerebras was not.

### 1.2 Payload matrix (local probe, `check_cerebras_auth_minimal.py`)

| Variant | HTTP | Valid JSON |
|---------|------|------------|
| A bare_chat | 200 | — |
| B json_object | 200 | yes |
| C json_schema strict=false | 200 | yes |
| D json_schema strict=true | 200 | yes |
| E stage4_style (max_tokens only) | 200 | yes* |

\*Probe user message minimal; production decisions parse OK when HTTP 200.

```text
cerebras_direct_success=true
cerebras_stage4_style_success=true
cerebras_valid_json=true (json_object mode)
cerebras_error_root_cause (412b soak): max_completion_tokens_conflict
cerebras_error_root_cause (post-fix): resolved_stage4_json_object_without_max_completion_tokens
```

Cerebras **supports** `json_object` and even `json_schema` on `gpt-oss-120b` — unlike Groq.

### 1.3 Code fix (minimal)

`stage4_llm_client.py` now routes Cerebras through `build_stage4_cerebras_openai_payload()` — `json_object`, **`max_tokens` only**.

---

## 2. Groq 429 Token Quota Diagnosis

### 2.1 Soak metrics (412b summary)

```text
groq_429_count=14
groq_success_count=22
groq_attempt_count=36
groq_429_first_tick≈23 (first provider_chain_failed streak after tick 22 success)
groq_429_last_tick=36
groq_keys status at end: both rate_limited_429, last_error_type=tokens
```

### 2.2 Classification

```text
groq_429_root_cause=TPM token quota (tokens per minute)
```

Not RPM-only (requests continued on schedule). Not auth. Pattern: **22 consecutive Groq successes**, then **14 skipped ticks** where Groq 429’d and Cerebras 400’d — zero fallback yield.

### 2.3 Token budget estimates

From prompt rebuild (representative ETHUSDT decision structure):

| Field | Estimate |
|-------|----------|
| system_prompt_chars | ~1,663 |
| total_prompt_chars (sample) | ~3,700–7,000+ with full Stage3 |
| estimated_prompt_tokens | **~925–1,750** per tick |
| NEXUS_LLM_MAX_COMPLETION_TOKENS | **700** (configured ceiling) |
| estimated_output_tokens (observed) | ~100–200 typical JSON response |
| **average_tokens_per_decision** | **~1,100–1,625** (input + output) |
| **max_tokens_per_decision** | **~1,625+** (input + 700 cap) |
| **estimated_tokens_before_first_429** | **~24,000–36,000** cumulative over ~110 min |

At 5‑minute polling, Groq TPM rolling window likely exceeded after ~20+ full-size calls. **700 max_completion_tokens** inflates worst-case TPM even when outputs are small.

---

## 3. Prompt Token Budget Review

### 3.1 Character breakdown (sample)

```text
system_prompt_chars≈1663
user_prompt_chars≈2037 (varies with Stage3 payload)
stage3_context_chars≈variable (5 trades + 5 reflections + 5 patches in 412b)
market_context_chars≈400-800
active_patches_chars≈500-1500
recent_reflections_chars≈800-2000
estimated_prompt_tokens≈925-1750
estimated_output_tokens≈100-700 (cap 700)
```

### 3.2 Low-risk compression recommendations (not implemented this round)

1. **active_patches:** top 3 only  
2. **reflections:** most recent 3  
3. **stage3 trades:** most recent 3–5  
4. **market_context:** keep regime, trend_15m, volatility, 24h change; drop redundant fields  
5. **Remove duplicate schema** text in user `instructions` (already in SYSTEM_PROMPT)  
6. **Lower `NEXUS_LLM_MAX_COMPLETION_TOKENS`** to **400–500** for dry-run skip-heavy JSON  
7. **Groq:** keep `json_object`, no `json_schema`  
8. **Cerebras:** `max_tokens` only (fix deployed in code)

---

## 4. Shadow Quality Review

Distribution (21 compared): `neutral:8`, `reasonable_watch:3`, `bad_watch:5`, `good_skip:4`, `missed_opportunity:1`, `insufficient_future_data:1`

### 4.1 bad_watch (5) — common pattern

| Tick | Time (UTC) | Intent | Conf | Regime | 60m ret | MAE 60m | Reason |
|------|------------|--------|------|--------|---------|---------|--------|
| 4 | 02:55:57 | watch | 0.52 | trend | -0.31% | 0.42% | Adverse excursion dominated |
| 6 | 03:06:00 | watch | 0.52 | trend | -0.49% | 0.50% | Adverse excursion dominated |
| 8 | 03:16:03 | watch | 0.52 | trend | -0.47% | 0.84% | Adverse excursion dominated |
| 9 | 03:21:04 | watch | 0.52 | trend | -0.63% | 1.00% | Adverse excursion dominated |
| 10 | 03:26:06 | watch | 0.52 | trend | -0.29% | 0.78% | Adverse excursion dominated |

**bad_watch_root_cause:**

- **Confidence stuck at 0.52** for `watch` in a **downtrending / volatile** ETH window — upper watch band (0.30–0.55) but price moved adversely.  
- **Regime `trend`** label did not distinguish bearish drift; watch labels too optimistic for short-side risk.  
- Stage3 patch/reflection awareness **present** but did not tighten confidence.  
- Not an execution issue (all `order_sent=false`).

### 4.2 missed_opportunity (1)

| Tick | Time (UTC) | Intent | Conf | Regime | 60m ret | MFE 60m | MAE 60m |
|------|------------|--------|------|--------|---------|---------|---------|
| 19 | 04:11:18 | hard_skip | 0.05 | trend | **+0.48%** | 0.63% | -0.12% |

**missed_opportunity_root_cause:**

- `hard_skip` at **0.05 confidence** during later soak window; ETH rallied ~0.48% in 60m.  
- Likely **over-throttled** after volatile prior period / conservative skip bias.  
- Single sample — not enough to change strategy; flag for next soak review.

### 4.3 good_skip (4) / reasonable_watch (3)

Generally aligned: skips in adverse drift, watches with muted 60m moves. No action required beyond continued sampling.

---

## 5. Retry Plans (do not execute until Cerebras fix deployed to Zeabur)

### Plan A — Recommended if Cerebras fix deployed + prompt trim

```text
duration_minutes=180
poll_interval_seconds=300
max_ticks=36
target_effective_decision_count=30
STAGE4_LLM_PROVIDER_CHAIN=groq,cerebras
prompt_compression=top3 patches/reflections, max_tokens=450-500
```

**Expected:** Groq ~18–24 decisions + Cerebras fallback ~6–12 → **≥30** combined.

### Plan B — Lower frequency, longer window (only if Plan A still TPM-limited)

```text
duration_minutes=360
poll_interval_seconds=600
max_ticks=36
target_effective_decision_count=30
```

**Do NOT use** `poll=600s + duration=180m` (max 18 ticks — cannot reach 30).

---

## 6. Next Steps

1. **Deploy** `stage4_llm_client.py` + diagnostic tools to Zeabur (`nexus-stage3-bybit-demo-learning`).  
2. **Re-run** `check_cerebras_auth_minimal.py --matrix` on cloud → confirm `cerebras_stage4_style_success=true`.  
3. **Optional:** apply prompt compression config (env-only caps, no strategy rewrite).  
4. **Stage 4.12b-retry / 4.12d:** Plan A soak — only if preflight capacity PASS.  
5. **Do not** enter Stage 4.13 (BTC/ETH/SOL/PEPE) until **≥30/36** effective decisions.

---

## 7. Safety Confirmation

```text
mock_ai_used_count=0
order_sent_count=0
parse_error_count=0
debug_log_has_api_key=false
any_trading_action_sent=false
production_service_touched=false
btc_auto_touched=false
no 180m soak this round
```

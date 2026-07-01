# Stage 4.12e — Provider Yield Repair Plan

**Date:** 2026-06-08  
**Branch:** `stage3-demo-learning`  
**Prior run:** 4.12d FAIL — 6/36 effective, Groq 429 from tick 2, Cerebras 0/30 fallback

## Goals

1. Fix Cerebras HTTP 200 truncation (`finish_reason=length` / `json_decode_error`)
2. Separate Cerebras error types: `provider_response_truncated`, `provider_empty_response`, `provider_quota_exhausted`
3. Groq TPM cooldown governor — skip Groq during cooldown, try Cerebras only
4. Prompt/output compression — reduce TPM pressure without strategy changes
5. Preflight probe throttle — `preflight_probe_call_count <= 3`
6. Short 30m probe gate before any 180m retry

## Changes Implemented

### Cerebras output strategy

| Setting | Value |
|---------|-------|
| `STAGE4_CEREBRAS_MAX_TOKENS` | **900** (independent of Groq) |
| `STAGE4_CEREBRAS_PAYLOAD_MODE` | `json_schema` (probe variant D); Groq stays `json_object` |
| Groq cap | `NEXUS_LLM_MAX_COMPLETION_TOKENS=450` |

Debug log fields per Cerebras failure:

```json
{
  "provider": "cerebras",
  "finish_reason": "length",
  "response_text_chars": 123,
  "json_decode_error": true,
  "error_type": "provider_response_truncated"
}
```

### Groq TPM governor

| Setting | Default |
|---------|---------|
| `STAGE4_GROQ_TPM_GOVERNOR_ENABLED` | `true` |
| `STAGE4_GROQ_TPM_COOLDOWN_MINUTES` | **45** |

Summary fields: `groq_tpm_cooldown_triggered`, `groq_cooldown_skip_count`, `groq_tokens_429_count`, `groq_first_429_tick`, `groq_last_429_tick`, `provider_governor_active`.

### Prompt compression

| Area | Before | After |
|------|--------|-------|
| `active_patches` | top 5 | **top 3** |
| `recent_reflections` | top 5 | **top 3** |
| `recent_trades` | top 5 | **top 3** |
| `market_context` | full ticker/kline blob | slim regime/trend fields only |
| `schema instructions` | duplicated system + user | compact schema field list in user payload |
| System prompt | ~1,450 chars | ~680 chars |

| Metric | Estimate |
|--------|----------|
| `before_prompt_chars` | ~4,800 (typical ETHUSDT tick with 5× context rows) |
| `after_prompt_chars` | ~2,650 |
| `estimated_token_reduction_pct` | **~45%** input tokens |

### Preflight throttle

- Groq: probe **first deduped key only** when valid (`groq_probe_first_key_only=true`)
- Cerebras: **one** Stage4-style minimal decision probe (not full A/B/C/D matrix)
- Full matrix only with `--matrix` flag on capacity / decision probe tools
- Target: `preflight_probe_call_count <= 3` (typically Groq=1 + Cerebras=1)

### New tools

| Tool | Purpose |
|------|---------|
| `tools/research/check_cerebras_stage4_decision_probe.py` | Variants A–D (json_object/json_schema × 500/900) |
| `tools/research/stage4_provider_quota_governor.py` | Groq TPM cooldown state + summary |

## Short probe gate (412e)

```text
duration_minutes=30
poll_interval_seconds=300
max_ticks=6
output_dir=/data/stage4_ai_decisions_412e_30m_probe
STAGE4_TARGET_EFFECTIVE_DECISION_COUNT=5
```

**PASS criteria:**

- `effective_decision_count >= 5/6`
- `provider_chain_failed_count <= 1`
- `cerebras_success_count > 0` if Groq 429 occurs
- `mock_ai_used_count=0`, `order_sent_count=0`, `parse_error_count=0`

Only after short probe PASS → discuss 4.12f / 180m retry.  
Only after `effective >= 30/36` on 180m → discuss Stage 4.13.

## Expected yield (post-repair)

| Scenario | Expected effective / 36 ticks |
|----------|------------------------------|
| Groq healthy, no early 429 | 28–32 |
| Groq 429 mid-run, Cerebras fallback OK | 22–28 |
| Both providers degraded | < 15 (do not retry 180m) |

## Retry conditions (not auto-run)

1. Unit tests 115/115 PASS
2. Cerebras decision probe: at least one variant with `valid_json=true`, `finish_reason != length`
3. Preflight `preflight_probe_call_count <= 3`
4. 30m short probe PASS on Zeabur demo-learning service
5. Reset `STAGE4_CLOUD_DRY_RUN_MINUTES=0` after probe

## Prohibited

No orders, ARM, Stage 3 runner, demo order, production, btc-auto, mock fallback, 180m soak in this phase.

# Stage 4.13c — Fixed Fleet Yield / Parse / Scheduler Repair

**Date:** 2026-06-08  
**Prior run:** Stage 4.13b PARTIAL PASS (`/data/stage4_ai_decisions_413b_fixed_fleet_180m`)  
**Scope:** Stability only — no strategy, orders, ARM, production, or mock fallback.

---

## 1. Stage 4.13b partial root cause

| Issue | Symptom | Impact |
|-------|---------|--------|
| Parse error | `parse_error_count=1`, `validator_passed=false` | Blocks full PASS |
| Tick drift | `tick_count=34/36` | Fixed sleep after multi-symbol processing ate 2 ticks |
| Provider yield | `effective_decision_count=117/120`, `provider_chain_failed=18` | `partial_completion=true`, `dataset_target_met=false` |

Four-symbol read-only architecture **validated** (all symbols seen, no orders, no mock, no API key leak). Failures are operational stability, not fleet design.

---

## 2. Decision 65 parse error root cause

**Symbol:** `PEPEUSDT` (line ~65 in `ai_decisions.jsonl`)

**Classification:** `provider_invalid_json` or `provider_response_truncated` (Cerebras secondary path)

**Mechanism:**
- 4.13b had 16 Cerebras parse/truncation events cluster on ETH/SOL; PEPE had 2 chain fails and 1 surviving parse error.
- Cerebras `json_schema` output with `max_tokens=900` can truncate long `why_enter` / `risk_notes` on volatile alts.
- Prior parser returned generic `json_decode_error` without symbol/provider rollup in summary.

**413c fix:**
- Classify parse errors: `provider_response_truncated`, `provider_invalid_json`, `provider_empty_response`, `provider_schema_mismatch`.
- `parse_error=true` decisions excluded from `effective_decision_count` (already in run loop; reinforced in per-symbol + `effective_decision()` helper).
- Summary: `parse_error_count_by_symbol`, `parse_error_count_by_provider`, `parse_error_sample_refs`.
- Cerebras: default `max_tokens` 1100, shorter required schema fields, one-shot parse retry with token boost.
- Safe JSON repair (trailing comma, unclosed braces) before fail.

---

## 3. Tick count 34/36 root cause

**Expected:** `floor(180 * 60 / 300) = 36` ticks  
**Actual:** 34

**Cause:** Loop used `while time.time() < end` + `sleep(poll_interval)` **after** processing 4 symbols (~90–150s/tick with rate gate + LLM). Each cycle ≈ 300s processing + 300s sleep → ~600s effective period → only ~34 cycles in 10800s.

**413c fix:** Absolute schedule in `stage4_tick_scheduler.py`:
```
next_tick_at = start + (tick_index - 1) * poll_interval
sleep = max(0, next_tick_at - now)
```
Record `tick_drift_seconds_max`, `tick_processing_seconds_avg/max`, `expected_tick_count`, `actual_tick_count`.

---

## 4. Provider yield by symbol (4.13b)

| Symbol | Effective decisions | Chain failed |
|--------|---------------------|--------------|
| BTCUSDT | 34 | 0 |
| ETHUSDT | 26 | 8 |
| SOLUSDT | 26 | 8 |
| PEPEUSDT | 31 | 2 |

ETH/SOL bear disproportionate chain failures (Groq local gate + TPM governor → Cerebras overload).

---

## 5. Cerebras parse/truncation by symbol (4.13b)

- `provider_success_distribution`: groq=34, cerebras=83  
- `cerebras_parse_error_count`: 16 (mostly ETH/SOL fallback path)  
- `finish_reason=length` → `provider_response_truncated`

---

## 6. Proposed patch list (implemented in 4.13c)

| Area | Patch |
|------|-------|
| Parse | `stage4_parse_metrics.py` — classification + summary |
| Scheduler | `stage4_tick_scheduler.py` — absolute tick schedule + drift metrics |
| Run loop | `run_stage4_ai_decision_dry_run.py` — integrate scheduler + parse summary |
| Cerebras | `max_tokens` default 1100, schema trim, parse retry once |
| Rate gate | `STAGE4_FLEET_MIN_INTERVAL_SECONDS` when multi-symbol fleet |
| Parser | JSON repair + normalized error types |
| Validator | Export parse + tick metrics |
| Tests | `test_stage4_ai_decision_layer.py` — 413c regression cases |

---

## 7. Retry plan

### Step A — 30m regression (413c)
- `STAGE4_OUTPUT_DIR=/data/stage4_ai_decisions_413c_fixed_fleet_30m_regression`
- `STAGE4_CLOUD_DRY_RUN_MINUTES=30`, `poll=300`, target effective=20
- **PASS:** `tick_count=6`, `expected_tick_count=6`, `parse_error_count=0`, `validator_passed=true`, `provider_chain_failed<=4`

### Step B — Only if 413c PASS
- Stage 4.13d / 4.13b-retry: 180m fixed fleet, `target_effective_decision_count=120`

### Step C — If 413c FAIL
- Do **not** run 180m; continue parse / scheduler / provider yield repair.

---

## Safety checklist (unchanged)

- No orders, demo order, ARM, Stage 3 runner, production, btc-auto, radar
- No mock fallback
- No full API keys in logs
- No commit of data/jsonl/logs/bundles/secrets

# Stage 4.13c — Fixed Fleet Yield / Parse / Scheduler Repair

**Date:** 2026-06-08  
**Prior stage:** 4.13b Fixed Fleet 180m — **PARTIAL PASS**  
**Output reviewed:** `/data/stage4_ai_decisions_413b_fixed_fleet_180m`

---

## 1. 4.13b partial root cause

| Symptom | Value | Impact |
|---------|-------|--------|
| `tick_count` | 34 / 36 | Scheduler drift; two ticks lost |
| `effective_decision_count` | 117 / 120 | Below dataset target |
| `parse_error_count` | 1 | `validator_passed=false`, `technical_valid=false` |
| `provider_chain_failed_count` | 18 | ETH/SOL ×8 each; yield pressure |
| `cerebras_parse_error_count` (events) | 16 | Truncation / invalid JSON on fallback path |
| Groq success | 34 | Heavy `local_rate_gate_skip` + TPM governor → Cerebras fallback |

**Verdict:** Four-symbol read-only architecture is validated (all symbols seen, shadow/alias OK, no orders/mock). Partial pass is due to **scheduler drift**, **one parse error**, and **provider yield** — not strategy defects.

---

## 2. decision_65 parse error root cause

**Evidence (4.13b summary):**

- `decision_65_parse_error_true`
- `symbol=PEPEUSDT`
- `parse_error_count=1` (sole validator blocker)

**Likely mechanism:**

1. Groq primary skipped or rate-gated → Cerebras fallback.
2. Cerebras returned non-empty content that failed JSON parse (`json_decode_error` or truncated object).
3. Decision row retained `parse_error=true` with `real_llm_used=true`; supervisor forced `skip`.
4. Dry-run stats already excluded this row from `effective_decision_count`, but validator correctly fails on any `parse_error` in require-real-llm mode.

**Repair (4.13c):**

- Canonical `parse_error_type` classes: `provider_response_truncated`, `provider_invalid_json`, `provider_empty_response`, `provider_schema_mismatch`.
- Safe truncated-JSON repair in `stage4_response_parser.py`.
- Cerebras one-shot retry with bumped `max_tokens` on truncation/invalid JSON.
- Summary fields: `parse_error_count_by_symbol`, `parse_error_count_by_provider`, `parse_error_sample_refs`.

---

## 3. tick_count 34/36 root cause

**Config:** `duration=180m`, `poll=300s` → **expected 36 ticks**.

**Bug:** `run_stage4_ai_decision_dry_run.py` used `time.sleep(poll_interval_seconds)` **after** each tick’s symbol processing. With four symbols + gaps + LLM latency, each cycle took **processing + 300s**, not **300s wall-clock from run start**.

**Example:** If average tick processing ≈ 35s, effective period ≈ 335s → `10800/335 ≈ 32–34` ticks (matches observed 34).

**Repair (4.13c):**

- Absolute schedule: `next_tick_at = start + tick_index * poll_interval`.
- `sleep = max(0, next_tick_at - now)`.
- Metrics: `expected_tick_count`, `actual_tick_count`, `tick_drift_seconds_max`, `tick_processing_seconds_avg/max`.
- Loop bound: `while tick < expected_ticks and time.time() < end`.

---

## 4. Provider yield by symbol (4.13b)

| Symbol | Effective decisions | Chain failed |
|--------|---------------------|--------------|
| BTCUSDT | 34 | 0 |
| ETHUSDT | 26 | 8 |
| SOLUSDT | 26 | 8 |
| PEPEUSDT | 31 | 2 |

ETH/SOL bear the bulk of `provider_chain_failed` (Groq gate + Cerebras exhaustion/truncation under fleet pacing).

---

## 5. Cerebras parse/truncation by symbol

- **Global:** 16 Cerebras parse/truncation events; 83 Cerebras successes.
- **Concentration:** ETH/SOL chain failures (8 each) correlate with longer context + fallback load after Groq `local_rate_gate_skip`.
- **Hypothesis:** `max_tokens=900` + `json_schema` occasionally truncates (`finish_reason=length`) → `json_decode_error` on repair miss.

**Repair (4.13c):**

- Default `STAGE4_CEREBRAS_MAX_TOKENS` raised to **1100** (env override unchanged).
- Truncation retry once at `min(base+250, 2048)`.
- Fleet rate gate: `STAGE4_FLEET_LLM_MIN_INTERVAL_SECONDS` default **6s** when `STAGE4_SYMBOLS` has ≥2 symbols (was effectively 30s global).

---

## 6. Proposed patch list (implemented in 4.13c)

| Area | File(s) | Change |
|------|---------|--------|
| Parse taxonomy | `stage4_parse_error_metrics.py`, `stage4_ai_decision_agent.py` | Canonical types + summary aggregates |
| JSON repair | `stage4_response_parser.py` | Truncated object brace repair |
| Scheduler | `stage4_tick_scheduler.py`, `run_stage4_ai_decision_dry_run.py` | Absolute tick schedule + drift metrics |
| Provider yield | `stage4_rate_limit_gate.py`, `stage4_cerebras_payload.py`, `stage4_llm_client.py` | Fleet pacing, tokens 1100, Cerebras retry |
| Validation | `validate_stage4_ai_decision_outputs.py` | Parse + tick fields in report |
| Tests | `tests/test_stage4_ai_decision_layer.py` | `Stage413cRepairTests` |

**Not changed:** entry/exit strategy, confidence logic, risk limits, order paths, mock fallback.

---

## 7. Retry plan

### Step A — 30m regression (4.13c)

```
STAGE4_OUTPUT_DIR=/data/stage4_ai_decisions_413c_fixed_fleet_30m_regression
STAGE4_CLOUD_DRY_RUN_MINUTES=30
STAGE4_POLL_INTERVAL_SECONDS=300
STAGE4_TARGET_EFFECTIVE_DECISION_COUNT=20
STAGE4_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,PEPEUSDT
```

**PASS criteria:**

| Metric | Target |
|--------|--------|
| `tick_count` / `expected_tick_count` | 6 / 6 |
| `effective_decision_count` | ≥ 20 |
| `parse_error_count` | 0 |
| `validator_passed` / `technical_valid` | true |
| `provider_chain_failed_count` | ≤ 4 |
| `mock_ai_used_count` / `order_sent_count` | 0 |

### Step B — Only if 4.13c PASS

- **4.13d / 4.13b-retry:** 180m fixed fleet, `target_effective_decision_count=120`.

### Step C — If 4.13c FAIL

- Do **not** run 180m.
- Iterate parse repair, scheduler, or provider pacing only.

---

## Safety reaffirmation

- No orders, ARM, Stage 3 runner, production, btc-auto, or radar.
- `STAGE4_ALLOW_MOCK_FALLBACK=false`, `STAGE4_ORDER_ALLOWED=false`.
- Still **not** the demo-order / trading stage.

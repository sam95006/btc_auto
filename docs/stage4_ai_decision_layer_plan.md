# Stage 4 AI Decision Layer Plan

## Phase 4.0–4.1

- Mock and real LLM dry-run decision loop (no orders).
- Risk Supervisor always runs after AI proposal.
- Groq via OpenAI-compatible client with User-Agent, retries, and `llm_client_debug.jsonl`.

## Phase 4.2a — Cloud Real-LLM Required Guard

When cloud dry-run must use a real LLM, mock fallback is forbidden.

### Environment variables

| Variable | Default | Meaning |
|----------|---------|---------|
| `STAGE4_REQUIRE_REAL_LLM` | `false` | Hard require real LLM when `--use-real-llm` |
| `STAGE4_ALLOW_MOCK_FALLBACK` | `true` (unless require=true, then `false`) | Allow mock when real LLM unavailable |

Recommended cloud settings:

```env
STAGE4_REQUIRE_REAL_LLM=true
STAGE4_ALLOW_MOCK_FALLBACK=false
STAGE4_USE_REAL_LLM=true
STAGE4_DRY_RUN_ONLY=true
STAGE4_ORDER_ALLOWED=false
```

### Groq key aliases (checked in order)

1. `GROQ_API_KEY_PRIMARY`
2. `GROQ_API_KEY_SECONDARY`
3. `GROQ_API_KEY`

Keys are never logged. Health check reports alias names and presence only.

### Runner behavior (`run_stage4_ai_decision_dry_run.py`)

When real LLM is required but unavailable:

- Do **not** enter the decision loop.
- Do **not** write `ai_decisions.jsonl`.
- Write `stage4_ai_decision_summary.json` with `dry_run_completed=false`, `failed_reason`, `order_sent_count=0`.

Preflight CLI:

```bash
python tools/research/run_stage4_ai_decision_dry_run.py --preflight-only --use-real-llm --output-dir /path
```

### Validator strict mode

```bash
python tools/research/validate_stage4_ai_decision_outputs.py --output-dir /path --require-real-llm
```

Fails when: `real_llm_used_count=0`, mock used, fallback, missing debug log, or provider health check failed. Still requires `order_sent_count=0`.

### Entrypoint (Zeabur idle)

If `STAGE4_CLOUD_DRY_RUN_MINUTES > 0` and `STAGE4_REQUIRE_REAL_LLM=true`:

1. Run `--preflight-only` first.
2. On failure: log + write fail summary; **do not** start background dry-run.
3. On success: start background real-LLM dry-run.

### Stage 4.5 — Provider rate limit + Stage3 seed context
- `Stage4LLMRateGate`: min interval + backoff after 429; shared by health check and decisions.
- 429 / gate block → `ProviderRateLimited` → `stage4_system_events.jsonl` skipped tick (no fake decision).
- `STAGE4_LIGHT_PREFLIGHT=true` (default): key check only, no extra LLM health call.
- `STAGE4_POLL_INTERVAL_SECONDS` default 120; `STAGE4_SYMBOL_GAP_SECONDS` default 5.
- Validator `--require-real-llm`: requires `parse_error_count=0`, `real_successful_llm_decision_count>0`.

### Stage 4.6 — Cloud Stage3 seed + volume persistence

- `check_stage3_context_seed.py`: read-only context availability check before dry-run.
- `STAGE4_REQUIRE_STAGE3_CONTEXT=true`: entrypoint blocks dry-run if seed missing; writes fail summary.
- `STAGE4_SYMBOLS` env (default `ETHUSDT,BTCUSDT`) for single-symbol low-frequency runs.
- Dry-run `finally` + SIGTERM handler always writes `stage4_ai_decision_summary.json` and bundle export.
- Seed import order: deploy → RUNNING → seed import → context check PASS → set dry-run minutes → restart.

### Stage 4.6c — Rate-limit diagnosis

- Granular system events: `provider_http_429`, `local_rate_gate_skip`, `backoff_active_skip`, `healthcheck_skipped_by_gate`.
- `analyze_stage4_rate_limit_events.py`: diagnosis report with `can_rerun_now` and suggested poll interval.
- Health check shares rate gate; gate-blocked health check does not fail dry-run startup.

### Stage 4.7 — Secondary real LLM provider fallback

- `STAGE4_LLM_PROVIDER_CHAIN=groq,cerebras` with `STAGE4_ALLOW_SECONDARY_REAL_LLM_FALLBACK=true`.
- Groq duplicate key dedup (PRIMARY/SECONDARY/legacy); per-provider circuit breaker on HTTP 429.
- `Stage4ProviderChainClient`: Groq 429 → Cerebras real fallback (never mock).
- Decision log: `provider`, `provider_chain`, `provider_attempts`, `fallback_used`, `fallback_reason`.
- Summary: `provider_chain_deduped`, `deduped_provider_key_count`, `provider_success_distribution`.
- Validator `--require-real-llm`: rejects mock fallback; validates allowed real providers.
- Agent init with `STAGE4_REQUIRE_REAL_LLM=true` + `STAGE4_ALLOW_MOCK_FALLBACK=false`: unavailable real LLM → `RealLLMRequiredError` (no mock fallback).

### Stage 4.9 — 60m read-only soak

- ETHUSDT-only, poll=300s, provider chain groq+cerebras.
- Target ≥10 effective decisions for shadow compare dataset.

### Stage 4.10 — Shadow compare

- `tools/research/stage4_shadow_compare.py`: read-only post-decision kline analysis.
- Labels: good_skip, missed_opportunity, reasonable_watch, bad_watch, neutral, insufficient_future_data.
- Output: `shadow_compare.jsonl`, summary JSON, markdown report under `/data/stage4_shadow_compare_410/`.
- **not_a_backtest=true** — no orders, labels only.

### Stage 4.12 — Provider exhaustion fallback + partial soak finalization

- Groq HTTP 429 / `provider_quota_exhausted` / empty `content_empty` → Cerebras real fallback (never mock).
- `provider_attempts` records per-tick chain; summary tracks `provider_exhaustion_count`, `fallback_attempt_count`, `fallback_success_count`, `provider_chain_failed_count`.
- Partial completion always writes summary + bundle (`partial_completion`, `target_effective_decision_count`).
- Validator: `technical_valid` vs `dataset_target_met` (target default 30).
- Cerebras default model: `gpt-oss-120b` (do not inherit `STAGE4_LLM_MODEL` from Groq).
- Groq multi-key exhaustion (429/quota) prefers chain fallback even if a later key returns 401.

### Stage 4.12c — Provider yield + shadow quality review (read-only, no soak)

- `check_cerebras_auth_minimal.py`: Cerebras payload matrix A–E (diagnose `max_completion_tokens` conflict).
- `analyze_stage4_provider_yield.py`: Groq 429 / token estimates from soak output.
- `analyze_stage4_prompt_budget.py`: prompt character/token budget breakdown.
- `stage4_cerebras_payload.py` + `stage4_llm_client.py`: Cerebras uses `max_tokens` only (mirror Groq 4.12a-5 fix).
- Report: `docs/reports/STAGE_4_12C_PROVIDER_YIELD_AND_SHADOW_REVIEW.md`.
- Retry plans: Plan A (180m/300s + Cerebras fix + prompt trim); Plan B (360m/600s only if TPM still limits).

### Stage 4.12e — Provider yield repair (no 180m soak)

- Cerebras: dedicated `STAGE4_CEREBRAS_MAX_TOKENS` (default 900), separate error types (`provider_response_truncated`, `provider_empty_response`, `provider_quota_exhausted`).
- Groq TPM governor: `stage4_provider_quota_governor.py` — cooldown skip Groq, try Cerebras only (`STAGE4_GROQ_TPM_COOLDOWN_MINUTES`, default 45).
- Prompt compression: context caps 3/3/3, slim `market_context`, shorter system prompt; Groq completion cap default 450.
- Preflight throttle: Groq first-key-only probe; one Cerebras Stage4 decision probe (`preflight_probe_call_count <= 3`).
- `check_cerebras_stage4_decision_probe.py`: variants A–D (json_object/json_schema × 500/900).
- Gate: 30m / 6-tick short probe before any 180m retry. Report: `docs/reports/STAGE_4_12E_PROVIDER_YIELD_REPAIR_PLAN.md`.

### Stage 4.13 — Fixed fleet read-only expansion

- Fixed symbols: `BTCUSDT,ETHUSDT,SOLUSDT,PEPEUSDT` via `STAGE4_SYMBOLS`.
- `stage4_fleet_symbols.py`, `stage4_per_symbol_summary.py`, `stage4_context_skip.py`.
- Summary fields: `symbols_configured`, `symbols_seen`, `per_symbol`, `symbols_with_market_context_error`.
- PEPE fetch alias `1000PEPEUSDT`; context failure does not crash run.
- 30m probe gate: `effective >= 20/24`. Report: `docs/reports/STAGE_4_13_FIXED_FLEET_READ_ONLY_PLAN.md`.

### Stage 4.13a — Evidence / shadow correctness (pre-413b)

- Per-symbol `provider_chain_failed_count` from `stage4_system_events.jsonl` (not decisions-only).
- `stage4_shadow_compare.py`: filter by `decision.symbol`; PEPE kline alias `1000PEPEUSDT`.
- Validator: `per_symbol_failed_sum_matches_global`, `decision_missing_symbol_count`.

### Stage 4.4 — Regime + Stage3 context wiring (read-only)

- Kline-derived regime: `trend|range|volatile|unknown` with `regime_reason`, `trend_strength`, `volatility_level`.
- Stage3 context from `/data/stage3_demo_learning/*.jsonl` with availability flags.
- `import_stage3_context_seed.py` for bundle/JSONL seed import (not committed to git).
- Patch veto split: `patch_block` vs `manual_review_required` vs `hard_skip`.
- Decision log: `patch_blocked`, `matched_patch_actions`, stage3 counts.
- `export_stage4_ai_decision_bundle.py` → `stage4_44_decision_bundle.tar.gz` (secret scan).

### Stage 4.3 — Market context + prompt calibration (read-only)

- Enriched `market_context` via `stage4_market_context.py` (ticker + 15m klines, regime, volatility).
- Read-only symbols: `ETHUSDT`, `BTCUSDT` (`STAGE4_READ_ONLY_SYMBOLS`).
- Stage 3 summaries via `stage4_context_summary.py` (max 5 trades/reflections/patches).
- Prompt adds `decision_intent`, `missing_data`, `edge_factors`, `risk_factors`.
- Supervisor veto reasons: `hard_skip`, `soft_skip`, `watch`, `patch_block`, `missing_market_context`, `order_not_allowed_dry_run`, `confidence_below_threshold`.

### Strict-env read-only exception (Stage 4.2b)

When all of the following hold:

- `STAGE3_STARTUP_MODE=idle`
- `STAGE4_DRY_RUN_ONLY=true`
- `STAGE4_ORDER_ALLOWED=false`
- `STAGE4_REQUIRE_REAL_LLM=true`
- `STAGE4_ALLOW_MOCK_FALLBACK=false`
- `OPERATOR_GO_STAGE3_24H_RUNNER=false`

`check_bybit_demo_learning_env.py` allows read-only safety values:

- `PAPER_ONLY=true`
- `BYBIT_SHADOW_MODE=true`
- `BYBIT_ORDER_ALLOWED=false`
- `EXCHANGE_WRITE_ALLOWED=false`
- `PRIVATE_ORDER_ENDPOINT_BLOCKED=true` (required)

Still hard-fails if `REAL_MONEY`, `LIVE_TRADING`, `BYBIT_MAINNET_ALLOWED`, or `PRODUCTION_PROMOTION_ALLOWED` are true, or if runner/order flags are unsafe.

### Safety invariants (unchanged)

- No orders sent in dry-run mode.
- Stage 3 runner remains gated by `STAGE3_STARTUP_MODE=idle`.
- Production / btc-auto services are out of scope.

### Stage 4.13c — Yield / parse / scheduler repair (fixed fleet)

- Absolute tick scheduler (`expected_tick_count`, `tick_drift_seconds_*`, `tick_processing_seconds_*`).
- Canonical parse-error taxonomy + `parse_error_count_by_symbol` / `by_provider` / `parse_error_sample_refs`.
- Parse-error decisions excluded from `effective_decision_count`.
- Fleet LLM min interval default 6s when `STAGE4_SYMBOLS` has ≥2 symbols; Cerebras default `max_tokens=1100` with one truncation retry.
- See `docs/reports/STAGE_4_13C_FIXED_FLEET_YIELD_PARSE_SCHEDULER_REPAIR.md`.

### Stage 4.13d — Fixed fleet 180m read-only soak

- Output: `/data/stage4_ai_decisions_413d_fixed_fleet_180m`
- PASS: 36/36 ticks, 138 effective (target 120), parse=0, 4 symbols, validator PASS.

### Stage 4.14 — Fixed fleet multi-session read-only stability review

- **4.14a:** Evidence / quality review only (no long soak). Modules:
  - `stage4_provider_stability_review.py`
  - `stage4_shadow_quality_summary.py`
  - `stage4_multi_session_review.py`
- **4.14b (gate):** 6h fixed fleet read-only soak (360m, 72 ticks, target 240 effective) — only after 4.14a PASS.
- **4.14b result:** PARTIAL PASS — ops layer validated (285 effective, 72/72 ticks); blocked by 1 Cerebras truncation parse on ETHUSDT.
- **4.14c:** Cerebras truncation repair — `finish_reason=length` always triggers one safe retry with `STAGE4_CEREBRAS_RETRY_MAX_TOKENS=1400` + compact JSON instruction; provider dependency budget guard metrics.
- **4.14d:** 6h clean validation — PARTIAL PASS (268 effective, 72/72 ticks); 1× `provider_schema_mismatch` on BTCUSDT (missing `requires_manual_review`).
- **4.14f:** Schema mismatch repair — cosmetic defaults for skip-safe near-valid JSON; safe_skip_defaults for directional gaps; never repairs into enter/long/short.
- See `docs/reports/STAGE_4_14_FIXED_FLEET_MULTI_SESSION_READ_ONLY_REVIEW.md`, `docs/reports/STAGE_4_14C_CEREBRAS_TRUNCATION_PARSE_REPAIR.md`, `docs/reports/STAGE_4_14D_FIXED_FLEET_6H_CLEAN_VALIDATION_REPORT.md`, `docs/reports/STAGE_4_14F_PROVIDER_SCHEMA_MISMATCH_REPAIR.md`.

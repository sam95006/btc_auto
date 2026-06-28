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

# Stage 4 AI Decision Layer Plan

**Scope:** AI-assisted enter/skip proposals with Risk Supervisor gate. Dry-run only in this phase.

## Goal

Before any demo order, an AI Decision Agent evaluates:

1. Bybit market data (public ticker)
2. Account snapshot
3. Active learning patches (JSONL retrieval)
4. Recent trade results / reflections
5. Safety constraints (immutable)
6. Regime / market condition (mock classifier in Phase 4.0)

Output: structured JSON decision log — **never sends orders** in dry-run.

## Components

| File | Role |
|------|------|
| `stage4_ai_decision_agent.py` | Mock/real AI proposal + patch retrieval |
| `stage4_risk_supervisor.py` | Veto / reduce / force_skip — cannot submit orders |
| `run_stage4_ai_decision_dry_run.py` | Local polling loop |
| `validate_stage4_ai_decision_outputs.py` | Schema + safety validation |

## Output paths

- Local: `data/external_alpha/stage4_ai_decisions/`
- Zeabur (future): `/data/stage4_ai_decisions/`

Files:

- `ai_decisions.jsonl`
- `risk_supervisor_decisions.jsonl`
- `stage4_ai_decision_summary.json`

## Safety invariants

AI **cannot** modify:

- `max_margin_usd`, `max_leverage`, `max_open_positions`
- `require_stop_loss`, `require_max_hold`
- `mainnet_allowed`, `real_money`, `production_promotion_allowed`

Risk Supervisor hard-vetoes unsafe env and active `block_reentry` / `manual_review_required` patches.

## Phase 4.0 (this round)

- Deterministic **mock AI** (`is_mock_ai=true`, `model_name=mock_ai_decision_agent`)
- JSONL patch retrieval (no VectorDB)
- Local dry-run only — no Zeabur 24h runner

## Phase 4.1a (this round)

- Root cause of 30m empty responses: Groq HTTP 403 (Cloudflare 1010) when `User-Agent` header missing
- `stage4_llm_client.py`: User-Agent, retries/backoff, `llm_client_debug.jsonl`, GROQ secondary key fallback
- `stage4_response_parser.py`: content extraction + markdown/tool-call JSON parsing
- `check_stage4_llm_provider.py`: minimal health probe
- Dry-run logs: `stage4_30m_dry_run.log` / `stage4_short_run.log` under output dir

Health check:

```bash
python tools/research/check_stage4_llm_provider.py --provider groq --model llama-3.3-70b-versatile
```

## Phase 4.1 (previous)

- Real LLM via `stage4_llm_client.py` (Groq / OpenAI / Anthropic / Gemini / Ollama / Cerebras)
- Blocked: DeepSeek, Qwen, ChatGLM, and other China-origin model name patterns
- Structured JSON output enforced by `stage4_decision_schema.py`
- Prompt builder: `stage4_prompt_builder.py`
- Flow: LLM → Risk Supervisor → `final_decision` → `order_sent=false`
- `--use-real-llm` on dry-run runner; honest `fallback_to_mock=true` if no key

Run locally:

```bash
python tools/research/run_stage4_ai_decision_dry_run.py --duration-minutes 30 --poll-interval-seconds 60 --symbols ETHUSDT,BTCUSDT --mode dry-run --use-real-llm
```

## Phase 4.2 (future)

- Wire real LLM with `is_mock_ai=false`
- Integrate with Stage 3 demo-order path behind `decision_source=ai_decision_agent`
- Zeabur shadow dry-run service

## Acceptance

- `decision_count > 0`
- Every row: `order_sent=false`, `prompt_hash`, `risk_supervisor_result`
- Patch veto tests pass in unittest

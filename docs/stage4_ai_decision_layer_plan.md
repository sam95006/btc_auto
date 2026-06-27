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

## Phase 4.1 (future)

- Wire real LLM with `is_mock_ai=false`
- Integrate with Stage 3 demo-order path behind `decision_source=ai_decision_agent`
- Zeabur shadow dry-run service

## Acceptance

- `decision_count > 0`
- Every row: `order_sent=false`, `prompt_hash`, `risk_supervisor_result`
- Patch veto tests pass in unittest

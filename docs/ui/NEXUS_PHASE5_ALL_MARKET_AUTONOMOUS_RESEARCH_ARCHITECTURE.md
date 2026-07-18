# NEXUS Phase 5 — All-Market AI Review Runtime Architecture

**Gate B: All-Market AI Review Runtime**
Status: IMPLEMENTED
Research-only · No real orders · No private API

---

## Overview

Phase 5 Gate B introduces the All-Market AI Review Runtime — a structured, deterministic research
layer that reviews scanner candidates using role-based analysts and a 6-hour scheduled review cycle.
All processing is research-only and does not trigger any real trading.

---

## Gate B Architecture

### Package: `backend/nexus_research/`

| Module | Purpose |
|---|---|
| `storage.py` | Storage audit + adapter (memory default; optional sqlite under NEXUS_DATA_DIR) |
| `domain_events.py` | Append-only NexusDomainEvent bus with idempotency dedup + dead-letter queue |
| `runtime_supervisor.py` | 24h supervisor: job registry, retry/backoff, circuit breaker, stuck detection |
| `review_cases.py` | CandidateReviewCase manager: triggers, dedup, cooldown, expiry |
| `roles.py` | 6 role analysts + DecisionOrchestrator; deterministic RULES mode |
| `ai_review_cycle.py` | 6h cycle scheduler (Asia/Taipei: 00:00, 06:00, 12:00, 18:00) |
| `api_routes.py` | Flask Blueprint with 9 GET-only research API endpoints |

---

### Event Bus (`domain_events.py`)

- Append-only, bounded in-memory deque (capacity: 2000)
- Idempotency key deduplication
- Dead-letter queue for unknown event types (capacity: 200)
- Correlation/causation chain support
- Event types: MARKET_SNAPSHOT_UPDATED, CANDIDATE_*, REVIEW_CASE_*, ROLE_ASSESSMENT_*,
  RESEARCH_DECISION_*, REVIEW_CYCLE_*, SIM_*, REFLECTION_*, PATCH_*, SUPERVISOR_*, SCANNER_SNAPSHOT_INGESTED

### Review Cases (`review_cases.py`)

**Triggers:**
- `TOP5_ENTRY` — candidate appears in scanner long/short top 5
- `CONFIRMED` — candidate reaches CONFIRMED stage
- `SCORE_CHANGE` — significant score delta (≥10 points)
- `MAJOR_ANOMALY` — anomaly signal detected
- `POSITION_RISK` — risk score threshold breach
- `SCHEDULED_REVIEW` — 6h cycle sweep
- `MANUAL_RESEARCH` — operator-initiated

**Lifecycle:** `PENDING → IN_REVIEW → COMPLETED | EXPIRED | CANCELLED`

**Deduplication rules:**
- Same (symbol, direction, trigger) within active window → deduped
- Cooldown per (symbol, direction): 5 minutes after close
- Auto-expire after 1 hour
- Close on candidate invalidation

**Scanner hook:** `ingest_scanner_snapshot(snapshot)` is called best-effort after each
scanner candidate recompute (inside `MarketScannerService.refresh_once()`). Never breaks scanner.

### Role Analysts (`roles.py`)

| Role | Responsibility |
|---|---|
| `MARKET_CONTEXT` | 24h trend, funding rate, volatility flags |
| `STRUCTURE` | 5m price/OI alignment, spread quality |
| `RISK_CRITIC` | Risk score gate, overextended flag — **mandatory, never skipped** |
| `PORTFOLIO` | Case load assessment |
| `PERFORMANCE` | Score quality |
| `REFLECTION` | Prior outcome pattern review |
| `DecisionOrchestrator` | Runs all roles, produces ResearchDecision |

**Decision statuses:** `WATCH_ONLY | REJECTED | RISK_BLOCKED | READY_FOR_SIMULATION | EXPIRED`

**Analysis mode:** `RULES` (deterministic templates from evidence; no LLM fabrication).
Mark `analysisMode: "LLM"` only when a real LLM response is available.

**Critical constraint:** Risk Critic assessment is mandatory in every orchestration run.
The orchestrator cannot produce a `READY_FOR_SIMULATION` result if Risk Critic verdict is `BLOCKED`.

### AI Review Cycle (`ai_review_cycle.py`)

- Schedule: **Asia/Taipei 00:00, 06:00, 12:00, 18:00** (UTC+8)
- Session deduplication by slot key (one session per 6h slot)
- Manual trigger available via `AIReviewCycleScheduler.trigger_manual()`
- Session states: `PENDING → RUNNING → COMPLETED | SKIPPED | FAILED`
- Collects non-fabricated summary: active cases, event bus stats, storage audit
- Registered as a supervisor job (6h interval)

### Research Supervisor (`runtime_supervisor.py`)

- Single-owner daemon thread (24h)
- Per-job circuit breaker (3 failures → open for 5 minutes)
- Stuck detection threshold: 120 seconds
- Retry with exponential backoff
- Graceful shutdown hooks

---

## API Endpoints (Gate B)

All endpoints: GET-only, `researchOnly: true`, `Cache-Control: no-store`, no secrets.

| Endpoint | Description |
|---|---|
| `GET /api/nexus/runtime/status` | Supervisor status + job registry |
| `GET /api/nexus/events/status` | Event bus stats + DLQ count |
| `GET /api/nexus/review-cases` | List review cases (filters: status, symbol, limit) |
| `GET /api/nexus/review-cases/<caseId>` | Single case detail |
| `GET /api/nexus/review-cases/status` | Case manager summary |
| `GET /api/nexus/ai-reviews/status` | Cycle scheduler status |
| `GET /api/nexus/ai-reviews/sessions` | List review sessions |
| `GET /api/nexus/ai-reviews/sessions/<sessionId>` | Single session detail |
| `GET /api/nexus/decisions/status` | Recent research decisions |

---

## Frontend (Gate B UI)

- Page: `frontend/src/pages/AiReviewsPage.tsx` at route `/ai-reviews`
- SidebarNav: RESEARCH group, label "AI 檢討中心" (collapsed by default)
- Fetches `/api/nexus/ai-reviews/status` and `/api/nexus/ai-reviews/sessions`
- Shows empty/partial/completed states honestly — no fabricated chat
- CSS: `.nx-ai-reviews` namespace in `global.css`

---

## Deploy Mirror

Modules are mirrored under:
```
deploy/zeabur_stage3_demo_learning/backend/nexus_research/
```
Routes registered in `stage3_readonly_web_app.py` (try/except guard).
SPA prefix `ai-reviews` added to `_SPA_PREFIXES`.

---

## Safety Constraints

- `RESEARCH_ONLY = True` at package level
- No fleet runtime created (no HQ, no fixed BTC/ETH fleet)
- No private API calls (`privateApi: false` on all responses)
- No real order submission in any code path
- Candidate scoring/ranking formulas untouched
- Scanner hook is best-effort: any exception is silently swallowed

---

## Gate C (Simulator / Risk / Reflection / Replay)
Status: IMPLEMENTED
Research-only · No real orders · No private API · Simulation-isolated

---

### Gate C Overview

Gate C adds a fully isolated simulation execution layer to the Phase 5 research stack.
All Gate C modules operate exclusively on simulated state and never interact with any
real exchange, wallet, or production system.

---

### Gate C Architecture

#### Package: `backend/nexus_research/` (Gate C additions)

| Module | Purpose |
|---|---|
| `simulator.py` | Simulated MARKET/LIMIT orders; pending/partial/filled/cancelled/expired/rejected; spread slippage fee funding latency precision margin leverage unrealised/realised PnL |
| `sim_ledger.py` | Append-only ledger: cash, margin, orders, fills, positions, fees, funding, PnL, equity. Reconciliation, idempotency, no negative balance (honest reject) |
| `risk_engine.py` | Simulator-only risk: max position/symbol/sector/portfolio notional, leverage, concurrent, daily loss, drawdown, correlation, funding crowding, spread, stale, missing evidence, candidate expiry, duplicate, kill switch |
| `capital_allocator.py` | Simulated allocation only; conservative when sample insufficient; score-scaled fixed fraction |
| `reflection.py` | Post-sim close attribution + reflection + PatchProposal (PROPOSED only). Never auto-applies to production |
| `patch_governance.py` | States PROPOSED→…→APPLIED_TO_SIMULATION / ROLLED_BACK; approval gates require problem/evidence/sample/scope/replay/walk-forward/rollback metadata |
| `replay.py` | Deterministic replay from public OHLCV/OI/funding/candidate/anomaly inputs; date range; seed; pause/resume/checkpoint |
| `soak.py` | Accelerated smoke soak framework (smoke/1h/6h/24h/72h profiles; smoke verify in verify script) |
| `sim_routes.py` | Flask Blueprint: 14 GET + 2 POST (guarded) API endpoints for Gate C |
| `gate_b_to_gate_c.py` | Integration bridge: `try_simulate_decision(decision)` → risk→allocator→simulator; `read_sim_closed_positions_for_reflection()` |

---

### Simulator (`simulator.py`)

- MARKET and LIMIT order types
- Order states: `PENDING → PARTIAL → FILLED / CANCELLED / EXPIRED / REJECTED`
- Fill model: bid/ask spread + slippage (configurable bps), taker/maker fee, latency guard
- Per-position: entry fee, funding accrual, unrealised PnL → realised PnL on close
- Kill switch: halts all new submissions instantly
- Config-driven: spread_bps, slippage_market_bps, taker_fee_bps, maker_fee_bps, fill_latency_ms, price_precision, default_leverage, max_leverage
- Thread-safe in-memory; no production persistence

### Ledger (`sim_ledger.py`)

- Append-only events: `DEPOSIT / WITHDRAWAL / ORDER_SUBMITTED / ORDER_FILLED / ORDER_CANCELLED / ORDER_EXPIRED / ORDER_REJECTED / POSITION_OPENED / POSITION_CLOSED / FEE_CHARGED / FUNDING_CHARGED / PNL_REALISED / MARGIN_RESERVED / MARGIN_RELEASED / RECONCILIATION / REJECT_INSUFFICIENT_BALANCE`
- Honest negative-balance reject: never allows impossible state
- Idempotency via key deduplication
- Bounded history (5000 events)
- UTC millisecond timestamps
- `reconcile()` returns equity = cash + margin + unrealised_pnl

### Risk Engine (`risk_engine.py`)

**Verdicts:**

| Verdict | Meaning |
|---|---|
| `ALLOW_SIMULATION` | All checks pass |
| `REDUCE_SIZE` | Oversized; suggested_qty provided |
| `BLOCK_KILL_SWITCH` | Kill switch active |
| `BLOCK_MAX_LEVERAGE` | Leverage exceeds limit |
| `BLOCK_MAX_POSITION` | Max concurrent positions reached |
| `BLOCK_MAX_NOTIONAL` | Per-symbol or portfolio notional exceeded |
| `BLOCK_DAILY_LOSS` | Daily loss limit breached |
| `BLOCK_DRAWDOWN` | Drawdown limit breached |
| `BLOCK_DUPLICATE` | Same (symbol, side) already open |
| `BLOCK_SPREAD` | Spread too wide |
| `BLOCK_STALE_DATA` | Market data age exceeds limit |
| `BLOCK_MISSING_EVIDENCE` | Required evidence fields absent |
| `BLOCK_CANDIDATE_EXPIRY` | Candidate expired |
| `BLOCK_FUNDING_CROWDING` | Funding rate exceeds crowding threshold |
| `BLOCK_CORRELATION` | Sector notional cap exceeded |

### Capital Allocator (`capital_allocator.py`)

- Fixed-fraction of equity (configurable 2–5%)
- Score-scaled: score < 50 → 0 allocation; score 50–90 → linear scale to max fraction
- Conservative mode: sample < 20 closed trades → multiply fraction by 0.5
- Hard caps: per-symbol notional, portfolio notional
- Never allocates real capital

### Reflection (`reflection.py`)

- Triggered after each simulated position close
- Attribution: realised/gross PnL, price move %, fee drag %, funding, outcome class (WIN/LOSS/BREAKEVEN)
- Pattern detection: repeated losses on same symbol with high score → PatchProposal
- Fee drag threshold: >0.5% of notional → PatchProposal
- **`autoApplyProduction: false` enforced in all proposals**
- Persists to `sim_reflections` table in research store

### Patch Governance (`patch_governance.py`)

**State machine:**
```
PROPOSED → UNDER_REVIEW → APPROVED_SIM → APPLIED_TO_SIMULATION
         → REJECTED                    → ROLLED_BACK
         → NEEDS_REPLAY → REPLAY_DONE → APPROVED_SIM
```

**Approval preconditions for `APPROVED_SIM`:**
- `problem` and `evidence` fields present
- `scope = "simulation_only"`
- `rollbackDescription` present
- `sampleSize >= requiresMinSample`
- `requires_replay` satisfied if true
- `requires_walk_forward` satisfied if true
- `autoApplyProduction` must be False (enforced, cannot be overridden)

### Replay (`replay.py`)

- Deterministic: same seed → same fill sequence
- Public data only: OHLCV bars, OI, funding rate, candidate events, anomaly events
- Synthetic bar generation for testing when real data unavailable
- Pause / resume from current bar index
- Checkpoint snapshots every N bars (configurable)
- Session states: `IDLE → RUNNING → PAUSED / COMPLETED / FAILED`

### Soak Framework (`soak.py`)

| Profile | Duration | Interval | Symbols |
|---|---|---|---|
| `smoke` | 0.5h | 1m | 2 |
| `1h` | 1h | 5m | 3 |
| `6h` | 6h | 5m | 5 |
| `24h` | 24h | 1h | 8 |
| `72h` | 72h | 1h | 10 |

- Always isolated (fresh sim/ledger instances)
- `run_smoke_verify()` for CI/verify scripts (completes in seconds)
- Verdict: PASS/FAIL based on state + equity > 0 + no errors

---

### Gate C API Endpoints

All endpoints: `researchOnly: true`, `Cache-Control: no-store`, no secrets.

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/nexus/simulator/status` | GET | Simulator status, kill switch, PnL summary |
| `GET /api/nexus/simulator/orders` | GET | Order list (filters: symbol, state, limit) |
| `GET /api/nexus/simulator/positions` | GET | Open/closed positions + unrealised PnL |
| `GET /api/nexus/simulator/ledger` | GET | Ledger snapshot + recent events |
| `POST /api/nexus/simulator/order` | POST | Test helper (requires `researchOnly:true` in body) |
| `GET /api/nexus/risk/status` | GET | Risk engine stats, config summary |
| `GET /api/nexus/replay/status` | GET | Replay engine session overview |
| `GET /api/nexus/replay/sessions/<id>` | GET | Single replay session detail |
| `GET /api/nexus/reflection/status` | GET | Reflection analyst stats |
| `GET /api/nexus/reflection/records` | GET | Reflection records (filter: symbol, limit) |
| `GET /api/nexus/patch/status` | GET | Patch governance state counts |
| `GET /api/nexus/patch/proposals` | GET | Proposal list (filter: state, symbol, limit) |
| `GET /api/nexus/soak/status` | GET | Soak framework latest verdict |
| `GET /api/nexus/soak/results` | GET | Soak result history |
| `POST /api/nexus/soak/run` | POST | Trigger isolated soak (requires `researchOnly:true` in body) |

---

### Gate B → Gate C Integration

`gate_b_to_gate_c.py` provides:

```python
from backend.nexus_research.gate_b_to_gate_c import try_simulate_decision

result = try_simulate_decision(decision.to_dict())
# result.attempted, result.success, result.order_id, result.risk_verdict
```

- Called optionally after `READY_FOR_SIMULATION` decision is produced
- Flow: `try_simulate_decision` → risk check → allocator → `sim.submit_order()`
- Returns `SimulationAttemptResult` on all paths (never throws)
- Non-eligible statuses are skipped silently

`read_sim_closed_positions_for_reflection()` — for Gate B Reflection role to read sim history.

---

### Deploy Mirror

All Gate C modules mirrored under:
```
deploy/zeabur_stage3_demo_learning/backend/nexus_research/
```
Gate C routes registered in `stage3_readonly_web_app.py` (try/except guard).
POST allowlist added to `_read_only_guard` for research-only helpers.
SPA prefixes `simulation` and `replay` added for future frontend routes.

---

### Safety Constraints (Gate C)

- `RESEARCH_ONLY = True` in every module
- `privateApi: false` on all API responses
- No real exchange API calls in any code path
- Kill switch enforced at order submission level
- Negative balance rejected by ledger with audit event
- Patch proposals: `autoApplyProduction: False` enforced by governance (cannot be overridden)
- Reflection does not write to any production config file
- Replay uses only public OHLCV/OI/funding/candidate/anomaly inputs
- Candidate scoring/ranking formulas untouched

---

### Verification

```bash
python tools/research/verify_phase5_gate_c.py
```

Expected output: `VERDICT=PASS`

---


## Verification

```bash
python tools/research/verify_phase5_gate_b.py
```

Expected output: `VERDICT=PASS`

---

## Phase 6 Persistence

**Phase 6 Gate B — Production Durable Persistence**
Status: IMPLEMENTED (postgres driver pending)
Research-only · No real orders · No private API

### New modules

| Module | Purpose |
|---|---|
| `storage_discovery.py` | `discover_storage()` — env-name presence check, recommended mode, no secret values |
| `storage.py` (enhanced) | Schema v2 migrations, typed tables, idempotency keys, UTC timestamps, retention/pagination |

### Env contract

| Variable | Purpose |
|---|---|
| `NEXUS_RESEARCH_DATABASE_URL` | Postgres DSN (pending psycopg2-binary in requirements) |
| `DATABASE_URL` | Fallback postgres DSN |
| `NEXUS_DATA_DIR` | Directory for `nexus_research.db` (never `trading.db`) |
| `NEXUS_RESEARCH_STORAGE_MODE` | `memory` \| `sqlite` \| `postgres` \| `auto` |

### Typed tables (schema v2)

`domain_events`, `dead_letters`, `review_cases`, `role_assessments`,
`research_decisions`, `review_sessions`, `sim_orders`, `sim_fills`,
`sim_positions`, `sim_ledger`, `risk_snapshots`, `outcomes`, `reflections`,
`patch_proposals`, `replay_checkpoints`, `runtime_job_state`,
`persistence_validation_markers`

Each typed table has a `UNIQUE` idempotency key constraint, UTC `created_at_utc`
column, and relevant secondary indexes.  Generic `kv` table retained for
backward compatibility.

### Durability honesty

If neither a confirmed-volume NEXUS_DATA_DIR nor a postgres URL is available:
`durableClaim=false`, `productionPersistenceAvailable=false`.
Sqlite under a non-volume-confirmed path → mode `sqlite_ephemeral`, NOT "durable".

### New API endpoints

- `GET /api/nexus/storage/status` — storageMode, durableClaim, volumeConfirmed, lastMigrationVersion, health
- `GET /api/nexus/storage/discovery` — env presence report, recommended mode (no secret values)

### Postgres status

psycopg2-binary is **not** in requirements.txt.  Postgres URLs are detected and
logged as warnings; the store falls back to sqlite/memory.  To enable postgres,
add `psycopg2-binary` to requirements.txt and re-run migrations.

### Verification

```bash
python tools/research/verify_phase6_gate_b_persistence.py
```

Expected output: `VERDICT=PASS`

---

## Phase 6 Gate D — AI-assisted Review, Performance Validation, Soak Framework

**Status: IMPLEMENTED**
Research-only · No real orders · No private API · LLM allowlist: openai, anthropic, azure_openai

### Overview

Gate D adds:
1. **Reasoning Provider** — structured interface for deterministic vs LLM-assisted analysis
2. **Performance Service** — per-stream metrics with strict stream separation
3. **Review Engine** — exposes current review mode to the UI honestly
4. **Live Soak Framework** — 30-minute smoke checklist + phased soak markers

### New modules

| Module | Purpose |
|---|---|
| `reasoning_provider.py` | `ResearchReasoningProvider` ABC + `RulesOnlyProvider` + `LlmAssistedProvider` stub |
| `performance_service.py` | Per-stream performance metrics: LIVE_PAPER / SHADOW / REPLAY / MANUAL_VALIDATION |
| `review_engine.py` | Wraps orchestrator + provider; exposes `reviewMode` / `uiModeLabel` to UI |
| `live_soak.py` | 30m smoke checklist + phased markers (6h/24h/72h DEFERRED) |

### Reasoning Provider

**Modes:**

| Mode | Condition |
|---|---|
| `RULES_ONLY` | No LLM env configured, or provider blocked |
| `LLM_ASSISTED` | Approved provider env set + API key present |
| `LLM_UNAVAILABLE` | Provider env set but API key absent |
| `DEGRADED` | Circuit breaker open (3 failures → 10-min cooldown) |

**Allowlisted providers (western/approved only):**
- `openai`, `anthropic`, `azure_openai`
- Any other provider (including Chinese endpoints) → `RULES_ONLY` (blocked)

**Safety invariants:**
- LLM NEVER modifies candidate scores, risk verdicts, or creates orders
- Only public market evidence packs sent to LLM (no private account data)
- No secrets logged
- Token budget: evidence ≤2000 tokens, output ≤800 tokens
- Numeric hallucination guard: rejects invented price/OI numbers
- JSON schema validation + SHA-256 output hash for audit
- Prompt version: `gate-d-v1`

**Env vars:**

| Variable | Purpose |
|---|---|
| `NEXUS_RESEARCH_LLM_PROVIDER` | `openai` \| `anthropic` \| `azure_openai` (or absent → RULES_ONLY) |
| `OPENAI_API_KEY` | Required if provider=openai |
| `ANTHROPIC_API_KEY` | Required if provider=anthropic |
| `AZURE_OPENAI_API_KEY` | Required if provider=azure_openai |

### Performance Service

**Streams (NEVER merged):**

| Stream ID | Source |
|---|---|
| `LIVE_PAPER` | Autonomous paper positions from `paper_controller` |
| `SHADOW` | Shadow / dry-run records (no sim positions) |
| `REPLAY` | Historical replay soak results |
| `MANUAL_VALIDATION` | Operator-triggered manual research cases |

**Metrics per stream:** cases, decisions by status, sim entries, open/closed positions,
PnL gross/net, fees, slippage, funding, win rate, expectancy, profit factor, max drawdown,
MFE/MAE, avg hold time, risk-block effectiveness, sample size + uncertainty label.

**Uncertainty labels:** INSUFFICIENT (<10) → LOW (<30) → MODERATE (<100) → ADEQUATE (≥100)

**New API endpoints:**

| Endpoint | Purpose |
|---|---|
| `GET /api/nexus/performance/summary` | All-stream summary |
| `GET /api/nexus/performance/by-sector` | Sector breakdown per stream |
| `GET /api/nexus/performance/by-regime` | Regime breakdown per stream |
| `GET /api/nexus/performance/by-side` | Long/Short breakdown per stream |
| `GET /api/nexus/performance/risk-blocks` | Risk block effectiveness per stream |
| `GET /api/nexus/performance/calibration` | Win rate / expectancy / PF per stream |
| `GET /api/nexus/review-engine/status` | Review mode + provider status |
| `GET /api/nexus/soak/live/status` | Live soak + phased marker status |

### Review Engine

Wraps `DecisionOrchestrator` (roles.py) + reasoning provider. Exposes:
- `reviewMode`: RULES_ONLY / LLM_ASSISTED / LLM_UNAVAILABLE / DEGRADED
- `uiModeLabel`: honest Chinese label (e.g. "規則式分析（非生成式 AI）")
- `fabricatedChat: false` (always)
- `_invariant`: annotation that reasoning never modifies risk verdict

UI must display mode honestly:
- `RULES_ONLY` → "規則式分析（非生成式 AI）" — NOT labelled as generative AI
- `LLM_ASSISTED` → "LLM 輔助分析" + provider name

### Live Soak Framework (30m smoke)

**30-minute smoke checklist (5 items):**

| Item | Check |
|---|---|
| `SIM_STACK_ALIVE` | Sim + ledger initialize; bars processed > 0 |
| `RISK_ENGINE_ACTIVE` | At least 1 risk decision recorded |
| `LEDGER_CONSISTENT` | Final equity > 0 (no negative balance) |
| `EXIT_POLICIES_FIRE` | At least 1 position closed (SKIP if window too short) |
| `NO_PRIVATE_API` | No private API references in soak errors |

**Phased markers:**

| Phase | Default status | Notes |
|---|---|---|
| `smoke_30m` | PENDING → PASSED/FAILED | Auto-run |
| `6h` | DEFERRED | Requires manual trigger |
| `24h` | DEFERRED | Requires manual trigger |
| `72h` | DEFERRED | Requires manual trigger |

### Frontend

- New page: `ResearchPerformancePage.tsx` at `/research-performance`
- Added to `SidebarNav.tsx` RESEARCH group: "Research Performance"
- `AiReviewsPage.tsx` updated: shows `ReviewEngineModeBanner` with honest mode disclosure
- Phase 6 Gate D marker badge on AI Review Center page
- SPA prefix `research-performance` added to `operator_ui_routes.py` and `stage3_readonly_web_app.py`

### Version

`__version__ = "6.0.0-gate-d"` · `PHASE = "6-GATE-D"`

### Verification

```bash
# Performance + Soak
python tools/research/verify_phase6_gate_d_performance.py

# AI Review + Reasoning Provider
python tools/research/verify_phase6_gate_d_ai_review.py
```

Expected output: `VERDICT=PASS`

### Mirror

All new `backend/nexus_research/` modules are mirrored to:
`deploy/zeabur_stage3_demo_learning/backend/nexus_research/`


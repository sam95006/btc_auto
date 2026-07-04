# Stage 4.16 — Paper-Trading Design Gate

**Date:** 2026-07-05  
**Branch:** `stage3-demo-learning`  
**Prerequisite:** Stage 4.15 `NEEDS_RISK_GOVERNOR_RULES` — `97187f4`  
**Mode:** **Design only — no execution**

---

## 0. Executive summary

Stage 4.16 defines how Stage 4 AI decisions would flow into a **hypothetical paper-trading pipeline** without placing any orders. The design introduces:

1. A **Hypothetical Entry Log** schema (append-only JSONL)
2. A **Watchlist Follow-up Tier** between `watch` and `hypothetical_entry`
3. **Enter Candidate Rules** with Risk Governor pre-checks
4. Four **Watch-Quality Guards** derived from Stage 4.15 shadow evidence
5. **Paper Exit / Evaluation** rules reusing shadow compare thresholds
6. **Post-Paper Reflection** schema (design-only; no live confidence mutation)
7. A **Stage 4.17** proposal with a recommended safest path

**This document does not implement, enable, or schedule any paper order execution.**

---

## 1. How AI decisions become hypothetical entry logs

### 1.1 Pipeline overview (design)

```text
Stage 4 AI Decision (read-only dry-run output)
        │
        ▼
┌───────────────────────┐
│  Paper Event Classifier │  maps decision_intent → paper_action candidate
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Watchlist State Store  │  watch → watchlist (never direct entry)
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Risk Governor Guards   │  SOL/PEPE/trend/MAE rules (Stage 4.15)
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Hypothetical Entry Log │  append-only JSONL (design schema below)
└───────────┬───────────┘
            │
            ▼ (later Stage 4.17+)
┌───────────────────────┐
│  Paper Exit Evaluator   │  fixed horizon / SL / TP simulation
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  Post-Paper Reflection  │  design-only record; no auto-apply
└───────────────────────┘
```

### 1.1.1 Input source

| Field | Source |
|-------|--------|
| `decision_id`, `symbol`, `decision_intent`, `final_action`, `candidate_side`, `confidence`, `provider`, `created_at_utc` | `ai_decisions.jsonl` |
| `market_regime`, `last_price`, volatility proxies | `market_context` on decision |
| `parse_error`, `schema_repaired`, `schema_repair_mode` | decision metadata |
| Shadow quality priors | Stage 4.15 per-symbol rates (offline config, not live mutation) |

### 1.1.2 Classification rules (high level)

| `decision_intent` | Initial `paper_action` candidate | Notes |
|-------------------|----------------------------------|-------|
| `hard_skip` | `hypothetical_skip` | Never watchlist, never entry |
| `soft_skip` | `hypothetical_skip` | May later produce `avoided_bad_trade` outcome |
| `watch` | `watchlist` | **Never** direct `hypothetical_entry` |
| `enter_candidate` | `hypothetical_entry` (pending RG) | Still requires full guard chain |

### 1.1.3 Output location (future Stage 4.17)

```text
/data/stage4_paper_events/hypothetical_entry_log.jsonl
/data/stage4_paper_events/paper_exit_evaluations.jsonl
/data/stage4_paper_events/post_paper_reflections.jsonl
```

Stage 4.16 defines schemas and rules only. No files are written in 4.16.

---

## 2. Hypothetical Entry Log Schema

### 2.1 Core record

```json
{
  "record_type": "stage4_hypothetical_paper_event",
  "paper_event_id": "pevt_20260705T023000Z_BTCUSDT_a1b2c3",
  "source_decision_id": "dec_20260705T023000Z_BTCUSDT_xyz",
  "source_tick_index": 12,
  "timestamp_utc": "2026-07-05T02:30:00Z",
  "symbol": "BTCUSDT",
  "decision_intent": "enter_candidate",
  "final_action": "skip",
  "paper_action": "hypothetical_entry",
  "candidate_side": "LONG",
  "reference_price": 62500.0,
  "hypothetical_entry_price": 62500.0,
  "hypothetical_stop_loss": 61875.0,
  "hypothetical_take_profit": 63125.0,
  "hypothetical_max_hold_minutes": 60,
  "risk_governor_verdict": "allow",
  "risk_governor_reasons": [],
  "watchlist_follow_up": {
    "required": false,
    "watchlist_id": null,
    "confirmation_count": 0,
    "confirmation_threshold": 2
  },
  "provider": "cerebras",
  "confidence": 0.52,
  "market_regime": "trend",
  "volatility_level": "medium",
  "mae_proxy_pct": 0.12,
  "shadow_prior_bad_watch_rate": 0.1124,
  "parse_error": false,
  "schema_repaired": false,
  "schema_repair_mode": null,
  "order_sent": false,
  "is_mock_ai": false,
  "created_by": "stage4_16_design_only",
  "design_gate_version": "4.16"
}
```

### 2.2 Field definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `paper_event_id` | string | yes | Unique ID: `pevt_{utc_compact}_{symbol}_{hash6}` |
| `source_decision_id` | string | yes | FK to Stage 4 decision |
| `timestamp_utc` | ISO8601 | yes | Decision timestamp |
| `symbol` | string | yes | Fleet symbol (BTCUSDT, ETHUSDT, SOLUSDT, PEPEUSDT) |
| `decision_intent` | enum | yes | `enter_candidate` \| `watch` \| `soft_skip` \| `hard_skip` |
| `paper_action` | enum | yes | `watchlist` \| `hypothetical_entry` \| `hypothetical_skip` |
| `candidate_side` | enum | yes | `LONG` \| `SHORT` \| `NONE` |
| `reference_price` | float | yes | `market_context.last_price` at decision time |
| `hypothetical_entry_price` | float | if entry | Same as reference unless slippage model added in 4.17 |
| `hypothetical_stop_loss` | float | if entry | Simulated SL price |
| `hypothetical_take_profit` | float | if entry | Simulated TP price |
| `risk_governor_verdict` | enum | yes | `allow` \| `block` \| `downgrade_to_watchlist` \| `downgrade_to_skip` |
| `risk_governor_reasons` | string[] | yes | Rule IDs that fired |
| `provider` | string | yes | `groq` \| `cerebras` |
| `confidence` | float | yes | LLM confidence 0–1 |
| `market_regime` | enum | yes | `trend` \| `range` \| `volatile` \| `unknown` |
| `created_by` | string | yes | Always `stage4_16_design_only` until 4.17 implementation gate |

### 2.3 `paper_action` assignment matrix

| Intent + RG verdict | `paper_action` |
|---------------------|----------------|
| `watch` + any | `watchlist` |
| `enter_candidate` + `allow` | `hypothetical_entry` |
| `enter_candidate` + `downgrade_to_watchlist` | `watchlist` |
| `enter_candidate` + `block` / `downgrade_to_skip` | `hypothetical_skip` |
| `soft_skip` / `hard_skip` | `hypothetical_skip` |

### 2.4 Stop-loss / take-profit defaults (design constants)

Aligned with shadow compare thresholds (`ADVERSITY_WATCH_PCT = 0.35`, `TREND_THRESHOLD_PCT = 0.4`):

| Symbol tier | SL % from entry | TP % from entry | Max hold |
|-------------|-----------------|-----------------|----------|
| BTC/ETH (majors) | 0.35% | 0.60% | 60m |
| SOL (high bad_watch) | 0.25% | 0.45% | 45m |
| PEPE (meme) | 0.20% | 0.40% | 30m |

These are **simulation defaults only** — not live order parameters.

---

## 3. Watchlist Follow-up Tier

### 3.1 Design principle

**`watch` intent must never become `hypothetical_entry` in the same tick.**

Stage 4.15 evidence: 113/113 `bad_watch` labels came from `watch` intent. Direct watch→entry would replicate the worst shadow failure mode.

### 3.2 Watchlist state schema (design)

```json
{
  "record_type": "stage4_watchlist_entry",
  "watchlist_id": "wl_20260705T020000Z_SOLUSDT_ab12",
  "symbol": "SOLUSDT",
  "first_decision_id": "dec_...",
  "last_decision_id": "dec_...",
  "first_seen_utc": "2026-07-05T02:00:00Z",
  "last_seen_utc": "2026-07-05T02:30:00Z",
  "confirmation_count": 2,
  "confirmation_threshold": 2,
  "side_bias": "LONG",
  "confidence_series": [0.48, 0.51],
  "regime_series": ["trend", "trend"],
  "status": "pending|confirmed|expired|blocked",
  "blocked_reason": null,
  "expires_after_ticks": 6
}
```

### 3.3 Follow-up confirmation criteria

A watchlist entry may **graduate** to `hypothetical_entry` candidate only when **all** conditions hold:

| # | Criterion | Rationale |
|---|-----------|-----------|
| 1 | Same symbol shows **≥2 consecutive** `watch` or `enter_candidate` within watchlist window (default 6 ticks / 30m) | Reduces single-tick noise |
| 2 | Confidence **non-decreasing** (latest ≥ first − 0.05) | Stage 4.15 bad_watch avg conf 0.513 — declining conf is a downgrade signal |
| 3 | Market regime **not** entering high-vol adverse condition | SOL/PEPE bad_watch in `volatile` + `trend` |
| 4 | Risk Governor returns `allow` (no block/downgrade) | RG guards mandatory |
| 5 | MAE proxy ≤ symbol tier cap (SOL ≤ 0.25%, PEPE ≤ 0.20%, majors ≤ 0.35%) | Pre-empt adverse excursion |
| 6 | Provider response valid: `parse_error=false`, no `schema_repair_mode=safe_skip_defaults` | 414f safe-skip repairs must not enter |
| 7 | No recent bad_watch cluster: symbol bad_watch in last N shadow-equivalent ticks < 2 | Rolling window from paper log, not live trading |
| 8 | Latest intent is `enter_candidate` **or** confirmed watch with side bias ≠ NONE | Side must be explicit before entry |

### 3.4 Watchlist expiration

- **Expire** after 6 ticks (30m at 5m poll) without confirmation → status `expired`, no entry.
- **Block** immediately if any RG guard fires → status `blocked`.
- Expired/blocked watchlist entries produce `hypothetical_skip` paper events with reason logged.

### 3.5 Missed-opportunity mitigation (Stage 4.15 finding)

65/90 `missed_opportunity` came from `watch`, not skip. Watchlist follow-up is the designed path to capture directional moves **without** skipping the confirmation tier:

```text
watch → watchlist → (confirm) → hypothetical_entry → evaluate at 60m
watch → watchlist → (expire)  → hypothetical_skip  → outcome: missed_opportunity_followup (if move was directional)
```

---

## 4. Enter Candidate Rules

`enter_candidate` **never** places an order. It may only produce a `hypothetical_entry` paper event after passing all gates.

### 4.1 Mandatory preconditions

| # | Rule | Fail action |
|---|------|-------------|
| E1 | `decision_intent == enter_candidate` | N/A |
| E2 | `final_action` consistent (not contradicted by supervisor veto without reason) | `downgrade_to_skip` |
| E3 | `candidate_side` ∈ {LONG, SHORT} | `downgrade_to_watchlist` if side unclear |
| E4 | `confidence >= CONFIDENCE_THRESHOLD` (default 0.35, existing RG) | `downgrade_to_skip` |
| E5 | `parse_error == false` | `block` |
| E6 | `schema_repaired == false` OR `schema_repair_mode != safe_skip_defaults` | `block` |
| E7 | `is_mock_ai == false` | `block` |
| E8 | Risk Governor `approved == true` (existing Stage4RiskSupervisor) | `block` |
| E9 | Symbol-specific watch-quality guard pass (Section 5) | per guard |
| E10 | Provider budget healthy: no chain_failed on same tick; Cerebras dependency budget not exhausted | `downgrade_to_watchlist` |
| E11 | No active blocking patch / manual_review | `block` |
| E12 | `order_sent == false` (always true in Stage 4; assert in 4.17 logger) | `block` |

### 4.2 Symbol-tier confidence floors (Stage 4.15 calibrated)

| Symbol | Min confidence for hypothetical entry | Notes |
|--------|---------------------------------------|-------|
| BTCUSDT | 0.40 | bad_watch_rate 0.11 |
| ETHUSDT | 0.38 | good_skip strong |
| SOLUSDT | 0.50 | bad_watch_rate 0.26 |
| PEPEUSDT | 0.52 | bad_watch + missed_opp elevated |

### 4.3 Enter candidate without watchlist

`enter_candidate` may skip watchlist **only** for BTC/ETH when:

- confidence ≥ tier floor + 0.05
- regime ∈ {range, unknown} OR (regime=trend AND side aligns with 15m trend proxy)
- no bad_watch cluster in last 3 ticks
- all RG guards pass

SOL/PEPE **always** require watchlist confirmation even from `enter_candidate`.

---

## 5. Risk Governor Watch-Quality Guards

These extend the existing `Stage4RiskSupervisor` (veto/adjust only; never submits orders). Stage 4.16 defines rule specs; implementation deferred to 4.17.

### 5.1 `watch_quality_guard_sol_high_volatility`

**Evidence:** SOL bad_watch_rate = 0.259 (Stage 4.15)

| Input | Source |
|-------|--------|
| `symbol` | decision |
| `market_regime` | decision.regime / market_context |
| `volatility_level` | market_context.volatility_level |
| `mae_proxy_pct` | rolling 15m adverse move estimate |
| `shadow_bad_watch_cluster` | count of bad_watch paper outcomes in last 6 ticks |
| `confidence` | decision |

**Decision table:**

| Condition | Verdict | Reason code |
|-----------|---------|-------------|
| regime=volatile AND volatility_level=high | `force_hard_skip` | `sol_vol_block` |
| regime=trend AND mae_proxy > 0.25% | `downgrade_to_soft_skip` | `sol_trend_mae` |
| shadow_bad_watch_cluster ≥ 2 | `downgrade_to_soft_skip` | `sol_bad_watch_cluster` |
| confidence < 0.45 AND regime=volatile | `downgrade_to_soft_skip` | `sol_low_conf_vol` |
| else | `allow_watch` | — |

*Note:* For `watch` intent, `allow_watch` → watchlist. For `enter_candidate`, any non-allow → block or downgrade.

### 5.2 `watch_quality_guard_meme_adverse_excursion`

**Evidence:** PEPE bad_watch_rate = 0.2515, missed_opp_rate = 0.2335

| Condition | Verdict | Reason code |
|-----------|---------|-------------|
| symbol=PEPEUSDT AND intent=enter_candidate AND watchlist confirmation < 2 | `downgrade_to_watchlist` | `pepe_watchlist_required` |
| regime=volatile OR volatility_level=high | `downgrade_to_watchlist` (watch) / `force_hard_skip` (enter) | `pepe_vol_cap` |
| mae_proxy > 0.20% | `force_hard_skip` | `pepe_mae_cap` |
| missed_opportunity cluster ≥ 3 in last 12 ticks | `downgrade_to_soft_skip` | `pepe_missed_cluster` |
| else (watch only) | `allow_watch` → watchlist | — |

**PEPE never receives direct hypothetical_entry without watchlist confirmation.**

### 5.3 `elevated_mae_watch_downgrade_or_soft_skip`

**Evidence:** 100% of bad_watch = watch intent with MAE-dominated shadow labels

| Input | Threshold |
|-------|-----------|
| `decision_intent` | watch or enter_candidate |
| `mae_proxy_pct` | vs symbol tier cap |
| `historical_watch_to_bad_watch_rate` | from Stage 4.15 offline priors |

| Condition | Verdict |
|-----------|---------|
| intent=watch AND mae_proxy > 80% of symbol cap | `downgrade_to_soft_skip` |
| intent=watch AND historical rate > 0.20 for symbol | `downgrade_to_watchlist` with elevated confirmation_threshold=3 |
| intent=enter_candidate AND mae_proxy > 60% of cap | `downgrade_to_watchlist` |

### 5.4 `regime_aware_watch_cap:trend`

**Evidence:** bad_watch regime trend=65, volatile=42, range=6 (Stage 4.15)

| Condition | Verdict |
|-----------|---------|
| regime=trend AND symbol ∈ {SOLUSDT, PEPEUSDT} AND intent=watch | `allow_watch` but **watchlist only**, confirmation_threshold=3 |
| regime=trend AND intent=enter_candidate AND side not aligned with 15m trend | `downgrade_to_watchlist` |
| regime=trend AND confidence < 0.55 for alts | `downgrade_to_soft_skip` |
| regime=range AND symbol ∈ {BTCUSDT, ETHUSDT} | standard watchlist rules |
| regime=volatile | delegate to SOL/PEPE guards |

### 5.5 Guard evaluation order

```text
1. parse/schema/mock hard blocks (E5–E7)
2. existing Stage4RiskSupervisor (patches, confidence, mainnet, ARM)
3. watch_quality_guard_meme_adverse_excursion  (if PEPE)
4. watch_quality_guard_sol_high_volatility      (if SOL)
5. elevated_mae_watch_downgrade_or_soft_skip    (all symbols)
6. regime_aware_watch_cap:trend                 (all symbols)
7. watchlist graduation check                   (if from watchlist)
```

---

## 6. Paper Exit / Evaluation Rules

### 6.1 Hypothetical exit record schema (design)

```json
{
  "record_type": "stage4_paper_exit_evaluation",
  "paper_event_id": "pevt_...",
  "symbol": "SOLUSDT",
  "candidate_side": "LONG",
  "entry_price": 145.0,
  "exit_price": 144.2,
  "exit_reason": "stop_loss|take_profit|max_hold|horizon",
  "exit_timestamp_utc": "2026-07-05T03:30:00Z",
  "hold_minutes": 45,
  "return_pct": -0.55,
  "mae_pct": 0.62,
  "mfe_pct": 0.18,
  "realized_volatility": 0.41,
  "horizon_evaluations": {
    "15m": {"return_pct": -0.12, "mae_pct": 0.15, "mfe_pct": 0.08},
    "30m": {"return_pct": -0.28, "mae_pct": 0.35, "mfe_pct": 0.12},
    "60m": {"return_pct": -0.55, "mae_pct": 0.62, "mfe_pct": 0.18}
  },
  "outcome_label": "bad_entry",
  "shadow_label_equivalent": "bad_watch",
  "order_sent": false,
  "created_by": "stage4_16_design_only"
}
```

### 6.2 Exit simulation modes

| Mode | Trigger | Priority |
|------|---------|----------|
| **Stop-loss** | MAE reaches `hypothetical_stop_loss` intrabar | 1 (highest) |
| **Take-profit** | MFE reaches `hypothetical_take_profit` | 2 |
| **Max hold** | `hold_minutes >= hypothetical_max_hold_minutes` | 3 |
| **Fixed horizon** | 15m / 30m / 60m mark-to-market snapshot | 4 (evaluation only) |

### 6.3 Outcome labels

| Label | Condition |
|-------|-----------|
| `good_entry` | Directional move in favor; return ≥ TP threshold or MFE > MAE + margin |
| `bad_entry` | Adverse excursion dominates (mirrors shadow `bad_watch` logic) |
| `neutral_entry` | abs(return) < neutral threshold (0.15%) |
| `avoided_bad_trade` | `hypothetical_skip` and subsequent move would have been bad_entry |
| `missed_opportunity_followup` | watchlist expired/skipped but 60m move was directional |
| `risk_governor_saved_trade` | RG blocked/downgraded and subsequent move was bad_entry |

Reuse shadow compare constants from `stage4_shadow_compare.py`:

- `NEUTRAL_THRESHOLD_PCT = 0.15`
- `TREND_THRESHOLD_PCT = 0.4`
- `MFE_MAE_MARGIN_PCT = 0.2`
- `ADVERSITY_WATCH_PCT = 0.35`

### 6.4 PnL simulation (design)

```text
return_pct = (exit_price - entry_price) / entry_price * 100
           (inverted for SHORT)

pnl_simulated_usd = notional_usd * return_pct / 100
notional_usd = design constant (e.g. 100 USDT hypothetical, not margin/leverage)
```

No leverage simulation in Stage 4.17 initial implementation — flat notional only.

---

## 7. Post-Paper Reflection

### 7.1 Schema (design only)

```json
{
  "record_type": "stage4_post_paper_reflection",
  "reflection_id": "pref_20260705T040000Z_SOLUSDT_c4d5",
  "paper_event_id": "pevt_...",
  "paper_exit_id": "pexit_...",
  "symbol": "SOLUSDT",
  "outcome_label": "bad_entry",
  "pnl_simulated": -0.55,
  "mae": 0.62,
  "mfe": 0.18,
  "reflection_summary": "Watch graduated to entry in trend regime but MAE exceeded SOL cap; RG should have downgraded.",
  "should_reduce_confidence": true,
  "should_block_similar_context": true,
  "suggested_risk_rule_update": "elevated_mae_watch_downgrade_or_soft_skip: tighten SOL mae_proxy cap to 0.20%",
  "context_fingerprint": {
    "regime": "trend",
    "volatility_level": "high",
    "intent_chain": ["watch", "watch", "enter_candidate"],
    "provider": "cerebras"
  },
  "applies_to_future_decisions": false,
  "auto_apply_forbidden": true,
  "created_by": "stage4_16_design_only"
}
```

### 7.2 Reflection rules (design)

| Outcome | Suggested action (human review only) |
|---------|----------------------------------------|
| `bad_entry` on SOL/PEPE | Flag `should_block_similar_context`; suggest RG tighten |
| `risk_governor_saved_trade` | Positive RG validation; no rule change |
| `missed_opportunity_followup` | Suggest watchlist window extension, not lower confidence |
| `good_entry` | Record for paper performance baseline |

### 7.3 Explicit prohibition (Stage 4.16 / 4.17 initial)

- **`applies_to_future_decisions` must remain `false`** until operator-approved learning gate
- **No auto-apply** to confidence, prompts, or RG thresholds
- **No write** to `applied_patches` or learning queue from paper reflections in 4.17-A

---

## 8. What Stage 4.17 may do (and what remains forbidden)

### 8.1 Stage 4.17 allowed (after explicit operator approval)

| Activity | Allowed in 4.17-A |
|----------|-------------------|
| Append `hypothetical_entry_log.jsonl` from existing decisions | Yes |
| Run watchlist follow-up simulator on historical JSONL | Yes |
| Compute paper exit evaluations offline | Yes |
| Write post-paper reflections (no auto-apply) | Yes |
| Unit tests for schema validation | Yes |

### 8.2 Still forbidden through Stage 4.17

| Activity | Status |
|----------|--------|
| Demo order | **Forbidden** |
| Paper order execution (any exchange API) | **Forbidden** |
| ARM | **Forbidden** |
| Radar station | **Forbidden** |
| Real money | **Forbidden** |
| Production / btc-auto | **Forbidden** |
| Stage 3 runner auto-start | **Forbidden** |
| Mock AI fallback | **Forbidden** |
| 6h / 24h new soak (unless separate approved gate) | **Forbidden** |
| Modify core strategy engines | **Forbidden** |
| Auto-apply reflections to live confidence | **Forbidden** |
| Commit data/jsonl/logs/bundles/secrets | **Forbidden** |

---

## 9. Stage 4.17 Proposal

### Option A — Paper event logger implementation

- **Scope:** Read existing `ai_decisions.jsonl`; classify; apply RG guards; append hypothetical logs only.
- **Output:** `/data/stage4_paper_events/hypothetical_entry_log.jsonl`
- **Orders:** Zero
- **Risk:** Lowest — append-only, no market interaction beyond existing kline read for exit eval

### Option B — Watchlist follow-up simulator

- **Scope:** Replay 413d/414b/414d decisions; simulate watchlist state machine; measure graduation rate.
- **Output:** Simulation report JSON + optional paper logs
- **Orders:** Zero
- **Risk:** Low — read-only replay; no new LLM calls

### Option C — 24h read-only + paper shadow design

- **Scope:** Extended soak plus paper pipeline design validation
- **Orders:** Zero
- **Risk:** Medium — long runtime, provider cost, requires explicit operator approval

### 9.1 Recommendation: **Option A** (safest incremental path)

**Rationale:**

1. Smallest blast radius — one new append-only writer, no exchange calls
2. Directly implements schemas defined in this document
3. Reuses existing Stage 4 decision outputs (718 effective decisions already validated)
4. Option B can run as a **read-only analysis pass** on A's output without new infrastructure
5. Option C deferred until A+B show acceptable bad_entry rate on SOL/PEPE guards

**Suggested 4.17-A deliverables:**

- `tools/research/stage4_paper_event_logger.py` (design from 4.16; logger only)
- `tests/test_stage4_paper_event_schema.py`
- `docs/reports/STAGE_4_17_PAPER_EVENT_LOGGER_REPORT.md`
- Validator: `order_sent=0`, `mock_ai_used=0`, no API key in logs

---

## 10. Gate verdict

| Check | Status |
|-------|--------|
| Hypothetical entry log schema defined | **Yes** |
| Watchlist follow-up tier defined | **Yes** |
| Enter candidate rules defined | **Yes** |
| RG watch-quality guards defined | **Yes** |
| Paper exit evaluation rules defined | **Yes** |
| Post-paper reflection schema defined | **Yes** |
| Stage 4.17 proposal documented | **Yes** |
| Any code executed paper orders | **No** |
| Any trading action sent | **No** |

**final_verdict:** `STAGE_4_16_DESIGN_GATE_COMPLETE`

**decision_quality_verdict (inherited):** `NEEDS_RISK_GOVERNOR_RULES` — guards specified above; implementation in 4.17-A

**next_step:** Await explicit operator instruction to begin **Stage 4.17-A (paper event logger)**. Do not auto-start.

---

## Appendix A — Stage 4.15 evidence cross-reference

| Metric | Value | Design response |
|--------|-------|-----------------|
| bad_watch total | 113 | Watchlist mandatory; MAE guards |
| bad_watch from watch | 100% | No direct watch→entry |
| SOL/PEPE share | 66% | Symbol-tier guards + higher conf floors |
| bad_watch avg conf | 0.513 | Non-decreasing conf rule in watchlist |
| bad_watch regime trend | 65 | `regime_aware_watch_cap:trend` |
| missed_opp total | 90 | Watchlist follow-up path |
| missed_opp from watch | 65 | Graduation criteria, not skip bypass |
| Cerebras dependency | 79.16% | Provider budget gate in E10 |
| order_sent | 0 | Hard assert in all paper modules |

## Appendix B — Related files

| File | Role |
|------|------|
| `docs/reports/STAGE_4_15_FIXED_FLEET_DECISION_QUALITY_REVIEW.md` | Evidence input |
| `tools/research/stage4_decision_quality_review.py` | Quality analyzer (4.15) |
| `tools/research/stage4_risk_supervisor.py` | Existing RG (extend in 4.17) |
| `tools/research/stage4_shadow_compare.py` | Threshold source for exit labels |
| `docs/stage4_ai_decision_layer_plan.md` | Master plan |

---

**Prohibitions remain in force. Stage 4.16 stops at design gate.**

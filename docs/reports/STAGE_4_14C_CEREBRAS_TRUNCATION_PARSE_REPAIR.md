# Stage 4.14c — Cerebras Truncation / Parse Repair

**Date:** 2026-07-03  
**Branch:** `stage3-demo-learning`  
**Prior session:** Stage 4.14b 6h fixed-fleet read-only soak — **PARTIAL PASS**

---

## 1. Stage 4.14b partial pass summary

| Metric | Value |
|--------|-------|
| output_dir | `/data/stage4_ai_decisions_414b_fixed_fleet_6h` |
| duration_minutes | 360 |
| tick_count | 72 / 72 |
| tick_drift_seconds_max | 0.0 |
| effective_decision_count | 285 (target 240) |
| dataset_target_met | true |
| per_symbol counts | BTC=71, ETH=71, SOL=71, PEPE=72 |
| provider_chain_failed_count | 2 |
| provider_success | groq=36, cerebras=249 |
| mock_ai_used_count | 0 |
| order_sent_count | 0 |

Operational layer: **PASS** — scheduler, fleet yield, provider fallback, and safety gates held for 6h.

---

## 2. Parse error root cause

Single parse error blocked full PASS:

| Field | Value |
|-------|-------|
| decision_id | `8e895f58-d536-447b-88f5-b8669f2b5bf1` |
| decision_index | ~184 |
| symbol | ETHUSDT |
| provider | cerebras |
| parse_error_type | `provider_response_truncated` |
| finish_reason | `length` (inferred) |
| max_tokens_used | 1100 |

**Root cause:** Cerebras returned `finish_reason=length`. `stage4_response_parser._repair_truncated_json` repaired partial JSON successfully, so `_finalize_cerebras_content` returned `status=ok` despite truncation. The truncation retry in `stage4_llm_client` never ran (it only fired on `status != ok`). Decision schema validation then failed and was classified as `provider_response_truncated` via `finish_reason=length`.

**Retry was not attempted** on the failing decision.

---

## 3. Why 6h operational layer is valid

- 72/72 ticks, zero scheduler drift
- 285 effective decisions across four symbols (all ≥ 50 per symbol)
- Real LLM only (no mock fallback)
- No orders sent, no API key leak
- Provider chain failed only twice (within budget)
- Cerebras carried ~87% of successful decisions after Groq TPM cooldown — expected under current quota profile

The 6h architecture is validated; the blocker is a single truncation edge case, not fleet or scheduler instability.

---

## 4. Why validator blocked full pass

- `parse_error_count=1` (ETHUSDT / cerebras)
- `validator_passed=false`, `technical_valid=false`
- PASS criteria require `parse_error_count=0`

---

## 5. Repair patch list

| File | Change |
|------|--------|
| `tools/research/stage4_cerebras_payload.py` | `resolve_cerebras_retry_max_tokens()` (default 1400), `compact_cerebras_retry_messages()` |
| `tools/research/stage4_llm_client.py` | Treat `finish_reason=length` as truncation always; one safe retry with compact prompt + `STAGE4_CEREBRAS_RETRY_MAX_TOKENS` |
| `tools/research/stage4_ai_decision_agent.py` | Propagate truncation retry metadata on decisions |
| `tools/research/stage4_provider_metrics.py` | `build_provider_dependency_metrics()` budget guard |
| `tools/research/run_stage4_ai_decision_dry_run.py` | Summary metrics for retry counts + dependency guard |
| `tests/test_stage4_ai_decision_layer.py` | Stage414cRepairTests |

**New env:** `STAGE4_CEREBRAS_RETRY_MAX_TOKENS=1400`

---

## 6. Retry / short regression plan

1. Deploy repair to Zeabur `nexus-stage3-bybit-demo-learning`
2. Run **30m fixed-fleet regression** (not 6h):
   - `STAGE4_OUTPUT_DIR=/data/stage4_ai_decisions_414c_fixed_fleet_30m_regression`
   - `STAGE4_CLOUD_DRY_RUN_MINUTES=30`
   - `STAGE4_TARGET_EFFECTIVE_DECISION_COUNT=20`
   - `STAGE4_CEREBRAS_RETRY_MAX_TOKENS=1400`
3. Finalize: validator + reset `STAGE4_CLOUD_DRY_RUN_MINUTES=0`

**414c PASS:** tick 6/6, effective ≥ 20, parse_error=0, validator PASS.

---

## 7. Criteria to re-run 6h or avoid

| Outcome | Next step |
|---------|-----------|
| 414c 30m regression PASS | Option A: 414d 6h clean validation; Option B: proceed to multi-session plan without re-soak if team accepts 414b ops + 414c parse fix |
| 414c regression FAIL (parse > 0) | Do **not** re-run 6h; iterate truncation retry / token budget |
| Re-run 6h only if | Scheduler/provider path changed materially, or stakeholder requires clean 6h validator PASS record |

**Still forbidden:** demo order, ARM, radar, production, btc-auto, mock fallback.

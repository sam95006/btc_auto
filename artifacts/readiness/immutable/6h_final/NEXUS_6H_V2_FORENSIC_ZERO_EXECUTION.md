# NEXUS 6H V2 Forensic Audit — Zero Execution

**Recommendation:** `NEXUS_6H_INCONCLUSIVE_FORENSIC_REQUIRED`  
**12H_ALLOWED:** `false`  
**Do not start 12H.**

## Canonical classification

| Field | Value |
|-------|-------|
| session_id | `NEXUS-DEMO-6H-V2-20260801T091457Z-2350a7d0` |
| canonical_6h_classification | `DEMO_AUTONOMOUS_6H_V2_INCONCLUSIVE_NO_EXECUTION` |
| runtime_recommendation_sot | `DEMO_AUTONOMOUS_6H_V2_FAILED` |
| gha_orchestrator_recommendation | `DEMO_AUTONOMOUS_6H_V2_PASS_WITH_FINDINGS` (**not** used for 12H) |
| operational_safety_pass | `true` |
| autonomous_execution_observed | `false` |
| order_route_verified | `false` |
| completed_outcome_observed | `false` |
| learning_chain_observed | `false` |

Operational pipeline: scan → cost gate → deadline → write-window close → flat account.  
Autonomous trading chain (valid intent → order → fill → protect → close → outcome → reflection) **not observed**.

## Funnel (evidence-backed)

Source: live `GET /api/nexus/demo-execution/persistence` `stream_counts` + `bounded-6h/status` (2026-08-02).

| Counter | Value | Evidence |
|---------|------:|----------|
| candidates_seen_total | 1318 | `bounded_candidates=1318`, `candidates_total=1318` |
| universe_scans_total | 170 | `universe_scans=170` |
| geometry_evaluated_total | null | not exposed |
| geometry_complete_total | null | not exposed |
| geometry_missing_total | null | not exposed |
| cost_gate_evaluated_total | **1311** | `cost_gates` stream count (= evaluations persisted) |
| cost_gate_pass_total | **0** | stream `cost_gates` == `cost_gate_blocks` == 1311 |
| cost_gate_block_total | 1311 | status + stream |
| risk_critic_block_total | 0 | status |
| mistake_guard_block_total | 0 | status |
| decision_delta_count (raw) | 1318 | **not** validated learning |
| intents | 0 | stream |
| orders | 0 | stream |
| outcomes | 0 | stream |
| reflections | 0 | stream |
| entries_total | 0 | status |
| completed_trades_total | 0 | status |
| exchange_write_attempt_total | null / 0 inferred | no order stream rows; kill_switch_events=0 |

### Gap: 1318 − 1311 = 7

**Do not label as Cost Gate passes.**

Code path (`bounded_6h_session._try_entry`): risk → decision_delta/mistake → allocator/qty/instrument → **then** cost_gate.

- risk_critic_blocks=0, mistake_guard_blocks=0, decision_deltas=1318 ⇒ all 1318 passed risk + mistake.
- Only 1311 `cost_gates` rows ⇒ **7 exited before cost evaluation** (allocator / price / instrument / reader `continue` with **no counter**).
- `cost_gates` count == `cost_gate_blocks` ⇒ **0 Cost Gate passes** among evaluated.

`cost_gate_block_reason_distribution`: **NOT_AVAILABLE** (payload stream not exposed via status API). Finding: `OBSERVABILITY_GAP_COST_GATE_REASON_DISTRIBUTION`.

## Zero-order root cause

| Class | Applied | Proof |
|-------|---------|-------|
| A. NO_CANDIDATE_PASSED_COST_GATE | **YES** | `cost_gates=1311` == `cost_gate_blocks=1311`; entries=0; no order kill |
| C. VALID_INTENT_NOT_CREATED | **YES** | `intents=0`, `dry_run_intents=0`, `orders=0` |
| H. OBSERVABILITY_INSUFFICIENT | **YES** | 7 pre-cost silent drops; no reason distribution; no exchange_* counters |
| B/D/E/F/G | not evidenced | no pass → no intent → no exchange retCode; domain=`api-demo.bybit.com` |

## Account identity (read-only, hashed)

| Field | Value |
|-------|-------|
| api_domain | `https://api-demo.bybit.com` |
| account_epoch | `epoch-0001` |
| epoch_fingerprint | `17ed5abfb1bb176c` |
| wallet_balance | 5024.31888124 |
| equity | 5024.31888124 |
| available_balance | 5029.0864552 |
| mainnet / real_money | false / false |
| founder_expected_account_fingerprint_match | **UNKNOWN** (Founder fingerprint not supplied this turn) |

## Safety freeze

position/order=0 · reconciliation MATCH · write windows closed · 12H not started · 24H not approved.

## Next required

1. Observability counters + cost reason distribution (persistent).  
2. Same-router Demo execution probe.  
3. `bounded-12h` start/status/stop API.  
4. Harden machine gate (execution evidence required).  
5. Reconsider 12H only after probe PASS + documented root cause.

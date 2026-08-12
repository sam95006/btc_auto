# V11.1 R1 A/B Remediation — Decision + Execution Bridge

Generated: 2026-08-05T04:13:10Z

## Verdict

**FIXED** — Decision↔Intent↔Position bridge via canonical execution adapter; decorative ID minting removed; risk/cost/lifecycle invariants fail-closed.

## Finding matrix

| ID | Status |
|----|--------|
| AUTH_DECISION_MINTS_INTENT_ID | FIXED |
| AUTH_DECISION_MINTS_POSITION_ID | FIXED |
| AUTH_DECISION_RISK_BYPASS | FIXED |
| AUTH_NO_DECISION_EXECUTION_BRIDGE | FIXED |
| AUTH_COST_MODEL_VERSION_MISMATCH | FIXED |
| AUTH_DECISION_NO_COST_VERSION_BIND | FIXED |
| VOCAB_MONITORING_SKIP_EXIT | FIXED |
| ADV_DECISION_APPROVED_TWICE | FIXED |
| ADV_INTENT_REPLAY_AFTER_RESTART | FIXED |
| ADV_PARTIAL_FILL_DURING_DECISION_TRANSITION | FIXED |
| ADV_COST_MODEL_VERSION_MISMATCH | FIXED |
| ADV_POSITION_CLOSED_DECISION_MONITORING | FIXED |
| ADV_DECISION_CLOSED_POSITION_OPEN | FIXED |
| ADV_SAME_BAR_STOP_TARGET | FIXED |

## Metrics

- false_PASS_count (targeted): **0**
- authority_conflict_count (targeted): **0**
- missing_negative_test_count (targeted): **0**
- critical_remaining: **0**
- tests_pass: `tests/test_r1_ab_decision_execution_remediation_v11_1.py` + `tests/test_decision_lifecycle_v11.py` = **42**
- ci_gate: **PASS**

## Owned paths

- `backend/nexus_decision/execution_bridge.py` (new)
- `backend/nexus_decision/orchestrator.py`
- `backend/nexus_decision/state_machine.py`
- `backend/nexus_decision/decision_object.py`
- `backend/nexus_decision/__init__.py`
- `backend/nexus_strategy_engine/cost_semantics.py` (re-export canonical COST_MODEL_VERSION)
- `tests/test_r1_ab_decision_execution_remediation_v11_1.py`
- `tools/architecture/ci_gate_decision_execution_bridge.py`
- `artifacts/readiness/immutable/v11_1_r1_ab_remediation/`

## Notes

- Coordinated conceptually with C1 (cost version), C2 (lifecycle vocabulary), C5 (execution shim non-authoritative).
- Intent/Position IDs only from `NEXUS_EXECUTION_ORCHESTRATOR_ADAPTER_V1` → `AutonomousExecutionSimulatorV11`.
- Same-bar stop/target remains `BLOCKED_AMBIGUOUS` via canonical fill engine only.

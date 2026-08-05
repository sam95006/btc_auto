# V11 R1 Decision + Execution Review

Generated: 2026-08-05T04:02:06Z

## Return matrix

- false_PASS_count: **7**
- authority_conflict_count: **7**
- missing_negative_test_count: **8**
- critical_count: **12**
- high_count: **5**
- integration_recommendation: **BLOCK_INTEGRATION_CRITICAL_CROSS_LANE_GAPS**

## Critical findings

- `AUTH_DECISION_MINTS_INTENT_ID` — DecisionLifecycleOrchestrator assigns intent_id locally on APPROVED_SIMULATED without creating backend.nexus_execution OrderIntent via the canonical adapter.
- `AUTH_DECISION_MINTS_POSITION_ID` — DecisionLifecycleOrchestrator assigns position_id on record→MONITORING without PositionRecord authority from AutonomousExecutionSimulatorV11.
- `AUTH_DECISION_RISK_BYPASS` — Decision decide() accepts an opaque deterministic_risk_result dict and never invokes backend.nexus_execution.risk_gates. Dual risk authority.
- `AUTH_COST_MODEL_VERSION_MISMATCH` — Multiple cost model version strings observed: {'nexus_execution': 'founder-conservative-v1-1-2026-08-05', 'backend\\nexus_strategy_engine\\cost_semantics.py': 'NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1', 'backend\\nexus_strategy_engine\\cost_semantics.py:COST_MODEL_VERSION': 'NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1', 'base:backend\\nexus_strategy_engine\\cost_semantics.py:COST_MODEL_VERSION': 'NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1', 'base:backend\\nexus_strategy_engine\\cost_semantics.py:proxy': 'NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1'}
- `AUTH_NO_DECISION_EXECUTION_BRIDGE` — No Decision↔Intent↔Position bridge module exists. Lanes A and B are authority-isolated; mapping invariants are unenforceable at runtime.
- `VOCAB_MONITORING_SKIP_EXIT` — Decision MONITORING may transition to UNDER_REVIEW (then CLOSED) without EXITED, enabling Decision CLOSED while a synthetic position_id remains conceptually open.
- `ADV_DECISION_APPROVED_TWICE` — Per-decision idempotency blocks re-approve with a new key, but nothing prevents two Decision Objects approving the same candidate_id with distinct intent_ids.
- `ADV_INTENT_REPLAY_AFTER_RESTART` — Decision intent_id survives restart and decide replay is idempotent, but the Intent is a string token unbound to OrderIntent.idempotency_key — execution has zero knowledge of it.
- `ADV_PARTIAL_FILL_DURING_DECISION_TRANSITION` — Lane B can partially fill while Decision sits in APPROVED_SIMULATED; Decision freely advances to MONITORING and mints an unrelated position_id. No joint lock.
- `ADV_COST_MODEL_VERSION_MISMATCH` — Canonical COST_MODEL_VERSION=founder-conservative-v1-1-2026-08-05; divergent versions=['NEXUS_CONSERVATIVE_EXECUTION_PROXY_V1_1']. Decision approval does not bind or reject on cost version.
- `ADV_POSITION_CLOSED_DECISION_MONITORING` — Forbidden combination Position CLOSED + Decision MONITORING is constructible because Decision position_id is a decorative string, not a PositionRecord reference.
- `ADV_DECISION_CLOSED_POSITION_OPEN` — Decision MONITORING→UNDER_REVIEW→CLOSED skips EXITED; synthetic position_id can remain OPEN with qty>0. Critical cross-lifecycle invariant absent.

## High findings

- `AUTH_DECISION_NO_COST_VERSION_BIND` — Decision APPROVED_SIMULATED does not bind or validate COST_MODEL_VERSION; approval evidence cannot prove which cost authority would price the Intent.
- `AUTH_DECISION_CHECKPOINT_PARALLEL` — DecisionCheckpointStore is a parallel checkpoint authority vs Session/recovery envelopes (Lane H MULTI_SCOPE_AUTHORITY_CHECKPOINT).
- `VOCAB_SHARED_CLOSED` — CLOSED exists in both Decision and Position vocabularies with different semantics; no cross-lifecycle invariant enforces Decision CLOSED ⇒ Position terminal.
- `VOCAB_SHARED_BLOCKED_AMBIGUOUS` — BLOCKED_AMBIGUOUS is shared by Decision and Position state machines without a joint recovery contract.
- `ADV_SAME_BAR_STOP_TARGET` — Fill engine blocks same-bar stop/target (adverse-first), but Decision MONITORING heartbeat proceeds with no linkage to the blocked order.

## Policy

- Reviewer-owned paths only
- Lane A/B implementation paths untouched
- No Draft PR if gh missing

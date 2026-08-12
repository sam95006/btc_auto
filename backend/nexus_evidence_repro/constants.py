"""Constants for V12 evidence reproducibility envelopes."""
from __future__ import annotations

REPRO_SCHEMA = "nexus_evidence_reproducibility_v12"
REPRO_SCHEMA_VERSION = 1

# Matches authority_registry domain=risk authority_id.
RISK_GATES_VERSION = "private_core.risk.gates_v1_1"
RISK_GATES_AUTHORITY = "backend.nexus_execution.risk_gates.evaluate_intent"

PROOF_DIMENSIONS: tuple[str, ...] = (
    "input_evidence_hashes",
    "code_version",
    "cost_version",
    "risk_version",
    "checkpoint_version",
    "ai_provider_model_identifiers",
    "deterministic_replay_result",
    "classification_provenance",
)

REQUIRED_ENVELOPE_KEYS: tuple[str, ...] = (
    "schema",
    "schema_version",
    "decision_id",
    "terminal_status",
    "input_evidence_hashes",
    "evidence_binding_hash",
    "code_version",
    "cost_version",
    "risk_version",
    "checkpoint_version",
    "ai_provider_model_identifiers",
    "classification_provenance",
    "replay_fingerprint",
    "simulated_only",
    "exchange_write",
    "demo_order",
    "learning_claim",
    "profitability_claim",
)

HARD_BAN_FLAGS = {
    "simulated_only": True,
    "exchange_write": False,
    "demo_order": False,
    "learning_claim": False,
    "profitability_claim": False,
    "formal_walk_forward_executed": False,
    "oos_executed": False,
    "mainnet": False,
    "real_money": False,
}

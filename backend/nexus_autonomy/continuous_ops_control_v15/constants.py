"""V15-J Continuous Autonomy Operations Control — shared constants.

Founder-only control plane. Mutating ops require Founder auth proof,
idempotency, ledger event, checkpoint, and deterministic safety gate.
No exchange writes. No *_status.json artifacts for this lane.
"""
from __future__ import annotations

SCHEMA = "v15_continuous_autonomy_ops"
SCHEMA_PASS1 = "v15_continuous_autonomy_ops_pass1"
SCHEMA_PASS2 = "v15_continuous_autonomy_ops_pass2"
PROGRAM_ID = "NEXUS_V15_CONTINUOUS_AUTONOMY_OPS"
LANE = "V15-J"
BRANCH = "feature/v15-continuous-autonomy-operations"
BASE_HEAD = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"

PASS = "PASS"
FAIL = "FAIL"
DENIED = "DENIED"
DUPLICATE = "DUPLICATE_IGNORED"
BLOCKED = "BLOCKED"

# Control lifecycle states (private; no exchange modes)
STATE_COLD = "COLD"
STATE_STARTING = "STARTING"
STATE_RUNNING = "RUNNING"
STATE_PAUSING = "PAUSING"
STATE_PAUSED = "PAUSED"
STATE_SAFE_STOPPING = "SAFE_STOPPING"
STATE_STOPPED = "STOPPED"
STATE_RECOVERING = "RECOVERING"
STATE_KILLED = "KILLED"
STATE_BLOCKED = "BLOCKED"

MUTATING_OPS: tuple[str, ...] = (
    "start",
    "pause",
    "resume",
    "safe_stop",
    "kill",
    "recover",
)

READ_OPS: tuple[str, ...] = (
    "health",
    "storage",
    "provider_capacity",
    "capture_health",
    "decision_lifecycle",
    "execution_lifecycle",
    "reflection_lifecycle",
    "lesson_gate",
    "qualification_blocks",
)

CONTROL_BLOCKS: tuple[str, ...] = MUTATING_OPS + READ_OPS

# Qualification remains blocked — V15-J never advances qualification.
QUALIFICATION_STAGE_ORDER: tuple[str, ...] = (
    "candidate_freeze",
    "replay",
    "walk_forward",
    "risk_review",
    "oos_reservation",
    "demo_eligibility",
)

PRESERVED_FACTS = {
    "exchange_write_attempt_count": 0,
    "demo_order_count": 0,
    "shadow_order_count": 0,
    "mainnet_attempt_count": 0,
    "real_money_attempt_count": 0,
    "formal_walk_forward_executed": False,
    "oos_reservation_created": False,
    "oos_executed": False,
    "oos_consumed": False,
    "strategy_promoted": False,
    "PR27_merged": False,
    "qualification_advanced": False,
}

HARD_BANS = {
    "demo": True,
    "shadow": True,
    "exchange_write": True,
    "mainnet": True,
    "real_money": True,
    "PR27_merge": True,
    "formal_walk_forward_execution": True,
    "real_oos_reservation": True,
    "real_oos_execution": True,
    "real_oos_consumption": True,
    "strategy_promotion": True,
    "fabricated_edge": True,
    "G_source_deletion": True,
}

OWNED_PATHS = (
    "backend/nexus_autonomy/continuous_ops_control_v15/",
    "tools/research/run_continuous_autonomy_ops_v15.py",
    "tests/test_continuous_autonomy_ops_v15.py",
    "artifacts/readiness/immutable/v15_continuous_autonomy_ops/",
)

PROOF_IDS_PASS1: tuple[str, ...] = (
    "start_with_founder_auth",
    "pause_resume_cycle",
    "safe_stop_and_recover",
    "kill_switch_terminal",
    "health_storage_provider_capture_blocks",
    "decision_execution_reflection_lesson_blocks",
    "qualification_blocks_remain_blocked",
    "mutating_requires_auth_idempotency_ledger_checkpoint_gate",
    "exchange_write_hard_banned",
)

PROOF_IDS_PASS2: tuple[str, ...] = (
    "neg_missing_founder_auth",
    "neg_spoofed_founder_auth",
    "neg_idempotency_replay",
    "neg_exchange_write_trap",
    "neg_qualification_advance_refused",
    "neg_kill_blocks_resume",
    "neg_unsafe_transition_refused",
    "neg_no_status_json_artifact",
)

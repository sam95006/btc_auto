"""V12 Disaster Recovery Control — shared constants.

Hard bans: no Demo / exchange write / mainnet; no PR27 merge; no silent recovery guesses.
Builds on V11.1 durability: false LKG banned, checksummed ledger position, owner-only duplicate intent.
"""
from __future__ import annotations

SCHEMA = "v12_disaster_recovery_control"
PROGRAM_ID = "NEXUS_V12_DISASTER_RECOVERY_CONTROL"
LANE = "V12-D"
BRANCH = "feature/v12-disaster-recovery-control"

PASS = "PASS"
FAIL = "FAIL"
BLOCKED_AMBIGUOUS_STATE = "BLOCKED_AMBIGUOUS_STATE"
RECOVERED_EXACT = "RECOVERED_EXACT"
RECOVERED_LAST_KNOWN_GOOD = "RECOVERED_LAST_KNOWN_GOOD"
CORRUPTION_DETECTED = "CORRUPTION_DETECTED"
KILL_SWITCH_TRIGGERED = "TRIGGERED"

# Control lifecycle (private; no exchange modes)
STATE_COLD = "COLD"
STATE_WARM = "WARM"
STATE_RECOVERING = "RECOVERING"
STATE_RUNNING = "RUNNING"
STATE_BLOCKED = "BLOCKED"
STATE_KILLED = "KILLED"

PROOF_IDS: tuple[str, ...] = (
    "cold_restart",
    "warm_restart",
    "lkg_restore",
    "checkpoint_restore",
    "ledger_tail_reconciliation",
    "ambiguous_state_blocking",
    "kill_switch_after_recovery",
    "storage_migration_recovery",
)

V11_1_INVARIANT_IDS: tuple[str, ...] = (
    "false_lkg_banned",
    "position_vs_checksummed_ledger",
    "owner_only_duplicate_intent",
)

PRESERVED_FACTS = {
    "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED": True,
    "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST": True,
    "old_trading_db_recovered": False,
    "wallet_delta_attribution_changed": False,
    "silent_recovery_guess": False,
    "evidence_loss_claimed_without_proof": False,
    "demo_order_count": 0,
    "exchange_write_attempt_count": 0,
    "mainnet_attempt_count": 0,
    "PR27_merged": False,
}

HARD_BANS = {
    "demo": True,
    "exchange_write": True,
    "mainnet": True,
    "PR27_merge": True,
    "silent_recovery_guess": True,
}

STORAGE_SCHEMA_V12 = "durability_ledger_v12_control"
STORAGE_SCHEMA_LEGACY = "durability_ledger_v2"

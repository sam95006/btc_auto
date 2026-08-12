"""Shared constants for Durability V2 / DR V2."""
from __future__ import annotations

SCHEMA_VERSION = "durability_ledger_v2"
GENESIS_HASH = "0" * 64

BLOCKED_AMBIGUOUS_STATE = "BLOCKED_AMBIGUOUS_STATE"
CORRUPTION_DETECTED = "CORRUPTION_DETECTED"
RECOVERED_EXACT = "RECOVERED_EXACT"
RECOVERED_LAST_KNOWN_GOOD = "RECOVERED_LAST_KNOWN_GOOD"
RECOVERY_FAILED = "RECOVERY_FAILED"
SNAPSHOT_OK = "SNAPSHOT_OK"
PASS = "PASS"
FAIL = "FAIL"

# Scale capability (full targets). Harness defaults may be reduced via env.
FULL_LEDGER_EVENTS = 1_000_000
FULL_SNAPSHOTS = 1_000
FULL_RECOVERY_DRILLS = 100

PRESERVED_FACTS = {
    "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED": True,
    "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST": True,
    "old_trading_db_recovered": False,
    "wallet_delta_attribution_changed": False,
    "silent_recovery_guess": False,
    "evidence_loss_claimed_without_proof": False,
}

INJECTION_KINDS = (
    "power_loss",
    "partial_write",
    "fsync_interruption",
    "truncation",
    "bit_corruption",
    "hash_chain_corruption",
    "snapshot_corruption",
    "latest_missing",
    "lkg_corruption",
    "concurrent_append",
    "duplicate_event",
    "out_of_order",
    "clock_rollback",
    "disk_soft_limit",
    "disk_hard_limit",
    "process_kill_during_checkpoint",
)

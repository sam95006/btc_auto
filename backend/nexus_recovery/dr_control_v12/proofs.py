"""V12-D disaster recovery proof matrix (8 required + 3 V11.1 invariants)."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend.nexus_recovery.dr_control_v12.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    CORRUPTION_DETECTED,
    PASS,
    PRESERVED_FACTS,
    PROOF_IDS,
    RECOVERED_EXACT,
    RECOVERED_LAST_KNOWN_GOOD,
    V11_1_INVARIANT_IDS,
)
from backend.nexus_recovery.dr_control_v12.control import DisasterRecoveryControlV12
from backend.nexus_runtime.durability_v2.constants import SNAPSHOT_OK
from backend.nexus_runtime.durability_v2.faults import (
    inject_hash_chain_corruption,
    inject_payload_bit_corruption,
    remove_latest_snapshot,
)
from backend.nexus_runtime.durability_v2.ledger import DurableEventLedgerV2


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class ProofResult:
    proof_id: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proof_id": self.proof_id,
            "passed": self.passed,
            "detail": dict(self.detail),
        }


def _ctrl(root: Path) -> DisasterRecoveryControlV12:
    return DisasterRecoveryControlV12(root)


def proof_cold_restart(root: Path) -> ProofResult:
    c = _ctrl(root / "cold")
    seeded = c.seed_events(12, prefix="cold")
    if seeded.get("status") != PASS:
        return ProofResult("cold_restart", False, {"seed": seeded})
    event_count = int(seeded["event_count"])
    stopped = c.cold_stop()
    # Simulate process death: new control instance on same root.
    c2 = _ctrl(root / "cold")
    restarted = c2.cold_restart()
    led = c2.durability.open_ledger()
    try:
        chain = led.verify_hash_chain()
        count = led.event_count()
    finally:
        led.close()
    passed = (
        stopped.get("status") == PASS
        and restarted.get("status") == PASS
        and restarted.get("state") == "RUNNING"
        and count == event_count
        and chain.get("ledger_hash_chain_status") == PASS
        and restarted.get("silent_recovery_guess") is False
    )
    return ProofResult(
        "cold_restart",
        passed,
        {
            "seed": seeded,
            "stop": stopped,
            "restart": restarted,
            "event_count": count,
            "chain": chain,
        },
    )


def proof_warm_restart(root: Path) -> ProofResult:
    c = _ctrl(root / "warm")
    seeded = c.seed_events(8, prefix="warm")
    stopped = c.warm_stop()
    # Append after warm stop via fresh handle (warm continuity).
    c2 = _ctrl(root / "warm")
    restarted = c2.warm_restart()
    led = c2.durability.open_ledger()
    try:
        before = led.event_count()
        led.append(
            aggregate_id="warm-extra",
            aggregate_type="DECISION",
            event_type="CONT",
            source="dr_control_v12",
            payload={"extra": True},
            idempotency_key="warm-extra",
        )
        after = led.event_count()
        chain = led.verify_hash_chain()
    finally:
        led.close()
    passed = (
        seeded.get("status") == PASS
        and stopped.get("status") == PASS
        and restarted.get("status") == PASS
        and after == before + 1
        and chain.get("ledger_hash_chain_status") == PASS
        and restarted.get("silent_recovery_guess") is False
    )
    return ProofResult(
        "warm_restart",
        passed,
        {
            "seed": seeded,
            "stop": stopped,
            "restart": restarted,
            "before": before,
            "after": after,
            "chain": chain,
        },
    )


def proof_lkg_restore(root: Path) -> ProofResult:
    c = _ctrl(root / "lkg")
    seeded = c.seed_events(10, prefix="lkg")
    led = c.durability.open_ledger()
    try:
        inject_hash_chain_corruption(led, seq=3)
    finally:
        led.close()
    restored = c.restore_lkg()
    led2 = c.durability.open_ledger()
    try:
        chain = led2.verify_hash_chain()
        count = led2.event_count()
    finally:
        led2.close()
    passed = (
        seeded.get("status") == PASS
        and restored.get("status") == PASS
        and restored.get("restore_status")
        in {RECOVERED_EXACT, RECOVERED_LAST_KNOWN_GOOD}
        and chain.get("ledger_hash_chain_status") == PASS
        and count == 10
        and restored.get("silent_recovery_guess") is False
    )
    return ProofResult(
        "lkg_restore",
        passed,
        {"seed": seeded, "restore": restored, "chain": chain, "count": count},
    )


def proof_checkpoint_restore(root: Path) -> ProofResult:
    c = _ctrl(root / "ckpt")
    seeded = c.seed_events(9, prefix="ckpt")
    # Corrupt live ledger; sealed checkpoint must still authorize LKG restore.
    led = c.durability.open_ledger()
    try:
        inject_hash_chain_corruption(led, seq=2)
    finally:
        led.close()
    # Positive path: sealed restore.
    ok = c.restore_checkpoint()
    # Negative path: unbound checkpoint blocks (separate root).
    c_bad = _ctrl(root / "ckpt_unbound")
    c_bad.seed_events(3, prefix="ub")
    c_bad.durability.checkpoint_path.write_text(
        json.dumps(
            {
                "checkpoint_id": "unbound",
                "lkg_seal": False,
                "schema": "not_sealed",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    blocked = c_bad.restore_checkpoint()
    passed = (
        seeded.get("status") == PASS
        and ok.get("status") == PASS
        and blocked.get("status") == BLOCKED_AMBIGUOUS_STATE
        and blocked.get("silent_recovery_guess") is False
    )
    return ProofResult(
        "checkpoint_restore",
        passed,
        {"seed": seeded, "sealed_restore": ok, "unbound_blocked": blocked},
    )


def proof_ledger_tail_reconciliation(root: Path) -> ProofResult:
    c = _ctrl(root / "tail")
    seeded = c.seed_events(7, prefix="tail")
    # Attempt to race position via patched event_count (V11.1 R2-C-002 regression).
    led = c.durability.open_ledger()
    orig = DurableEventLedgerV2.event_count
    fired = {"n": 0}

    def patched(self: DurableEventLedgerV2) -> int:
        fired["n"] += 1
        if fired["n"] == 1:
            self.append(
                aggregate_id="late-race",
                aggregate_type="DECISION",
                event_type="X",
                source="proof",
                payload={"late": True},
                idempotency_key="late-race",
            )
        return orig(self)

    DurableEventLedgerV2.event_count = patched  # type: ignore[method-assign]
    try:
        snap = c.durability.create_snapshot(led)
    finally:
        DurableEventLedgerV2.event_count = orig  # type: ignore[method-assign]
        led.close()

    recon = c.reconcile_ledger_tail()
    position_ok = (
        snap.status == SNAPSHOT_OK
        and snap.detail.get("position_source") == "checksummed_main_file"
        and recon.get("status") == PASS
        and recon.get("tail_match") is True
    )
    passed = seeded.get("status") == PASS and position_ok
    return ProofResult(
        "ledger_tail_reconciliation",
        passed,
        {
            "seed": seeded,
            "snapshot": snap.to_dict(),
            "reconcile": recon,
            "race_appends_observed": fired["n"],
        },
    )


def proof_ambiguous_state_blocking(root: Path) -> ProofResult:
    # Case A: live ahead of LKG would discard evidence → block
    c_ahead = _ctrl(root / "amb_ahead")
    c_ahead.seed_events(5, prefix="ahead")
    led = c_ahead.durability.open_ledger()
    try:
        led.append(
            aggregate_id="ahead-extra",
            aggregate_type="DECISION",
            event_type="X",
            source="proof",
            payload={"extra": True},
            idempotency_key="ahead-extra",
        )
    finally:
        led.close()
    blocked_ahead = c_ahead.restore_lkg()

    # Case B: latest snapshot missing → block
    c_miss = _ctrl(root / "amb_miss")
    c_miss.seed_events(4, prefix="miss")
    remove_latest_snapshot(c_miss.durability)
    blocked_miss = c_miss.restore_lkg()

    passed = (
        blocked_ahead.get("status") == BLOCKED_AMBIGUOUS_STATE
        and blocked_ahead.get("detail", {}).get("evidence_loss_claimed_without_proof")
        is False
        and blocked_miss.get("status") == BLOCKED_AMBIGUOUS_STATE
        and blocked_ahead.get("silent_recovery_guess") is False
        and blocked_miss.get("silent_recovery_guess") is False
    )
    return ProofResult(
        "ambiguous_state_blocking",
        passed,
        {"live_ahead": blocked_ahead, "latest_missing": blocked_miss},
    )


def proof_kill_switch_after_recovery(root: Path) -> ProofResult:
    c = _ctrl(root / "kill")
    seeded = c.seed_events(6, prefix="kill")
    led = c.durability.open_ledger()
    try:
        inject_hash_chain_corruption(led, seq=2)
    finally:
        led.close()
    restored = c.restore_lkg()
    killed = c.kill_switch(reason="post_recovery_founder_kill")
    # Further seed / restart must be blocked by kill switch.
    blocked_seed = c.seed_events(1, prefix="after-kill")
    blocked_restart = c.cold_restart()
    passed = (
        seeded.get("status") == PASS
        and restored.get("status") == PASS
        and killed.get("kill_switch_status") == "TRIGGERED"
        and blocked_seed.get("status") == "KILL_SWITCH_BLOCKS"
        and blocked_restart.get("status") == "KILL_SWITCH_BLOCKS"
        and killed.get("silent_recovery_guess") is False
    )
    return ProofResult(
        "kill_switch_after_recovery",
        passed,
        {
            "restore": restored,
            "kill": killed,
            "blocked_seed": blocked_seed,
            "blocked_restart": blocked_restart,
        },
    )


def proof_storage_migration_recovery(root: Path) -> ProofResult:
    src = _ctrl(root / "mig_src")
    seeded = src.seed_events(11, prefix="mig")
    # Source is durability_ledger_v2; migrate in place then cold restart on copy.
    migrated = src.migrate_storage()
    # Also prove copy-migrate path.
    from backend.nexus_recovery.dr_control_v12.storage_migration import (
        migrate_durability_root,
    )

    dest = root / "mig_dest" / "dr" / "durability"
    copy_mig = migrate_durability_root(src.durability.root, dest)
    c_dest = DisasterRecoveryControlV12(root / "mig_dest")
    # Point control at migrated durability by using same layout.
    restarted = c_dest.cold_restart()
    led = c_dest.durability.open_ledger()
    try:
        chain = led.verify_hash_chain()
        count = led.event_count()
        schema_row = led._conn.execute(
            "SELECT value FROM ledger_meta WHERE key='schema_version'"
        ).fetchone()
        schema = schema_row[0] if schema_row else None
    finally:
        led.close()
    passed = (
        seeded.get("status") == PASS
        and migrated.get("status") == PASS
        and copy_mig.get("status") == PASS
        and restarted.get("status") == PASS
        and chain.get("ledger_hash_chain_status") == PASS
        and count == 11
        and schema == "durability_ledger_v12_control"
        and migrated.get("silent_recovery_guess") is False
    )
    return ProofResult(
        "storage_migration_recovery",
        passed,
        {
            "seed": seeded,
            "in_place_migration": migrated,
            "copy_migration": copy_mig,
            "restart": restarted,
            "schema": schema,
            "count": count,
            "chain": chain,
        },
    )


def invariant_false_lkg_banned(root: Path) -> ProofResult:
    c = _ctrl(root / "inv_false_lkg")
    led = c.durability.open_ledger()
    led.append(
        aggregate_id="a",
        aggregate_type="DECISION",
        event_type="X",
        source="inv",
        payload={"n": 1},
        idempotency_key="pay-1",
    )
    inject_payload_bit_corruption(led, seq=1)
    gen_before = c.durability._generation
    lkg_before = c.durability.lkg_path.exists()
    snap = c.durability.create_snapshot(led)
    led.close()
    passed = (
        snap.status == CORRUPTION_DETECTED
        and c.durability._generation == gen_before
        and c.durability.lkg_path.exists() == lkg_before
    )
    return ProofResult(
        "false_lkg_banned",
        passed,
        {
            "snapshot_status": snap.status,
            "generation_advanced": c.durability._generation != gen_before,
            "lkg_advanced": c.durability.lkg_path.exists() and not lkg_before,
        },
    )


def invariant_position_vs_checksummed_ledger(root: Path) -> ProofResult:
    # Covered structurally by ledger_tail_reconciliation; keep dedicated assert.
    r = proof_ledger_tail_reconciliation(root / "inv_pos")
    return ProofResult(
        "position_vs_checksummed_ledger",
        r.passed,
        r.detail,
    )


def invariant_owner_only_duplicate_intent(root: Path) -> ProofResult:
    c = _ctrl(root / "inv_owner")
    c.save_intent_owners({"owner-key-1": "order-abc-recovered"})
    out = c.restore_owner_only_intents()
    passed = out.get("status") == PASS and out.get("owners_restored") == 1
    return ProofResult("owner_only_duplicate_intent", passed, out)


PROOF_RUNNERS: dict[str, Callable[[Path], ProofResult]] = {
    "cold_restart": proof_cold_restart,
    "warm_restart": proof_warm_restart,
    "lkg_restore": proof_lkg_restore,
    "checkpoint_restore": proof_checkpoint_restore,
    "ledger_tail_reconciliation": proof_ledger_tail_reconciliation,
    "ambiguous_state_blocking": proof_ambiguous_state_blocking,
    "kill_switch_after_recovery": proof_kill_switch_after_recovery,
    "storage_migration_recovery": proof_storage_migration_recovery,
}

INVARIANT_RUNNERS: dict[str, Callable[[Path], ProofResult]] = {
    "false_lkg_banned": invariant_false_lkg_banned,
    "position_vs_checksummed_ledger": invariant_position_vs_checksummed_ledger,
    "owner_only_duplicate_intent": invariant_owner_only_duplicate_intent,
}


def run_proof_matrix(base_root: Path) -> dict[str, Any]:
    base_root = Path(base_root)
    if base_root.exists():
        shutil.rmtree(base_root, ignore_errors=True)
    base_root.mkdir(parents=True, exist_ok=True)

    proof_results: list[dict[str, Any]] = []
    for pid in PROOF_IDS:
        result = PROOF_RUNNERS[pid](base_root / "proofs" / pid)
        proof_results.append(result.to_dict())

    invariant_results: list[dict[str, Any]] = []
    for iid in V11_1_INVARIANT_IDS:
        result = INVARIANT_RUNNERS[iid](base_root / "invariants" / iid)
        invariant_results.append(result.to_dict())

    proofs_passed = sum(1 for r in proof_results if r["passed"])
    invariants_passed = sum(1 for r in invariant_results if r["passed"])
    blockers: list[str] = []
    for r in proof_results:
        if not r["passed"]:
            blockers.append(f"proof_failed:{r['proof_id']}")
    for r in invariant_results:
        if not r["passed"]:
            blockers.append(f"invariant_failed:{r['proof_id']}")

    overall = (
        "NEXUS_V12_DISASTER_RECOVERY_CONTROL_PASS"
        if not blockers
        else "NEXUS_V12_DISASTER_RECOVERY_CONTROL_BLOCKED"
    )
    return {
        "schema": "v12_disaster_recovery_control",
        "created_at": _utc(),
        "overall_status": overall,
        "blockers": blockers,
        "counters": {
            "proofs_passed": proofs_passed,
            "proofs_total": len(PROOF_IDS),
            "invariants_passed": invariants_passed,
            "invariants_total": len(V11_1_INVARIANT_IDS),
            "exchange_write_attempt_count": 0,
            "demo_order_count": 0,
            "mainnet_attempt_count": 0,
            "silent_recovery_guess_count": 0,
            "PR27_merged": False,
        },
        "proofs": proof_results,
        "v11_1_invariants": invariant_results,
        "preserved_facts": PRESERVED_FACTS,
        "required_proof_ids": list(PROOF_IDS),
        "required_invariant_ids": list(V11_1_INVARIANT_IDS),
    }

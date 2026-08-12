"""Storage migration helpers for V12 DR Control.

Migrates a sealed durability snapshot / live ledger meta from V2 schema
markers to V12 control schema without silent repair of corrupted bytes.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_recovery.dr_control_v12.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    CORRUPTION_DETECTED,
    PASS,
    STORAGE_SCHEMA_LEGACY,
    STORAGE_SCHEMA_V12,
)
from backend.nexus_runtime.durability_v2.engine import RuntimeDurabilityV2, file_sha256
from backend.nexus_runtime.durability_v2.ledger import DurableEventLedgerV2


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_schema_version(ledger_path: Path) -> str | None:
    if not ledger_path.exists():
        return None
    conn = sqlite3.connect(f"file:{ledger_path.as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute(
            "SELECT value FROM ledger_meta WHERE key='schema_version'"
        ).fetchone()
        return str(row[0]) if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def migrate_ledger_schema(
    ledger_path: Path,
    *,
    target_schema: str = STORAGE_SCHEMA_V12,
    allow_from: tuple[str, ...] = (STORAGE_SCHEMA_LEGACY, "durability_ledger_v2"),
) -> dict[str, Any]:
    """Bump ledger_meta schema_version when source is a known legacy marker.

    Never invents events. Corruption / unknown schema → BLOCKED_AMBIGUOUS_STATE.
    """
    if not ledger_path.exists():
        return {
            "status": BLOCKED_AMBIGUOUS_STATE,
            "reason": "ledger_missing_for_migration",
        }
    # Integrity first — refuse to migrate a corrupt file.
    probe = DurableEventLedgerV2(ledger_path)
    try:
        integrity = probe.integrity_check()
        chain = probe.verify_hash_chain()
        if integrity != "ok" or chain.get("ledger_hash_chain_status") != "PASS":
            return {
                "status": CORRUPTION_DETECTED,
                "reason": "refuse_migrate_corrupt_ledger",
                "integrity": integrity,
                "chain": chain,
            }
        count = probe.event_count()
    finally:
        probe.close()

    current = read_schema_version(ledger_path)
    if current == target_schema:
        return {
            "status": PASS,
            "reason": "already_at_target",
            "schema_version": current,
            "event_count": count,
            "migrated": False,
        }
    if current not in allow_from and current is not None:
        return {
            "status": BLOCKED_AMBIGUOUS_STATE,
            "reason": "unknown_source_schema",
            "schema_version": current,
            "silent_recovery_guess": False,
        }

    def _upsert_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
        cur = conn.execute("UPDATE ledger_meta SET value=? WHERE key=?", (value, key))
        if cur.rowcount == 0:
            conn.execute(
                "INSERT INTO ledger_meta(key, value) VALUES (?, ?)",
                (key, value),
            )

    conn = sqlite3.connect(str(ledger_path))
    try:
        _upsert_meta(conn, "schema_version", target_schema)
        _upsert_meta(conn, "migrated_at", _utc())
        _upsert_meta(conn, "migrated_from", current or "missing")
        conn.commit()
    finally:
        conn.close()

    # Re-verify after meta bump.
    probe2 = DurableEventLedgerV2(ledger_path)
    try:
        chain2 = probe2.verify_hash_chain()
        if chain2.get("ledger_hash_chain_status") != "PASS":
            return {
                "status": CORRUPTION_DETECTED,
                "reason": "post_migration_chain_failed",
                "chain": chain2,
            }
        count2 = probe2.event_count()
    finally:
        probe2.close()

    if count2 != count:
        return {
            "status": BLOCKED_AMBIGUOUS_STATE,
            "reason": "migration_changed_event_count",
            "before": count,
            "after": count2,
            "silent_recovery_guess": False,
        }
    return {
        "status": PASS,
        "reason": "schema_bumped",
        "schema_version": target_schema,
        "migrated_from": current,
        "event_count": count2,
        "migrated": True,
    }


def migrate_durability_root(source_root: Path, dest_root: Path) -> dict[str, Any]:
    """Copy a durability V2 root into a V12 control root and migrate schema.

    Requires LKG + sealed checkpoint when present; refuses partial roots.
    """
    source = RuntimeDurabilityV2(source_root)
    dest_root = Path(dest_root)
    if dest_root.exists() and any(dest_root.iterdir()):
        return {
            "status": BLOCKED_AMBIGUOUS_STATE,
            "reason": "dest_root_not_empty",
            "silent_recovery_guess": False,
        }
    dest_root.mkdir(parents=True, exist_ok=True)

    if not source.ledger_path.exists():
        return {
            "status": BLOCKED_AMBIGUOUS_STATE,
            "reason": "source_ledger_missing",
            "silent_recovery_guess": False,
        }

    # Copy live ledger + LKG + checkpoint + snapshots tree.
    dest = RuntimeDurabilityV2(dest_root)
    shutil.copy2(source.ledger_path, dest.ledger_path)
    if source.lkg_path.exists():
        shutil.copy2(source.lkg_path, dest.lkg_path)
    if source.checkpoint_path.exists():
        shutil.copy2(source.checkpoint_path, dest.checkpoint_path)
    if source.meta_path.exists():
        shutil.copy2(source.meta_path, dest.meta_path)
    if source.backup_root.exists():
        shutil.copytree(source.backup_root, dest.backup_root, dirs_exist_ok=True)

    # Refresh LKG checksum if LKG points at source absolute path.
    if dest.lkg_path.exists():
        pointer = json.loads(dest.lkg_path.read_text(encoding="utf-8"))
        old_snap = Path(pointer.get("snapshot_path") or "")
        # Prefer matching generation under dest snapshots.
        gen = int(pointer.get("generation") or 0)
        local_snap = dest.backup_root / f"snapshot_{gen:06d}" / "event_ledger_v2.sqlite3"
        if local_snap.exists():
            pointer["snapshot_path"] = str(local_snap)
            pointer["snapshot_checksum"] = file_sha256(local_snap)
            pointer["migration"] = {
                "from": str(old_snap),
                "to": str(local_snap),
                "at": _utc(),
            }
            dest.lkg_path.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
            if dest.checkpoint_path.exists():
                ckpt = json.loads(dest.checkpoint_path.read_text(encoding="utf-8"))
                ckpt["snapshot_path"] = str(local_snap)
                ckpt["snapshot_checksum"] = pointer["snapshot_checksum"]
                dest.checkpoint_path.write_text(
                    json.dumps(ckpt, indent=2) + "\n", encoding="utf-8"
                )
        elif old_snap.exists():
            # Keep absolute path only if file still reachable; do not invent.
            pass
        else:
            return {
                "status": BLOCKED_AMBIGUOUS_STATE,
                "reason": "lkg_snapshot_unreachable_after_copy",
                "silent_recovery_guess": False,
            }

    mig = migrate_ledger_schema(dest.ledger_path)
    if mig.get("status") != PASS:
        return mig

    seal = dest.validate_checkpoint_seal()
    return {
        "status": PASS,
        "migration": mig,
        "checkpoint_seal": seal,
        "dest_root": str(dest_root),
        "event_count": mig.get("event_count"),
    }

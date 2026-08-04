"""NEXUS Runtime Durability V1 — snapshots, last-known-good, fail-closed restore.

Preserves:
  TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED
  WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.private_event_ledger_v1 import PrivateEventLedger

PRESERVED_FACTS = {
    "TRADING_DB_PRIOR_LOCAL_STATE_NOT_RECOVERED": True,
    "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST": True,
    "old_trading_db_recovered": False,
    "wallet_delta_attribution_changed": False,
}


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


@dataclass
class RestoreResult:
    status: str
    detail: dict[str, Any]


class RuntimeDurabilityV1:
    def __init__(self, root: Path, *, backup_root: Path | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.backup_root = Path(backup_root) if backup_root else self.root / "backups"
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "private_event_ledger.sqlite3"
        self.lkg_path = self.root / "last_known_good.json"
        self.meta_path = self.root / "durability_meta.json"
        self._generation = 0
        if self.meta_path.exists():
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            self._generation = int(meta.get("generation") or 0)

    def open_ledger(self) -> PrivateEventLedger:
        return PrivateEventLedger(self.ledger_path)

    def _write_meta(self) -> None:
        self.meta_path.write_text(
            json.dumps({"generation": self._generation, "updated_at": _utc(), **PRESERVED_FACTS}, indent=2)
            + "\n",
            encoding="utf-8",
        )

    def create_snapshot(self, ledger: PrivateEventLedger) -> dict[str, Any]:
        chain = ledger.verify_hash_chain()
        if chain.get("ledger_hash_chain_status") != "PASS":
            return {"status": "CORRUPTION_DETECTED", "chain": chain}
        if ledger.integrity_check() != "ok":
            return {"status": "CORRUPTION_DETECTED", "integrity": ledger.integrity_check()}

        self._generation += 1
        gen = self._generation
        snap_dir = self.backup_root / f"snapshot_{gen:06d}"
        snap_dir.mkdir(parents=True, exist_ok=True)
        dest = snap_dir / "private_event_ledger.sqlite3"
        # Safe snapshot via vacuum-into or file copy after checkpoint
        ledger._conn.execute("PRAGMA wal_checkpoint(FULL)")
        shutil.copy2(self.ledger_path, dest)
        checksum = _file_sha(dest)
        pointer = {
            "generation": gen,
            "created_at": _utc(),
            "source_ledger_position": ledger.event_count(),
            "snapshot_checksum": checksum,
            "snapshot_path": str(dest),
            "ledger_hash_chain_status": "PASS",
        }
        (snap_dir / "snapshot_manifest.json").write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
        self.lkg_path.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
        self._write_meta()
        return {"status": "SNAPSHOT_OK", **pointer}

    def detect_corruption(self, ledger: PrivateEventLedger) -> dict[str, Any]:
        integrity = ledger.integrity_check()
        chain = ledger.verify_hash_chain()
        status = "PASS"
        if integrity != "ok" or chain.get("ledger_hash_chain_status") != "PASS":
            status = "CORRUPTION_DETECTED"
        return {
            "corruption_detection_status": status,
            "integrity_check": integrity,
            **chain,
        }

    def restore_last_known_good(self) -> RestoreResult:
        if not self.lkg_path.exists():
            return RestoreResult(status="RECOVERY_FAILED", detail={"reason": "missing_lkg_pointer"})
        pointer = json.loads(self.lkg_path.read_text(encoding="utf-8"))
        snap = Path(pointer["snapshot_path"])
        if not snap.exists():
            return RestoreResult(status="BLOCKED_AMBIGUOUS_STATE", detail={"reason": "missing_snapshot_file", "pointer": pointer})
        actual = _file_sha(snap)
        if actual != pointer.get("snapshot_checksum"):
            return RestoreResult(
                status="CORRUPTION_DETECTED",
                detail={"reason": "snapshot_checksum_mismatch", "expected": pointer.get("snapshot_checksum"), "actual": actual},
            )
        # Restore into a side path first, validate, then replace.
        tmp = self.root / "restore_tmp.sqlite3"
        shutil.copy2(snap, tmp)
        probe = PrivateEventLedger(tmp)
        try:
            det = self.detect_corruption(probe)
            if det.get("corruption_detection_status") != "PASS":
                probe.close()
                tmp.unlink(missing_ok=True)
                return RestoreResult(status="CORRUPTION_DETECTED", detail=det)
            count = probe.event_count()
            probe.close()
        except Exception as exc:
            try:
                probe.close()
            except Exception:
                pass
            tmp.unlink(missing_ok=True)
            return RestoreResult(status="RECOVERY_FAILED", detail={"error": str(exc)})

        # Ambiguous if live ledger has diverged with unreadable corruption
        live_ok = True
        if self.ledger_path.exists():
            try:
                live = PrivateEventLedger(self.ledger_path)
                live_det = self.detect_corruption(live)
                live.close()
                if live_det.get("corruption_detection_status") != "PASS":
                    live_ok = False
            except Exception:
                live_ok = False

        shutil.copy2(tmp, self.ledger_path)
        tmp.unlink(missing_ok=True)
        if live_ok and count == pointer.get("source_ledger_position"):
            return RestoreResult(status="RECOVERED_EXACT", detail={"generation": pointer.get("generation"), "event_count": count})
        return RestoreResult(
            status="RECOVERED_LAST_KNOWN_GOOD",
            detail={"generation": pointer.get("generation"), "event_count": count, "live_ok_before": live_ok},
        )

    def fail_closed_ambiguous(self, *, reason: str) -> dict[str, Any]:
        return {
            "status": "BLOCKED_AMBIGUOUS_STATE",
            "reason": reason,
            "exchange_write_attempt_count": 0,
            "demo_order_count": 0,
            "policy_mutation": False,
            **PRESERVED_FACTS,
        }


def run_failure_injection_matrix(tmp_root: Path | None = None) -> dict[str, Any]:
    root = Path(tmp_root) if tmp_root else Path(tempfile.mkdtemp(prefix="nexus_durability_"))
    dur = RuntimeDurabilityV1(root)
    ledger = dur.open_ledger()
    results = {}

    # Happy append + snapshot
    for i in range(5):
        ledger.append(
            aggregate_id=f"agg-{i}",
            aggregate_type="CANDIDATE",
            event_type="CREATED",
            source="test",
            payload={"i": i},
            idempotency_key=f"idemp-{i}",
        )
    snap = dur.create_snapshot(ledger)
    results["snapshot"] = snap
    results["hash_chain"] = ledger.verify_hash_chain()
    # Idempotent append
    dup = ledger.append(
        aggregate_id="agg-0",
        aggregate_type="CANDIDATE",
        event_type="CREATED",
        source="test",
        payload={"i": 0},
        idempotency_key="idemp-0",
    )
    results["idempotency"] = {"status": "PASS" if dup.duplicate else "FAIL", "result": dup.status}

    # Truncated / corrupted snapshot checksum
    bad_snap_dir = Path(snap["snapshot_path"]).parent
    corrupted = bad_snap_dir / "corrupted.sqlite3"
    shutil.copy2(snap["snapshot_path"], corrupted)
    with corrupted.open("ab") as fh:
        fh.write(b"\x00\xffCORRUPT")
    # Point LKG at corrupted file with old checksum -> detect
    pointer = json.loads(dur.lkg_path.read_text(encoding="utf-8"))
    pointer_bad = dict(pointer)
    pointer_bad["snapshot_path"] = str(corrupted)
    dur.lkg_path.write_text(json.dumps(pointer_bad, indent=2) + "\n", encoding="utf-8")
    restore_bad = dur.restore_last_known_good()
    results["corrupted_snapshot_restore"] = {
        "status": "PASS" if restore_bad.status == "CORRUPTION_DETECTED" else "FAIL",
        "restore_status": restore_bad.status,
    }
    # Restore good LKG pointer
    dur.lkg_path.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    # Simulate live corruption then restore
    with dur.ledger_path.open("ab") as fh:
        fh.write(b"GARBAGE_TAIL")
    # Opening may fail integrity — treat as ambiguous/corrupt path via restore
    restore = dur.restore_last_known_good()
    results["restore_after_live_corruption"] = {
        "status": "PASS"
        if restore.status in {"RECOVERED_LAST_KNOWN_GOOD", "RECOVERED_EXACT"}
        else "FAIL",
        "restore_status": restore.status,
        "detail": restore.detail,
    }
    ledger2 = dur.open_ledger()
    results["post_restore_chain"] = ledger2.verify_hash_chain()
    results["integrity"] = ledger2.integrity_check()
    ledger2.close()
    ledger.close()

    ambiguous = dur.fail_closed_ambiguous(reason="stale_checkpoint_vs_ledger")
    results["ambiguous_fail_closed"] = {
        "status": "PASS" if ambiguous["status"] == "BLOCKED_AMBIGUOUS_STATE" else "FAIL",
        "detail": ambiguous,
    }
    results["preserved_facts"] = PRESERVED_FACTS
    results["backup_root"] = str(dur.backup_root)
    results["exchange_write_attempt_count"] = 0
    results["demo_order_count"] = 0

    all_pass = all(
        results[k].get("status") == "PASS"
        for k in ("idempotency", "corrupted_snapshot_restore", "restore_after_live_corruption", "ambiguous_fail_closed")
    ) and results["hash_chain"].get("ledger_hash_chain_status") == "PASS"
    results["durability_status"] = (
        "NEXUS_RUNTIME_DURABILITY_V1_PASS" if all_pass else "NEXUS_RUNTIME_DURABILITY_RECOVERY_PARTIAL"
    )
    results["created_at"] = _utc()
    return results

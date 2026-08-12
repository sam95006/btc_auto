"""Fault injectors for Durability / DR V2 drills. No silent repair."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from backend.nexus_runtime.durability_v2.engine import RuntimeDurabilityV2, file_sha256
from backend.nexus_runtime.durability_v2.ledger import DurableEventLedgerV2


def truncate_file(path: Path, keep_bytes: int) -> dict[str, Any]:
    data = path.read_bytes()
    path.write_bytes(data[: max(0, keep_bytes)])
    return {"path": str(path), "kept": keep_bytes, "was": len(data)}


def bit_flip_file(path: Path, offset: int = 64) -> dict[str, Any]:
    data = bytearray(path.read_bytes())
    if not data:
        return {"status": "EMPTY"}
    idx = min(max(0, offset), len(data) - 1)
    data[idx] ^= 0xFF
    path.write_bytes(bytes(data))
    return {"path": str(path), "offset": idx}


def power_loss_mid_write(path: Path) -> dict[str, Any]:
    """Simulate power loss: truncate mid-file (incomplete durable write).

    Trailing-byte append is ignored by SQLite page accounting; mid-file
    truncation is the realistic power-loss failure mode.
    """
    size = path.stat().st_size
    keep = max(100, size // 2)
    truncate_file(path, keep_bytes=keep)
    return {"path": str(path), "kind": "power_loss", "kept": keep, "was": size}


def partial_write_append(path: Path, junk: bytes = b"\x00PARTIAL") -> dict[str, Any]:
    """Simulate partial page write: multi-offset bit flips + truncated tail."""
    size = path.stat().st_size
    offsets = sorted({64, 128, max(64, size // 3), max(64, size // 2), max(64, size - 256)})
    for off in offsets:
        if off < size:
            bit_flip_file(path, offset=off)
    keep = max(200, int(size * 0.85))
    truncate_file(path, keep_bytes=keep)
    with path.open("ab") as fh:
        fh.write(junk)
        fh.flush()
    return {"path": str(path), "appended": len(junk), "kind": "partial_write", "kept": keep, "was": size}


def corrupt_lkg_pointer(dur: RuntimeDurabilityV2) -> dict[str, Any]:
    if not dur.lkg_path.exists():
        return {"status": "NO_LKG"}
    pointer = json.loads(dur.lkg_path.read_text(encoding="utf-8"))
    pointer["snapshot_checksum"] = "0" * 64
    pointer["corrupted"] = True
    dur.lkg_path.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")
    return {"status": "LKG_CHECKSUM_CORRUPTED"}


def remove_latest_snapshot(dur: RuntimeDurabilityV2) -> dict[str, Any]:
    snaps = dur.list_snapshots()
    if not snaps:
        return {"status": "NO_SNAPSHOTS"}
    latest = snaps[-1]
    snap_path = Path(latest["snapshot_path"])
    if snap_path.exists():
        snap_path.unlink()
    # Keep LKG pointing at missing file.
    return {"status": "LATEST_REMOVED", "generation": latest.get("generation")}


def corrupt_snapshot_bytes(dur: RuntimeDurabilityV2) -> dict[str, Any]:
    snaps = dur.list_snapshots()
    if not snaps:
        return {"status": "NO_SNAPSHOTS"}
    snap_path = Path(snaps[-1]["snapshot_path"])
    return bit_flip_file(snap_path, offset=128)


def inject_hash_chain_corruption(ledger: DurableEventLedgerV2, seq: int = 1) -> dict[str, Any]:
    ok = ledger.corrupt_hash_at(seq)
    return {"status": "OK" if ok else "MISS", "sequence": seq}


def inject_payload_bit_corruption(ledger: DurableEventLedgerV2, seq: int = 1) -> dict[str, Any]:
    ok = ledger.flip_bit_in_payload(seq)
    return {"status": "OK" if ok else "MISS", "sequence": seq}


def copy_tree_size(src: Path, dst: Path) -> int:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    total = 0
    for p in dst.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total

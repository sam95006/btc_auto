"""Corrupt archive recovery — quarantine + checkpoint resume (fixture-only)."""
from __future__ import annotations

import hashlib
import json
import os
import zlib
from pathlib import Path
from typing import Any

from backend.nexus_deep_ingest_contamination.constants import (
    BOUNDED_MAX_ARCHIVE_ENTRIES,
    BOUNDED_MAX_DISK_BYTES,
)
from backend.nexus_deep_ingest_contamination.hard_bans import (
    HardBanViolation,
    refuse_silent_corrupt_resume,
)


class ArchiveIntegrityError(RuntimeError):
    """Archive bytes failed integrity verification."""


class CorruptArchiveRecovery:
    """File-backed fixture archive with checksum, quarantine, and resume.

    Recovery contract:
      * Intact entries resume from checkpoint.
      * Corrupt / truncated / checksum-mismatched entries are quarantined.
      * Silent resume over corrupted bytes is hard-banned.
    """

    def __init__(
        self,
        root: Path,
        *,
        max_disk_bytes: int = BOUNDED_MAX_DISK_BYTES,
        max_entries: int = BOUNDED_MAX_ARCHIVE_ENTRIES,
    ) -> None:
        self.root = Path(root)
        self.max_disk_bytes = int(max_disk_bytes)
        self.max_entries = int(max_entries)
        self.entries_dir = self.root / "entries"
        self.quarantine_dir = self.root / "quarantine"
        self.index_path = self.root / "index.json"
        self.checkpoint_path = self.root / "resume_checkpoint.json"
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, dict[str, Any]] = self._load_index()

    def _load_index(self) -> dict[str, dict[str, Any]]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self) -> None:
        self._atomic_write_json(self.index_path, self._index)

    def _atomic_write_json(self, path: Path, obj: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        payload = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def disk_usage_bytes(self) -> int:
        total = 0
        for p in self.root.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total

    @staticmethod
    def content_hash(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    def pack_entry(self, entry_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if len(self._index) >= self.max_entries and entry_id not in self._index:
            raise HardBanViolation(f"archive_entry_budget_exceeded:{self.max_entries}")
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
        compressed = zlib.compress(raw, level=6)
        digest = self.content_hash(compressed)
        blob = {
            "schema": "v17_deep_archive_entry_v1",
            "entry_id": entry_id,
            "content_hash": digest,
            "encoding": "zlib+json",
            "byte_len": len(compressed),
            "payload_b64_len": len(compressed),
        }
        path = self.entries_dir / f"{entry_id}.bin"
        if self.disk_usage_bytes() + len(compressed) + 256 > self.max_disk_bytes:
            raise HardBanViolation(
                f"bounded_disk_exceeded:usage={self.disk_usage_bytes()}:max={self.max_disk_bytes}"
            )
        with open(path, "wb") as f:
            f.write(compressed)
            f.flush()
            os.fsync(f.fileno())
        meta_path = self.entries_dir / f"{entry_id}.meta.json"
        self._atomic_write_json(meta_path, blob)
        self._index[entry_id] = {
            "entry_id": entry_id,
            "content_hash": digest,
            "status": "OK",
            "path": str(path.relative_to(self.root)).replace("\\", "/"),
            "byte_len": len(compressed),
        }
        self._save_index()
        self.write_checkpoint(last_entry_id=entry_id)
        return {"status": "PACKED", **self._index[entry_id]}

    def write_checkpoint(self, *, last_entry_id: str) -> None:
        self._atomic_write_json(
            self.checkpoint_path,
            {
                "schema": "v17_deep_archive_resume_checkpoint_v1",
                "last_entry_id": last_entry_id,
                "entry_count": len(self._index),
            },
        )

    def read_checkpoint(self) -> dict[str, Any] | None:
        if not self.checkpoint_path.exists():
            return None
        return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))

    def verify_entry(self, entry_id: str) -> dict[str, Any]:
        meta = self._index.get(entry_id)
        if meta is None:
            raise FileNotFoundError(entry_id)
        path = self.entries_dir / f"{entry_id}.bin"
        if not path.exists():
            return self.quarantine(entry_id, reason="missing_bytes")
        data = path.read_bytes()
        digest = self.content_hash(data)
        if digest != meta["content_hash"]:
            return self.quarantine(entry_id, reason="content_hash_mismatch")
        try:
            raw = zlib.decompress(data)
            json.loads(raw.decode("utf-8"))
        except (zlib.error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return self.quarantine(entry_id, reason=f"decode_fail:{exc}")
        return {"status": "OK", "entry_id": entry_id, "content_hash": digest}

    def quarantine(self, entry_id: str, *, reason: str) -> dict[str, Any]:
        path = self.entries_dir / f"{entry_id}.bin"
        q_path = self.quarantine_dir / f"{entry_id}.bin"
        meta_q = self.quarantine_dir / f"{entry_id}.meta.json"
        data = path.read_bytes() if path.exists() else b""
        if path.exists():
            q_path.write_bytes(data)
            path.unlink()
        pointer = {
            "schema": "v17_deep_archive_quarantine_v1",
            "entry_id": entry_id,
            "status": "QUARANTINED",
            "reason": reason,
            "original_sha256": self.content_hash(data) if data else None,
            "quarantine_path": str(q_path.relative_to(self.root)).replace("\\", "/")
            if q_path.exists()
            else None,
        }
        self._atomic_write_json(meta_q, pointer)
        if entry_id in self._index:
            self._index[entry_id]["status"] = "QUARANTINED"
            self._index[entry_id]["reason"] = reason
            self._save_index()
        return pointer

    def corrupt_entry_bytes(self, entry_id: str, *, mode: str = "truncate") -> None:
        """Test helper — intentionally damage stored bytes (fixture only)."""
        path = self.entries_dir / f"{entry_id}.bin"
        if not path.exists():
            raise FileNotFoundError(entry_id)
        data = path.read_bytes()
        if mode == "truncate":
            damaged = data[: max(1, len(data) // 3)]
        elif mode == "flip":
            damaged = bytes([b ^ 0xFF for b in data[: min(16, len(data))]]) + data[16:]
        elif mode == "empty":
            damaged = b""
        else:
            raise ValueError(f"unknown corrupt mode: {mode}")
        path.write_bytes(damaged)

    def recover(self, *, allow_silent_corrupt: bool = False) -> dict[str, Any]:
        """Scan index, quarantine corrupt entries, resume from last good checkpoint."""
        if allow_silent_corrupt:
            refuse_silent_corrupt_resume()
        verified: list[dict[str, Any]] = []
        quarantined: list[dict[str, Any]] = []
        for entry_id in list(self._index.keys()):
            result = self.verify_entry(entry_id)
            if result.get("status") == "QUARANTINED":
                quarantined.append(result)
            else:
                verified.append(result)
        checkpoint = self.read_checkpoint()
        last_good = None
        for entry_id, meta in self._index.items():
            if meta.get("status") == "OK":
                last_good = entry_id
        if last_good is not None:
            self.write_checkpoint(last_entry_id=last_good)
            checkpoint = self.read_checkpoint()
        if verified and quarantined:
            status = "RECOVERED_WITH_QUARANTINE"
        elif verified:
            status = "RECOVERED"
        elif quarantined:
            status = "BLOCKED_CORRUPT_ARCHIVE"
        else:
            status = "EMPTY"
        return {
            "status": status,
            "verified_count": len(verified),
            "quarantined_count": len(quarantined),
            "quarantined": quarantined,
            "checkpoint": checkpoint,
            "silent_corrupt_resume": False,
            "fixture_only": True,
        }

    def attempt_silent_resume_over_corrupt(self, entry_id: str) -> dict[str, Any]:
        """Adversarial path — must refuse to treat corrupt bytes as valid."""
        result = self.verify_entry(entry_id)
        if result.get("status") == "OK":
            return {"attack_blocked": False, "detail": "corrupt_not_detected", "result": result}
        try:
            refuse_silent_corrupt_resume()
        except HardBanViolation as exc:
            return {
                "attack_blocked": True,
                "detail": str(exc),
                "result": result,
            }
        return {"attack_blocked": False, "detail": "silent_resume_allowed", "result": result}

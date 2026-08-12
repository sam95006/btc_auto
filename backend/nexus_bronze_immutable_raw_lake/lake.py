"""Append-only Bronze lake — checksum, dedupe, quarantine, resume, disk bound."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from backend.nexus_bronze_immutable_raw_lake.constants import DEFAULT_MAX_DISK_BYTES, SCHEMA
from backend.nexus_bronze_immutable_raw_lake.hard_bans import (
    HardBanViolation,
    refuse_historical_rewrite,
)
from backend.nexus_bronze_immutable_raw_lake.hashing import content_hash_of, sha_bytes, utc_now_iso
from backend.nexus_bronze_immutable_raw_lake.records import (
    BronzeRecordError,
    build_bronze_record,
    verify_bronze_record,
)


class DiskBudgetExceeded(RuntimeError):
    pass


class BronzeLake:
    """File-backed append-only raw lake with quarantine and resume checkpoint."""

    def __init__(
        self,
        root: Path,
        *,
        max_disk_bytes: int = DEFAULT_MAX_DISK_BYTES,
    ) -> None:
        self.root = Path(root)
        self.max_disk_bytes = int(max_disk_bytes)
        self.records_dir = self.root / "records"
        self.quarantine_dir = self.root / "quarantine"
        self.manifest_path = self.root / "manifest.jsonl"
        self.checkpoint_path = self.root / "resume_checkpoint.json"
        self.index_path = self.root / "content_hash_index.json"
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, str] = self._load_index()

    def _load_index(self) -> dict[str, str]:
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

    def _assert_disk_budget(self, incoming_bytes: int) -> None:
        if self.disk_usage_bytes() + incoming_bytes > self.max_disk_bytes:
            raise DiskBudgetExceeded(
                f"bounded_disk_exceeded:usage={self.disk_usage_bytes()}:max={self.max_disk_bytes}"
            )

    def has_content_hash(self, content_hash: str) -> bool:
        return content_hash in self._index

    def ingest(
        self,
        *,
        exchange_timestamp: str,
        received_timestamp: str,
        source_id: str,
        symbol_original: str,
        payload: Any,
        classification: str,
        license_reference: str,
        compression: str = "none",
        source_offset: int | None = None,
    ) -> dict[str, Any]:
        record = build_bronze_record(
            exchange_timestamp=exchange_timestamp,
            received_timestamp=received_timestamp,
            source_id=source_id,
            symbol_original=symbol_original,
            payload=payload,
            classification=classification,
            license_reference=license_reference,
            compression=compression,
        )
        c_hash = record["content_hash"]
        if self.has_content_hash(c_hash):
            return {
                "status": "DUPLICATE",
                "content_hash": c_hash,
                "record_id": self._index[c_hash],
                "action": "skipped",
            }

        blob = (json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        self._assert_disk_budget(len(blob) + 256)
        rec_path = self.records_dir / f"{c_hash}.json"
        if rec_path.exists():
            # Existing file must never be rewritten.
            refuse_historical_rewrite()
        with open(rec_path, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())

        self._index[c_hash] = record["record_id"]
        self._save_index()
        self._append_manifest_line(
            {
                "content_hash": c_hash,
                "partition_hash": record["partition_hash"],
                "source_id": source_id,
                "symbol_original": symbol_original,
                "exchange_timestamp": exchange_timestamp,
                "path": str(rec_path.relative_to(self.root)).replace("\\", "/"),
                "bytes": len(blob),
                "ingested_timestamp": record["ingested_timestamp"],
            }
        )
        if source_offset is not None:
            self.write_checkpoint(source_offset=source_offset, last_content_hash=c_hash)
        return {
            "status": "INGESTED",
            "content_hash": c_hash,
            "record_id": record["record_id"],
            "path": str(rec_path.relative_to(self.root)).replace("\\", "/"),
            "action": "appended",
        }

    def _append_manifest_line(self, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        with open(self.manifest_path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def rewrite_record(self, content_hash: str, new_payload: Any) -> None:
        """Historical rewrite is hard-banned."""
        _ = (content_hash, new_payload)
        refuse_historical_rewrite()

    def quarantine_corrupt(self, content_hash: str, *, reason: str) -> dict[str, Any]:
        rec_path = self.records_dir / f"{content_hash}.json"
        if not rec_path.exists():
            raise FileNotFoundError(content_hash)
        q_path = self.quarantine_dir / f"{content_hash}.json"
        data = rec_path.read_bytes()
        meta = {
            "schema": SCHEMA,
            "content_hash": content_hash,
            "reason": reason,
            "quarantined_at": utc_now_iso(),
            "original_sha256": sha_bytes(data),
        }
        # Move bytes into quarantine; leave tombstone marker (no silent rewrite of payload).
        q_path.write_bytes(data)
        (self.quarantine_dir / f"{content_hash}.meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        # Replace live record with immutable quarantine pointer (not a payload rewrite).
        pointer = {
            "schema": "v17_b_bronze_quarantine_pointer_v1",
            "content_hash": content_hash,
            "status": "QUARANTINED",
            "reason": reason,
            "quarantine_path": str(q_path.relative_to(self.root)).replace("\\", "/"),
            "pointer_at": utc_now_iso(),
        }
        # Pointer write is allowed only once from a live record → quarantine state.
        # We do NOT mutate the quarantined payload bytes.
        tmp = rec_path.with_suffix(".json.ptr.tmp")
        tmp.write_text(json.dumps(pointer, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, rec_path)
        self._append_manifest_line(
            {
                "content_hash": content_hash,
                "status": "QUARANTINED",
                "reason": reason,
                "quarantine_path": pointer["quarantine_path"],
            }
        )
        return pointer

    def verify_stored(self, content_hash: str) -> dict[str, Any]:
        rec_path = self.records_dir / f"{content_hash}.json"
        raw = rec_path.read_text(encoding="utf-8")
        obj = json.loads(raw)
        if obj.get("status") == "QUARANTINED":
            return {"status": "QUARANTINED", "content_hash": content_hash}
        try:
            verify_bronze_record(obj)
            # Recompute vs payload
            if content_hash_of(obj["payload"]) != obj["content_hash"]:
                raise BronzeRecordError("content_hash_mismatch")
            return {"status": "OK", "content_hash": content_hash}
        except (BronzeRecordError, HardBanViolation, KeyError, TypeError, json.JSONDecodeError) as exc:
            pointer = self.quarantine_corrupt(content_hash, reason=f"verify_fail:{exc}")
            return {"status": "QUARANTINED", "content_hash": content_hash, "pointer": pointer}

    def write_checkpoint(self, *, source_offset: int, last_content_hash: str) -> None:
        self._atomic_write_json(
            self.checkpoint_path,
            {
                "schema": "v17_b_bronze_resume_checkpoint_v1",
                "source_offset": int(source_offset),
                "last_content_hash": last_content_hash,
                "updated_at": utc_now_iso(),
            },
        )

    def read_checkpoint(self) -> dict[str, Any] | None:
        if not self.checkpoint_path.exists():
            return None
        return json.loads(self.checkpoint_path.read_text(encoding="utf-8"))

    def resume_offset(self) -> int:
        cp = self.read_checkpoint()
        if not cp:
            return 0
        return int(cp.get("source_offset", 0)) + 1

    def list_manifest(self) -> list[dict[str, Any]]:
        if not self.manifest_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in self.manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

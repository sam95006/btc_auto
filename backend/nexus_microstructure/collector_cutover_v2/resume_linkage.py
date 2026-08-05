"""Resume-safe partition linkage for Collector Cutover V2."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_microstructure.collector_cutover_v2.constants import (
    SCHEMA,
    SESSION_LINKAGE_FILENAME,
)
from backend.nexus_microstructure.integrity_recovery_v11.linkage import audit_linkage_v11


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ResumeSafeLinkage:
    """Persist last sealed partition_id and arm resume boundaries after open tails."""

    def __init__(self, session_dir: Path, *, capture_session_id: str) -> None:
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.capture_session_id = capture_session_id
        self.path = self.session_dir / SESSION_LINKAGE_FILENAME
        self.last_sealed_partition_id: str | None = None
        self.resume_boundary_armed = False
        self.open_tail_partition_ids: list[str] = []
        self.load()

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self.snapshot()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if data.get("capture_session_id") != self.capture_session_id:
            return self.snapshot()
        self.last_sealed_partition_id = data.get("last_sealed_partition_id")
        self.resume_boundary_armed = bool(data.get("resume_boundary_armed", False))
        self.open_tail_partition_ids = list(data.get("open_tail_partition_ids") or [])
        return self.snapshot()

    def record_sealed(self, partition_id: str) -> None:
        self.last_sealed_partition_id = partition_id
        self.resume_boundary_armed = False
        self._persist()

    def record_open_tail(self, partition_id: str) -> None:
        if partition_id not in self.open_tail_partition_ids:
            self.open_tail_partition_ids.append(partition_id)
        self.resume_boundary_armed = True
        self._persist()

    def previous_for_next_partition(self) -> str | None:
        """Return previous_partition_id for the next sealed partition.

        After an open-tail / resume boundary, return None so linkage treats
        the next sealed partition as a new chain start (V11 semantics).
        """
        if self.resume_boundary_armed:
            return None
        return self.last_sealed_partition_id

    def audit(self, partitions: list[dict[str, Any]]) -> dict[str, Any]:
        result = audit_linkage_v11(partitions)
        result["schema"] = f"{SCHEMA}_resume_safe_linkage_audit"
        result["resume_boundary_armed"] = self.resume_boundary_armed
        result["last_sealed_partition_id"] = self.last_sealed_partition_id
        result["open_tail_partition_ids"] = list(self.open_tail_partition_ids)
        return result

    def _persist(self) -> None:
        body = self.snapshot()
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": f"{SCHEMA}_session_linkage",
            "capture_session_id": self.capture_session_id,
            "last_sealed_partition_id": self.last_sealed_partition_id,
            "resume_boundary_armed": self.resume_boundary_armed,
            "open_tail_partition_ids": list(self.open_tail_partition_ids),
            "updated_at": _utc(),
        }

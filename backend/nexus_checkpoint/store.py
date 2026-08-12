"""Atomic canonical checkpoint store: temp → fsync → rename + LKG + restore."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_checkpoint.constants import (
    BLOCKED_AMBIGUOUS_STATE,
    CHECKPOINT_OK,
    CORRUPTION_DETECTED,
    DESTRUCTIVE_LIVE_MIGRATION_FORBIDDEN,
    LIVE_V23_CHECKPOINT_NAME,
    LKG_SCHEMA,
    RECOVERED_EXACT,
    RECOVERED_LAST_KNOWN_GOOD,
    RECOVERY_FAILED,
)
from backend.nexus_checkpoint.envelope import (
    build_envelope,
    detect_corruption,
    sha256_bytes,
    validate_envelope,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def atomic_write_bytes(path: Path, data: bytes) -> dict[str, Any]:
    """Write bytes via temp + fsync + os.replace. Returns write metrics."""
    path = Path(path)
    if DESTRUCTIVE_LIVE_MIGRATION_FORBIDDEN and path.name == LIVE_V23_CHECKPOINT_NAME:
        raise PermissionError(
            f"refusing write to live V2.3 checkpoint path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    t0 = time.perf_counter()
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    # Best-effort directory fsync (POSIX); Windows may not support.
    try:
        dir_fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass
    os.replace(tmp, path)
    elapsed = time.perf_counter() - t0
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": sha256_bytes(data),
        "fsync": True,
        "rename": True,
        "latency_s": elapsed,
    }


def atomic_write_json(path: Path, obj: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n"
    return atomic_write_bytes(path, text.encode("utf-8"))


class CanonicalCheckpointStore:
    """One envelope authority for Session/Reflection/Microstructure/Qualification/Decision.

    Subsystem stores may continue to own payload schema; this store owns the
    durable envelope, LKG pointer, and fail-closed restore semantics.
    """

    def __init__(self, root: Path, *, source_runtime: str = "nexus_checkpoint_v11_1") -> None:
        self.root = Path(root)
        self.checkpoints_dir = self.root / "checkpoints"
        self.lkg_path = self.root / "last_known_good_checkpoint.json"
        self.source_runtime = source_runtime
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self._idempotency_index: dict[str, str] = {}
        self._load_idempotency_index()

    def _load_idempotency_index(self) -> None:
        for path in self.checkpoints_dir.glob("*.json"):
            if path.name.endswith(".tmp"):
                continue
            try:
                env = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            key = env.get("idempotency_key")
            cid = env.get("checkpoint_id")
            if key and cid:
                self._idempotency_index[str(key)] = str(cid)

    def checkpoint_path(self, checkpoint_id: str) -> Path:
        return self.checkpoints_dir / f"{checkpoint_id}.json"

    def save(
        self,
        *,
        payload: dict[str, Any],
        payload_type: str,
        idempotency_key: str,
        manifest_checksum: str | None = None,
        ledger_sequence: int = 0,
        previous_checkpoint_id: str | None = None,
        migration_history: list[dict[str, Any]] | None = None,
        update_lkg: bool = True,
        source_runtime: str | None = None,
    ) -> dict[str, Any]:
        existing_id = self._idempotency_index.get(str(idempotency_key))
        if existing_id:
            existing_path = self.checkpoint_path(existing_id)
            if existing_path.is_file():
                env = json.loads(existing_path.read_text(encoding="utf-8"))
                probe = validate_envelope(env)
                if probe["ok"]:
                    return {
                        "status": CHECKPOINT_OK,
                        "duplicate": True,
                        "checkpoint_id": existing_id,
                        "path": str(existing_path),
                        "envelope": env,
                        "write": None,
                    }

        # Chain previous from LKG when not provided.
        prev = previous_checkpoint_id
        if prev is None and self.lkg_path.is_file():
            try:
                ptr = json.loads(self.lkg_path.read_text(encoding="utf-8"))
                prev = ptr.get("checkpoint_id")
            except (OSError, json.JSONDecodeError):
                prev = None

        env = build_envelope(
            payload=payload,
            payload_type=payload_type,
            idempotency_key=idempotency_key,
            source_runtime=source_runtime or self.source_runtime,
            manifest_checksum=manifest_checksum,
            ledger_sequence=ledger_sequence,
            previous_checkpoint_id=prev,
            migration_history=migration_history,
        )
        path = self.checkpoint_path(env["checkpoint_id"])
        write = atomic_write_json(path, env)
        # Verify after rename
        raw = path.read_bytes()
        if sha256_bytes(raw) != write["sha256"]:
            return {
                "status": CORRUPTION_DETECTED,
                "reason": "post_write_checksum_mismatch",
                "path": str(path),
            }
        probe = detect_corruption(raw.decode("utf-8"))
        if not probe["ok"]:
            return {"status": CORRUPTION_DETECTED, **probe, "path": str(path)}

        self._idempotency_index[str(idempotency_key)] = env["checkpoint_id"]
        if update_lkg:
            self._write_lkg(env, path, write["sha256"])

        return {
            "status": CHECKPOINT_OK,
            "duplicate": False,
            "checkpoint_id": env["checkpoint_id"],
            "path": str(path),
            "envelope": env,
            "write": write,
        }

    def _write_lkg(self, env: dict[str, Any], path: Path, file_sha256: str) -> None:
        pointer = {
            "schema": LKG_SCHEMA,
            "checkpoint_id": env["checkpoint_id"],
            "path": str(path),
            "payload_type": env["payload_type"],
            "payload_checksum": env["payload_checksum"],
            "manifest_checksum": env.get("manifest_checksum") or "",
            "envelope_checksum": env["envelope_checksum"],
            "file_sha256": file_sha256,
            "ledger_sequence": env.get("ledger_sequence"),
            "idempotency_key": env.get("idempotency_key"),
            "updated_at": _utc(),
        }
        atomic_write_json(self.lkg_path, pointer)

    def load(self, checkpoint_id: str) -> dict[str, Any]:
        path = self.checkpoint_path(checkpoint_id)
        if not path.is_file():
            return {
                "status": RECOVERY_FAILED,
                "reason": "missing_checkpoint",
                "checkpoint_id": checkpoint_id,
            }
        raw = path.read_text(encoding="utf-8")
        probe = detect_corruption(raw)
        if not probe["ok"]:
            return {"status": CORRUPTION_DETECTED, **probe, "path": str(path)}
        env = json.loads(raw)
        return {"status": CHECKPOINT_OK, "envelope": env, "path": str(path)}

    def read_lkg_pointer(self) -> dict[str, Any] | None:
        if not self.lkg_path.is_file():
            return None
        try:
            return json.loads(self.lkg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def restore_last_known_good(self, *, allow_ambiguous: bool = False) -> dict[str, Any]:
        """Restore via LKG pointer. Ambiguous divergence blocks (no silent guess)."""
        if not self.lkg_path.is_file():
            return {
                "status": RECOVERY_FAILED,
                "reason": "missing_lkg_pointer",
            }
        try:
            pointer = json.loads(self.lkg_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "status": CORRUPTION_DETECTED,
                "reason": "lkg_unreadable",
                "error": str(exc),
            }

        if pointer.get("schema") != LKG_SCHEMA:
            return {
                "status": CORRUPTION_DETECTED,
                "reason": "lkg_schema_mismatch",
                "observed": pointer.get("schema"),
            }

        path = Path(pointer.get("path") or "")
        if not path.is_file():
            # Try resolve by checkpoint_id under this store.
            cid = pointer.get("checkpoint_id")
            if cid:
                alt = self.checkpoint_path(str(cid))
                if alt.is_file():
                    path = alt
                else:
                    return {
                        "status": BLOCKED_AMBIGUOUS_STATE,
                        "reason": "lkg_target_missing",
                        "pointer": pointer,
                    }
            else:
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "lkg_target_missing",
                    "pointer": pointer,
                }

        raw_bytes = path.read_bytes()
        actual_sha = sha256_bytes(raw_bytes)
        if pointer.get("file_sha256") and actual_sha != pointer.get("file_sha256"):
            return {
                "status": CORRUPTION_DETECTED,
                "reason": "lkg_file_checksum_mismatch",
                "expected": pointer.get("file_sha256"),
                "actual": actual_sha,
            }

        probe = detect_corruption(raw_bytes.decode("utf-8"))
        if not probe["ok"]:
            return {"status": CORRUPTION_DETECTED, **probe, "path": str(path)}

        env = json.loads(raw_bytes.decode("utf-8"))
        if env.get("checkpoint_id") != pointer.get("checkpoint_id"):
            if not allow_ambiguous:
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "lkg_checkpoint_id_mismatch",
                    "pointer_id": pointer.get("checkpoint_id"),
                    "file_id": env.get("checkpoint_id"),
                }

        if env.get("envelope_checksum") != pointer.get("envelope_checksum"):
            if not allow_ambiguous:
                return {
                    "status": BLOCKED_AMBIGUOUS_STATE,
                    "reason": "lkg_vs_file_envelope_checksum_divergence",
                    "pointer": pointer.get("envelope_checksum"),
                    "file": env.get("envelope_checksum"),
                }

        # Ambiguous: newer checkpoint exists with higher ledger_sequence than LKG.
        latest = self._latest_envelope()
        if (
            latest
            and int(latest.get("ledger_sequence") or 0) > int(env.get("ledger_sequence") or 0)
            and latest.get("checkpoint_id") != env.get("checkpoint_id")
            and not allow_ambiguous
        ):
            return {
                "status": BLOCKED_AMBIGUOUS_STATE,
                "reason": "newer_checkpoint_ahead_of_lkg",
                "lkg_checkpoint_id": env.get("checkpoint_id"),
                "lkg_ledger_sequence": env.get("ledger_sequence"),
                "latest_checkpoint_id": latest.get("checkpoint_id"),
                "latest_ledger_sequence": latest.get("ledger_sequence"),
                "silent_recovery_guess": False,
            }

        status = RECOVERED_EXACT
        if latest and latest.get("checkpoint_id") != env.get("checkpoint_id"):
            status = RECOVERED_LAST_KNOWN_GOOD

        return {
            "status": status,
            "envelope": env,
            "path": str(path),
            "pointer": pointer,
            "silent_recovery_guess": False,
        }

    def _latest_envelope(self) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_seq = -1
        for path in self.checkpoints_dir.glob("*.json"):
            if path.name.endswith(".tmp"):
                continue
            try:
                env = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not validate_envelope(env)["ok"]:
                continue
            seq = int(env.get("ledger_sequence") or 0)
            if seq > best_seq:
                best_seq = seq
                best = env
        return best

    def fail_closed_ambiguous(self, *, reason: str) -> dict[str, Any]:
        return {
            "status": BLOCKED_AMBIGUOUS_STATE,
            "reason": reason,
            "silent_recovery_guess": False,
            "exchange_write_attempt_count": 0,
            "demo_order_count": 0,
        }

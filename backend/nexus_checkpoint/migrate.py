"""Schema migration helpers — dry-run first; never destroy live V2.3 checkpoint."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_checkpoint.constants import (
    DESTRUCTIVE_LIVE_MIGRATION_FORBIDDEN,
    LIVE_V23_CHECKPOINT_NAME,
    MIGRATION_BLOCKED,
    MIGRATION_DRY_RUN,
)
from backend.nexus_checkpoint.envelope import validate_envelope


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 256)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def migrate_legacy_to_envelope(
    state: dict[str, Any],
    *,
    payload_type: str,
    idempotency_key: str,
    dry_run: bool = True,
    source_runtime: str = "migration_v11_1",
) -> dict[str, Any]:
    """In-memory migration of a legacy checkpoint dict into the envelope."""
    from .adapters import ADAPTERS

    adapter = ADAPTERS.get(payload_type)
    if adapter is None:
        return {
            "status": MIGRATION_BLOCKED,
            "reason": "unknown_payload_type",
            "payload_type": payload_type,
        }
    env = adapter(
        state,
        idempotency_key=idempotency_key,
        source_runtime=source_runtime,
        dry_run=dry_run,
    )
    probe = validate_envelope(env)
    return {
        "status": MIGRATION_DRY_RUN if dry_run else "MIGRATED",
        "dry_run": dry_run,
        "validation": probe,
        "envelope": env,
        "destructive_write": False,
    }


def dry_run_migrate_live_v23(
    live_path: Path,
    *,
    artifact_out: Path | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """READ-ONLY dry-run wrap of the live Blind Reflection V2.3 checkpoint.

    Hard bans:
      - never write to ``live_path``
      - never rename/delete the live checkpoint
      - optional artifact write is allowed only under an artifacts directory
    """
    live_path = Path(live_path)
    if not live_path.is_file():
        return {
            "status": MIGRATION_BLOCKED,
            "reason": "live_checkpoint_missing",
            "path": str(live_path),
        }

    before_sha = file_sha256(live_path)
    before_mtime = live_path.stat().st_mtime_ns
    raw = live_path.read_text(encoding="utf-8")
    try:
        state = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "status": MIGRATION_BLOCKED,
            "reason": "live_checkpoint_corrupt_json",
            "error": str(exc),
            "path": str(live_path),
            "source_sha256_before": before_sha,
        }

    key = idempotency_key or f"dryrun-v23-{before_sha[:16]}"
    result = migrate_legacy_to_envelope(
        state,
        payload_type="reflection",
        idempotency_key=key,
        dry_run=True,
        source_runtime="live_v23_dry_run",
    )

    # Prove live file untouched.
    after_sha = file_sha256(live_path)
    after_mtime = live_path.stat().st_mtime_ns
    untouched = before_sha == after_sha and before_mtime == after_mtime

    artifact_path = None
    if artifact_out is not None:
        artifact_out = Path(artifact_out)
        if DESTRUCTIVE_LIVE_MIGRATION_FORBIDDEN and artifact_out.name == LIVE_V23_CHECKPOINT_NAME:
            return {
                "status": MIGRATION_BLOCKED,
                "reason": "refused_artifact_path_collides_with_live_name",
                "path": str(artifact_out),
            }
        # Only allow writes under artifacts/ or a temp path explicitly passed.
        artifact_out.parent.mkdir(parents=True, exist_ok=True)
        envelope = result.get("envelope") or {}
        payload = {
            "schema": "nexus_checkpoint_v23_dry_run_migration_v1",
            "generated_at": _utc(),
            "live_path": str(live_path),
            "live_sha256": before_sha,
            "live_untouched": untouched,
            "destructive_write": False,
            "migration": {
                "status": result.get("status"),
                "validation": result.get("validation"),
                "envelope_checkpoint_id": envelope.get("checkpoint_id"),
                "payload_type": envelope.get("payload_type"),
                "payload_checksum": envelope.get("payload_checksum"),
                "envelope_checksum": envelope.get("envelope_checksum"),
                "migration_history": envelope.get("migration_history"),
                "ledger_sequence": envelope.get("ledger_sequence"),
            },
            # Full envelope for evidence (not written to live runtime).
            "envelope": envelope,
        }
        artifact_out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        artifact_path = str(artifact_out)

        # Re-check live untouched after artifact write.
        after_sha = file_sha256(live_path)
        after_mtime = live_path.stat().st_mtime_ns
        untouched = before_sha == after_sha and before_mtime == after_mtime

    return {
        "status": MIGRATION_DRY_RUN,
        "dry_run": True,
        "destructive_write": False,
        "live_path": str(live_path),
        "live_sha256": before_sha,
        "live_untouched": untouched,
        "validation": result.get("validation"),
        "envelope_checkpoint_id": (result.get("envelope") or {}).get("checkpoint_id"),
        "payload_type": (result.get("envelope") or {}).get("payload_type"),
        "artifact_path": artifact_path,
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
    }


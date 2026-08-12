"""Canonical checkpoint envelope — identity and integrity metadata only.

Subsystems own ``payload`` schema. The envelope owns:
checkpoint_id, schema_version, payload_type, payload_checksum,
manifest_checksum, created_at, ledger_sequence, previous_checkpoint_id,
idempotency_key, source_runtime, migration_history.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.nexus_checkpoint.constants import (
    CORRUPTION_DETECTED,
    ENVELOPE_SCHEMA,
    ENVELOPE_SCHEMA_VERSION,
    PAYLOAD_TYPES,
    REQUIRED_ENVELOPE_FIELDS,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")


def sha256_obj(obj: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(obj)).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_payload_checksum(payload: dict[str, Any]) -> str:
    return sha256_obj(payload)


def envelope_integrity_view(envelope: dict[str, Any]) -> dict[str, Any]:
    """Fields covered by envelope_checksum (excludes envelope_checksum itself)."""
    skip = {"envelope_checksum"}
    return {k: envelope[k] for k in sorted(envelope.keys()) if k not in skip}


def compute_envelope_checksum(envelope: dict[str, Any]) -> str:
    return sha256_obj(envelope_integrity_view(envelope))


def new_checkpoint_id() -> str:
    return str(uuid.uuid4())


def build_envelope(
    *,
    payload: dict[str, Any],
    payload_type: str,
    idempotency_key: str,
    source_runtime: str,
    manifest_checksum: str | None = None,
    ledger_sequence: int = 0,
    previous_checkpoint_id: str | None = None,
    checkpoint_id: str | None = None,
    migration_history: list[dict[str, Any]] | None = None,
    created_at: str | None = None,
    extra_envelope_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if payload_type not in PAYLOAD_TYPES:
        raise ValueError(f"unsupported payload_type: {payload_type}")
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dict owned by the subsystem")
    if not idempotency_key:
        raise ValueError("idempotency_key required")

    body = dict(payload)
    env: dict[str, Any] = {
        "schema": ENVELOPE_SCHEMA,
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "checkpoint_id": checkpoint_id or new_checkpoint_id(),
        "payload_type": payload_type,
        "payload_checksum": compute_payload_checksum(body),
        "manifest_checksum": manifest_checksum or "",
        "created_at": created_at or _utc(),
        "ledger_sequence": int(ledger_sequence),
        "previous_checkpoint_id": previous_checkpoint_id,
        "idempotency_key": str(idempotency_key),
        "source_runtime": str(source_runtime),
        "migration_history": list(migration_history or []),
        "payload": body,
    }
    if extra_envelope_fields:
        for k, v in extra_envelope_fields.items():
            if k in env or k == "envelope_checksum":
                continue
            env[k] = v
    env["envelope_checksum"] = compute_envelope_checksum(env)
    return env


def validate_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Validate envelope structure + checksums. Never mutates input."""
    if not isinstance(envelope, dict):
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "not_object",
        }
    if envelope.get("schema") != ENVELOPE_SCHEMA:
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "unknown_schema",
            "observed": envelope.get("schema"),
        }
    missing = [f for f in REQUIRED_ENVELOPE_FIELDS if f not in envelope]
    if missing:
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "missing_required_fields",
            "missing": missing,
        }
    if envelope.get("payload_type") not in PAYLOAD_TYPES:
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "invalid_payload_type",
            "observed": envelope.get("payload_type"),
        }
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "payload_not_object",
        }

    expected_payload = compute_payload_checksum(payload)
    if envelope.get("payload_checksum") != expected_payload:
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "payload_checksum_mismatch",
            "expected": expected_payload,
            "observed": envelope.get("payload_checksum"),
        }

    stored = envelope.get("envelope_checksum")
    if not stored:
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "missing_envelope_checksum",
        }
    recomputed = compute_envelope_checksum(envelope)
    if stored != recomputed:
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "envelope_checksum_mismatch",
            "expected": recomputed,
            "observed": stored,
        }

    return {
        "ok": True,
        "status": "OK",
        "checkpoint_id": envelope.get("checkpoint_id"),
        "payload_type": envelope.get("payload_type"),
        "ledger_sequence": envelope.get("ledger_sequence"),
    }


def detect_corruption(raw_text: str | None) -> dict[str, Any]:
    if raw_text is None or raw_text.strip() == "":
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "MISSING_FILE",
        }
    try:
        obj = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "status": CORRUPTION_DETECTED,
            "reason": "TRUNCATED_OR_CORRUPT_JSON",
            "error": str(exc),
        }
    return validate_envelope(obj)

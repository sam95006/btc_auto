"""Subsystem payload adapters — wrap legacy/domain payloads into the envelope.

Adapters never mutate subsystem payload schemas; they only attach envelope metadata.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_checkpoint.envelope import build_envelope


def _migration_step(
    *,
    from_schema: str | None,
    from_version: Any,
    note: str,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "from_schema": from_schema,
        "from_version": from_version,
        "to_schema": "nexus_checkpoint_envelope_v1",
        "to_version": 1,
        "note": note,
        "dry_run": bool(dry_run),
    }


def wrap_reflection_payload(
    state: dict[str, Any],
    *,
    idempotency_key: str,
    source_runtime: str = "reflection_v23",
    dry_run: bool = False,
    ledger_sequence: int = 0,
    previous_checkpoint_id: str | None = None,
) -> dict[str, Any]:
    history = list(state.get("legacy_provenance") or [])
    history.append(
        _migration_step(
            from_schema=state.get("schema"),
            from_version=state.get("schema_version"),
            note="wrap_reflection_into_envelope",
            dry_run=dry_run,
        )
    )
    return build_envelope(
        payload=dict(state),
        payload_type="reflection",
        idempotency_key=idempotency_key,
        source_runtime=source_runtime,
        manifest_checksum=str(state.get("calibration_manifest_checksum") or ""),
        ledger_sequence=ledger_sequence,
        previous_checkpoint_id=previous_checkpoint_id,
        migration_history=history,
    )


def wrap_session_payload(
    state: dict[str, Any],
    *,
    idempotency_key: str,
    source_runtime: str = "session_orchestrator",
    ledger_sequence: int = 0,
    previous_checkpoint_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    history = [
        _migration_step(
            from_schema=state.get("schema") or "session_checkpoint_legacy",
            from_version=state.get("schema_version"),
            note="wrap_session_into_envelope",
            dry_run=dry_run,
        )
    ]
    return build_envelope(
        payload=dict(state),
        payload_type="session",
        idempotency_key=idempotency_key,
        source_runtime=source_runtime,
        manifest_checksum=str(state.get("manifest_checksum") or ""),
        ledger_sequence=ledger_sequence or int(state.get("ledger_sequence") or 0),
        previous_checkpoint_id=previous_checkpoint_id,
        migration_history=history,
    )


def wrap_decision_payload(
    state: dict[str, Any],
    *,
    idempotency_key: str,
    source_runtime: str = "decision_lifecycle_v11",
    ledger_sequence: int = 0,
    previous_checkpoint_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    history = [
        _migration_step(
            from_schema="decision_checkpoint_legacy",
            from_version=state.get("checkpoint_seq"),
            note="wrap_decision_into_envelope",
            dry_run=dry_run,
        )
    ]
    return build_envelope(
        payload=dict(state),
        payload_type="decision",
        idempotency_key=idempotency_key,
        source_runtime=source_runtime,
        manifest_checksum=str(state.get("checkpoint_sha256") or ""),
        ledger_sequence=ledger_sequence or int(state.get("checkpoint_seq") or 0),
        previous_checkpoint_id=previous_checkpoint_id,
        migration_history=history,
    )


def wrap_control_plane_payload(
    state: dict[str, Any],
    *,
    idempotency_key: str,
    source_runtime: str = "private_control",
    ledger_sequence: int = 0,
    previous_checkpoint_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    history = [
        _migration_step(
            from_schema="control_plane_checkpoint_legacy",
            from_version=state.get("checkpoint_seq"),
            note="wrap_control_plane_into_envelope",
            dry_run=dry_run,
        )
    ]
    return build_envelope(
        payload=dict(state),
        payload_type="control_plane",
        idempotency_key=idempotency_key,
        source_runtime=source_runtime,
        manifest_checksum=str(state.get("checkpoint_sha256") or ""),
        ledger_sequence=ledger_sequence or int(state.get("checkpoint_seq") or 0),
        previous_checkpoint_id=previous_checkpoint_id,
        migration_history=history,
    )


def wrap_microstructure_payload(
    state: dict[str, Any],
    *,
    idempotency_key: str,
    source_runtime: str = "microstructure_v12",
    ledger_sequence: int = 0,
    previous_checkpoint_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    history = [
        _migration_step(
            from_schema=state.get("schema") or "microstructure_checkpoint_legacy",
            from_version=state.get("schema_version"),
            note="wrap_microstructure_into_envelope",
            dry_run=dry_run,
        )
    ]
    return build_envelope(
        payload=dict(state),
        payload_type="microstructure",
        idempotency_key=idempotency_key,
        source_runtime=source_runtime,
        manifest_checksum=str(state.get("manifest_checksum") or ""),
        ledger_sequence=ledger_sequence,
        previous_checkpoint_id=previous_checkpoint_id,
        migration_history=history,
    )


def wrap_qualification_payload(
    state: dict[str, Any],
    *,
    idempotency_key: str,
    source_runtime: str = "qualification_pit_v11",
    ledger_sequence: int = 0,
    previous_checkpoint_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    history = [
        _migration_step(
            from_schema=state.get("schema") or "qualification_checkpoint_legacy",
            from_version=state.get("schema_version"),
            note="wrap_qualification_into_envelope",
            dry_run=dry_run,
        )
    ]
    return build_envelope(
        payload=dict(state),
        payload_type="qualification",
        idempotency_key=idempotency_key,
        source_runtime=source_runtime,
        manifest_checksum=str(state.get("manifest_checksum") or state.get("oos_cryptographic_seal") or ""),
        ledger_sequence=ledger_sequence,
        previous_checkpoint_id=previous_checkpoint_id,
        migration_history=history,
    )


ADAPTERS: dict[str, Any] = {
    "reflection": wrap_reflection_payload,
    "session": wrap_session_payload,
    "decision": wrap_decision_payload,
    "control_plane": wrap_control_plane_payload,
    "microstructure": wrap_microstructure_payload,
    "qualification": wrap_qualification_payload,
}

"""Hardened Blind Reflection V2.3 checkpoint — integrity, migration, sanitization."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_ai.profiles import PROVIDER_PROFILES
from backend.nexus_edge_discovery.blind_reflection_v23 import SCHEMA_VERSION
from backend.nexus_edge_discovery.quota_aware_v23 import (
    build_initial_checkpoint as _build_v3_initial,
    migrate_checkpoint_v2_to_v3,
)

CHECKPOINT_NAME = "blind_reflection_v23_checkpoint.json"
CHECKPOINT_SCHEMA_V4 = "blind_reflection_v23_checkpoint_v4"
CURRENT_SCHEMA_VERSION = 4

BANNED_KEYS = frozenset(
    {
        "api_key",
        "apiKey",
        "raw_prompt",
        "raw_response",
        "Authorization",
        "authorization",
        "secret",
        "password",
        "account_id",
        "accountId",
        "wallet",
        "bearer",
    }
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def checkpoint_path(root: Path) -> Path:
    return root / ".nexus_runtime" / CHECKPOINT_NAME


def integrity_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Fields covered by integrity checksum (excludes the checksum itself)."""
    keys = (
        "schema",
        "schema_version",
        "calibration_manifest_checksum",
        "case_ids",
        "completed_case_ids",
        "pending_case_ids",
        "pending_critic_case_ids",
        "critic_case_ids",
        "critic_pending_ids",
        "critic_resolved_ids",
        "transport",
        "prompt_schema_version",
        "evidence_schema_version",
        "response_hashes",
        "prompt_hashes",
        "evidence_packet_hashes",
        "model_ids",
    )
    return {k: state.get(k) for k in keys if k in state}


def compute_integrity_checksum(state: dict[str, Any]) -> str:
    return _sha(integrity_payload(state))


def validate_counter_invariants(state: dict[str, Any]) -> dict[str, Any]:
    """Enforce success_count reconciliation with completed/resolved case lists.

    Inflated transport counters must not survive checksum-only integrity checks.
    """
    issues: list[str] = []
    transport = state.get("transport") or {}
    groq = transport.get("GROQ_REFLECTION_REASONER") or {}
    critic = transport.get("SAMBANOVA_INDEPENDENT_CRITIC") or {}
    completed = list(state.get("completed_case_ids") or [])
    resolved = list(state.get("critic_resolved_ids") or [])
    groq_success = int(groq.get("success_count") or 0)
    critic_success = int(critic.get("success_count") or 0)
    if groq_success != len(completed):
        issues.append(
            f"GROQ_SUCCESS_COUNT_DRIFT:success_count={groq_success}"
            f":completed_case_ids={len(completed)}"
        )
    if critic_success != len(resolved):
        issues.append(
            f"CRITIC_SUCCESS_COUNT_DRIFT:success_count={critic_success}"
            f":critic_resolved_ids={len(resolved)}"
        )
    return {
        "ok": not issues,
        "issues": issues,
        "groq_success_count": groq_success,
        "completed_case_count": len(completed),
        "critic_success_count": critic_success,
        "critic_resolved_count": len(resolved),
    }


def sanitize_checkpoint(state: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets / raw prompts / raw responses recursively."""

    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if str(k) in BANNED_KEYS or any(
                    b in str(k).lower() for b in ("api_key", "secret", "password", "authorization")
                ):
                    continue
                # Never persist full prompts/responses even under alternate names
                if str(k).lower() in {"prompt", "full_prompt", "provider_response", "raw_body"}:
                    continue
                out[k] = _walk(v)
            return out
        if isinstance(obj, list):
            return [_walk(x) for x in obj]
        return obj

    return _walk(state)


def _ensure_v4_fields(state: dict[str, Any]) -> dict[str, Any]:
    out = dict(state)
    out["schema"] = CHECKPOINT_SCHEMA_V4
    out["schema_version"] = CURRENT_SCHEMA_VERSION
    # Alias pending_critic_case_ids ↔ critic_pending_ids
    critic_pending = list(
        out.get("pending_critic_case_ids")
        or out.get("critic_pending_ids")
        or []
    )
    out["pending_critic_case_ids"] = critic_pending
    out["critic_pending_ids"] = critic_pending
    out.setdefault("prompt_hashes", {})
    out.setdefault("evidence_packet_hashes", {})
    out.setdefault("response_hashes", {})
    out.setdefault("idempotency_keys", [])
    model_ids = dict(out.get("model_ids") or {})
    transport = dict(out.get("transport") or {})
    for pid in PROVIDER_PROFILES:
        slot = dict(transport.get(pid) or {})
        if not slot:
            slot = {
                "profile_id": pid,
                "model_id": "",
                "attempt_count": 0,
                "success_count": 0,
                "HTTP_429_count": 0,
                "timeout_count": 0,
                "invalid_schema_count": 0,
                "other_failure_count": 0,
                "last_attempt_at": None,
                "retry_after": None,
                "next_resume_not_before": None,
                "last_exit_reason": None,
            }
        transport[pid] = slot
        if slot.get("model_id"):
            model_ids[pid] = slot["model_id"]
    out["transport"] = transport
    out["model_ids"] = model_ids
    out.setdefault("prompt_schema_version", "blind_reflection_v2_3")
    out.setdefault("evidence_schema_version", SCHEMA_VERSION)
    # Backfill hashes from case_results
    for cid, row in (out.get("case_results") or {}).items():
        if row.get("prompt_hash"):
            out["prompt_hashes"].setdefault(cid, row["prompt_hash"])
        if row.get("evidence_packet_hash"):
            out["evidence_packet_hashes"].setdefault(cid, row["evidence_packet_hash"])
        if row.get("response_hash"):
            out["response_hashes"].setdefault(cid, row["response_hash"])
    out["integrity_checksum"] = compute_integrity_checksum(out)
    out["updated_at"] = _utc()
    return out


def migrate_checkpoint(state: dict[str, Any], *, model_id: str = "") -> dict[str, Any]:
    """Migrate v2/v3 → v4; preserve legacy provenance."""
    ver = int(state.get("schema_version") or 0)
    provenance = list(state.get("legacy_provenance") or [])
    if ver < 3 or not state.get("transport"):
        provenance.append(
            {
                "from_schema": state.get("schema"),
                "from_version": ver,
                "migrated_at": _utc(),
                "note": "v2_to_v3",
            }
        )
        state = migrate_checkpoint_v2_to_v3(state, model_id=model_id or "unknown")
        ver = 3
    if ver < 4:
        provenance.append(
            {
                "from_schema": state.get("schema"),
                "from_version": ver,
                "migrated_at": _utc(),
                "note": "v3_to_v4",
            }
        )
    out = _ensure_v4_fields(state)
    out["legacy_provenance"] = provenance
    out["checkpoint_migration_status"] = "MIGRATED" if provenance else "CURRENT"
    counter_probe = validate_counter_invariants(out)
    out["counter_invariants"] = counter_probe
    if not counter_probe["ok"]:
        out["checkpoint_counter_invariant_status"] = "FAIL_CLOSED_DRIFT"
        out["checkpoint_integrity_status"] = "COUNTER_DRIFT"
    else:
        out["checkpoint_counter_invariant_status"] = "OK"
    return out


def build_initial_checkpoint(
    *,
    packets: list[dict[str, Any]],
    manifest_checksum: str,
    model_id: str,
) -> dict[str, Any]:
    base = _build_v3_initial(
        packets=packets, manifest_checksum=manifest_checksum, model_id=model_id
    )
    return migrate_checkpoint(base, model_id=model_id)


def detect_corruption(raw_text: str | None, *, expected_manifest: str | None = None) -> dict[str, Any]:
    if raw_text is None or raw_text.strip() == "":
        return {
            "checkpoint_integrity_status": "MISSING",
            "ok": False,
            "reason": "MISSING_FILE",
        }
    try:
        state = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return {
            "checkpoint_integrity_status": "TRUNCATED_OR_CORRUPT_JSON",
            "ok": False,
            "reason": f"JSON_DECODE:{exc}",
        }
    if not isinstance(state, dict):
        return {
            "checkpoint_integrity_status": "INVALID_TYPE",
            "ok": False,
            "reason": "NOT_OBJECT",
        }
    stored = state.get("integrity_checksum")
    if stored:
        recomputed = compute_integrity_checksum(state)
        if stored != recomputed:
            return {
                "checkpoint_integrity_status": "CHECKSUM_MISMATCH",
                "ok": False,
                "reason": "INTEGRITY_CHECKSUM_MISMATCH",
                "stored": stored,
                "recomputed": recomputed,
            }
    if expected_manifest and state.get("calibration_manifest_checksum") != expected_manifest:
        return {
            "checkpoint_integrity_status": "MANIFEST_MISMATCH",
            "ok": False,
            "reason": "MANIFEST_MISMATCH",
            "stored_manifest": state.get("calibration_manifest_checksum"),
            "expected_manifest": expected_manifest,
        }
    counter_probe = validate_counter_invariants(state)
    if not counter_probe["ok"]:
        return {
            "checkpoint_integrity_status": "COUNTER_DRIFT",
            "ok": False,
            "reason": "SUCCESS_COUNT_CASE_LIST_DRIFT",
            "counter_invariants": counter_probe,
            "state": state,
        }
    return {
        "checkpoint_integrity_status": "OK",
        "ok": True,
        "reason": None,
        "counter_invariants": counter_probe,
        "state": state,
    }


def load_checkpoint(
    root: Path,
    *,
    expected_manifest: str | None = None,
    migrate: bool = True,
    model_id: str = "",
) -> dict[str, Any]:
    """Load checkpoint with corruption detection. Raises ValueError on corrupt."""
    path = checkpoint_path(root)
    if not path.is_file():
        return {
            "ok": False,
            "local_runtime_checkpoint_available": False,
            "checkpoint_integrity_status": "MISSING",
            "checkpoint_migration_status": "NOT_APPLICABLE",
            "manifest_checksum_status": "NOT_APPLICABLE",
            "real_resume_status": "LOCAL_CHECKPOINT_REQUIRED_FOR_REAL_RESUME",
            "state": None,
        }
    raw = path.read_text(encoding="utf-8")
    probe = detect_corruption(raw, expected_manifest=expected_manifest)
    if not probe["ok"]:
        return {
            "ok": False,
            "local_runtime_checkpoint_available": True,
            "checkpoint_integrity_status": probe["checkpoint_integrity_status"],
            "checkpoint_migration_status": "NOT_ATTEMPTED",
            "manifest_checksum_status": (
                "MISMATCH" if probe["checkpoint_integrity_status"] == "MANIFEST_MISMATCH" else "UNKNOWN"
            ),
            "real_resume_status": "CHECKPOINT_INVALID",
            "reason": probe.get("reason"),
            "state": None,
        }
    state = probe["state"]
    migration_status = "CURRENT"
    if migrate:
        before = int(state.get("schema_version") or 0)
        state = migrate_checkpoint(state, model_id=model_id)
        migration_status = state.get("checkpoint_migration_status") or (
            "MIGRATED" if before < CURRENT_SCHEMA_VERSION else "CURRENT"
        )
    manifest_status = "OK"
    if expected_manifest:
        manifest_status = (
            "OK"
            if state.get("calibration_manifest_checksum") == expected_manifest
            else "MISMATCH"
        )
    return {
        "ok": True,
        "local_runtime_checkpoint_available": True,
        "checkpoint_integrity_status": "OK",
        "checkpoint_migration_status": migration_status,
        "manifest_checksum_status": manifest_status,
        "real_resume_status": "READY",
        "state": state,
    }


def save_checkpoint(root: Path, state: dict[str, Any]) -> Path:
    path = checkpoint_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = sanitize_checkpoint(state)
    safe = _ensure_v4_fields(safe)
    # Recompute integrity after sanitize
    safe["integrity_checksum"] = compute_integrity_checksum(safe)
    path.write_text(json.dumps(safe, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return path

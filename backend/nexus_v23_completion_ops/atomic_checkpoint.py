"""Atomic checkpoint write + semantic counter validation for V13-B ops."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_reflection.checkpoint import (
    compute_integrity_checksum,
    sanitize_checkpoint,
    validate_counter_invariants,
)
from backend.nexus_v23_completion_ops.constants import SCHEMA_ATOMIC, SCHEMA_COUNTERS
from backend.nexus_v23_completion_ops.sanitize import assert_no_secret_keys
from backend.nexus_v23_completion_ops.sot import (
    assert_incomplete_truth,
    incomplete_sot_snapshot,
    synthetic_incomplete_checkpoint,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_checkpoint(path: Path, state: dict[str, Any]) -> dict[str, Any]:
    """Write checkpoint via temp file + os.replace (atomic on same filesystem)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe = sanitize_checkpoint(dict(state))
    # Defense-in-depth: drop remaining forbidden keys before persist.
    from backend.nexus_v23_completion_ops.sanitize import strip_forbidden_keys

    safe = strip_forbidden_keys(safe)
    if not isinstance(safe, dict):
        raise RuntimeError("atomic_checkpoint_sanitize_failed")
    if "integrity_checksum" not in safe or not safe.get("integrity_checksum"):
        safe["integrity_checksum"] = compute_integrity_checksum(safe)
    safe["updated_at"] = _utc()
    assert_no_secret_keys(safe)
    payload = json.dumps(safe, indent=2, ensure_ascii=False, default=str) + "\n"
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    prior_bytes = path.read_bytes() if path.is_file() else None
    try:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
        replaced = True
    except Exception:
        if tmp.is_file():
            try:
                tmp.unlink()
            except OSError:
                pass
        # Prior file untouched on failure (atomic replace semantics).
        if prior_bytes is not None and path.is_file():
            if path.read_bytes() != prior_bytes:
                raise RuntimeError("atomic_checkpoint_prior_corrupted_on_failure") from None
        raise
    return {
        "schema": SCHEMA_ATOMIC,
        "created_at": _utc(),
        "path": str(path),
        "atomic_replace": replaced,
        "bytes_written": len(payload.encode("utf-8")),
        "checksum_sha256": _sha_bytes(payload.encode("utf-8")),
        "integrity_checksum": safe.get("integrity_checksum"),
        "tmp_cleaned": not tmp.exists(),
        "secrets_stripped": True,
        "real_resume_executed": False,
        "V2_3_complete": False,
    }


def evaluate_atomic_checkpoint(
    *,
    root: Path | None = None,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Demonstrate atomic checkpoint round-trip on a sanitized fixture."""
    root = Path(root) if root else Path.cwd() / ".nexus_runtime" / "v13_b_fixtures"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "blind_reflection_v23_checkpoint_fixture.json"
    fixture = state or synthetic_incomplete_checkpoint()
    write_report = atomic_write_checkpoint(path, fixture)
    # Reload and verify
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    counters = validate_semantic_counters(reloaded)
    report = {
        **write_report,
        "reload_ok": True,
        "semantic_counters_ok": bool(counters.get("ok")),
        "completed_case_count": len(reloaded.get("completed_case_ids") or []),
        "pending_case_count": len(reloaded.get("pending_case_ids") or []),
        "groq_success_count": int(
            ((reloaded.get("transport") or {}).get("GROQ_REFLECTION_REASONER") or {}).get(
                "success_count"
            )
            or 0
        ),
        "sambanova_success_count": int(
            ((reloaded.get("transport") or {}).get("SAMBANOVA_INDEPENDENT_CRITIC") or {}).get(
                "success_count"
            )
            or 0
        ),
    }
    assert_incomplete_truth(report)
    return report


def validate_semantic_counters(state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Semantic counter validation: transport success must reconcile with case lists."""
    state = state or synthetic_incomplete_checkpoint()
    probe = validate_counter_invariants(state)
    completed = list(state.get("completed_case_ids") or [])
    pending = list(state.get("pending_case_ids") or [])
    critic_resolved = list(state.get("critic_resolved_ids") or [])
    critic_pending = list(
        state.get("critic_pending_ids") or state.get("pending_critic_case_ids") or []
    )
    issues = list(probe.get("issues") or [])
    overlap = set(completed) & set(pending)
    if overlap:
        issues.append(f"completed_pending_overlap:{sorted(overlap)[:3]}")
    if len(completed) != len(set(completed)):
        issues.append("completed_duplicates")
    if set(critic_resolved) - set(completed):
        issues.append("critic_resolved_without_reasoner_success")
    sot = incomplete_sot_snapshot(verify_checkpoint=False)
    # When using synthetic fixture, expect SoT alignment
    g = int(probe.get("groq_success_count") or 0)
    s = int(probe.get("critic_success_count") or 0)
    fixture_aligned = (
        g == sot["lanes"]["GROQ_REFLECTION_REASONER"]["success_count"]
        and len(pending) == sot["lanes"]["GROQ_REFLECTION_REASONER"]["pending_count"]
        and s == sot["lanes"]["SAMBANOVA_INDEPENDENT_CRITIC"]["success_count"]
        and len(critic_pending) == sot["lanes"]["SAMBANOVA_INDEPENDENT_CRITIC"]["pending_count"]
    )
    report = {
        "schema": SCHEMA_COUNTERS,
        "created_at": _utc(),
        "ok": not issues and bool(probe.get("ok")),
        "issues": issues,
        "groq_success_count": g,
        "completed_case_count": len(completed),
        "pending_case_count": len(pending),
        "critic_success_count": s,
        "critic_resolved_count": len(critic_resolved),
        "critic_pending_count": len(critic_pending),
        "fixture_sot_aligned": fixture_aligned,
        "refused_inflated_counter": not bool(probe.get("ok")),
        "V2_3_complete": False,
    }
    assert_incomplete_truth(report)
    return report

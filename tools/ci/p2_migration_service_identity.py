"""P2 migration 0007 Zeabur service identity guards (no secrets)."""
from __future__ import annotations

import re
from typing import Any

# Legacy fixed name from early runs — must never be the runtime service for a new attempt.
MIGRATION_SERVICE_BASE_NAME = "nexus-p2-migration-0007"
MIGRATION_SERVICE_NAME_PREFIX = "nexus-p2m7"
# Back-compat alias for tests that still reference the base constant name.
MIGRATION_SERVICE_NAME = MIGRATION_SERVICE_BASE_NAME
LEARNING_VALIDATION_SERVICE_NAME = "nexus-bybit-demo-learning-validation"
# Canonical live control-plane origin for the bounded-Demo learning-validation
# service, derived from its service name. The old short alias
# `nexus-bybit-demo-val.zeabur.app` is a DEAD binding (edge-404, no container).
LEARNING_VALIDATION_ORIGIN = f"https://{LEARNING_VALIDATION_SERVICE_NAME}.zeabur.app"


def learning_validation_origin() -> str:
    """One canonical, configurable bounded-Demo control-plane origin: the
    ``DEMO_VAL_URL`` env override when set, else the canonical long domain.
    Never defaults to the dead short alias."""
    import os

    return (os.environ.get("DEMO_VAL_URL") or LEARNING_VALIDATION_ORIGIN).strip().rstrip("/")


# The ONLY Zeabur service id permitted for bounded-Demo `zeabur service exec`.
LEARNING_VALIDATION_SERVICE_ID = "6a82a79aa21454a2cf6b0015"


def assert_canonical_validation_service_id(service_id: str | None) -> str:
    """Fail closed unless the id is EXACTLY the canonical learning-validation
    service. Empty, the migration-control service, or any other id is rejected —
    `zeabur service exec` must never target an arbitrary service. Returns the id."""
    sid = (service_id or "").strip()
    if not sid:
        raise ValueError("validation_service_id_missing")
    if sid != LEARNING_VALIDATION_SERVICE_ID:
        raise ValueError("validation_service_id_not_canonical")
    return sid

_RUN_SCOPED_RE = re.compile(rf"^{re.escape(MIGRATION_SERVICE_NAME_PREFIX)}-(\d+)-(\d+)$")


def safe_service_id_prefix(service_id: str | None) -> str:
    value = (service_id or "").strip()
    return value[:6] if value else "missing"


def safe_service_name_prefix(service_name: str | None) -> str:
    value = (service_name or "").strip()
    return value[:24] if value else "missing"


def build_run_scoped_migration_service_name(*, run_id: str | int, run_attempt: str | int) -> str:
    rid = str(run_id).strip()
    attempt = str(run_attempt).strip()
    if not rid or not attempt:
        raise ValueError("run_identity_missing")
    if not rid.isdigit() or not attempt.isdigit():
        raise ValueError("run_identity_invalid")
    return f"{MIGRATION_SERVICE_NAME_PREFIX}-{rid}-{attempt}"


def assert_run_scoped_service_name(
    service_name: str,
    *,
    run_id: str | int,
    run_attempt: str | int,
) -> dict[str, Any]:
    name = (service_name or "").strip()
    expected = build_run_scoped_migration_service_name(run_id=run_id, run_attempt=run_attempt)
    if not name:
        raise ValueError("migration_service_name_missing")
    if name == MIGRATION_SERVICE_BASE_NAME:
        raise ValueError("legacy_fixed_migration_service_name_forbidden")
    if name != expected:
        raise ValueError("service_name_not_run_scoped")
    match = _RUN_SCOPED_RE.fullmatch(name)
    if not match:
        raise ValueError("service_name_pattern_invalid")
    return {
        "P2_MIGRATION_RUN_SCOPED_SERVICE": True,
        "P2_MIGRATION_PREVIOUS_SERVICE_REUSED": False,
        "service_name": name,
        "service_name_prefix": safe_service_name_prefix(name),
        "run_id": match.group(1),
        "run_attempt": match.group(2),
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def assert_distinct_migration_service(
    migration_service_id: str,
    *,
    learning_validation_service_id: str,
    forbidden_service_ids: set[str],
    service_name: str | None = None,
) -> dict[str, Any]:
    migration_id = (migration_service_id or "").strip()
    learning_id = (learning_validation_service_id or "").strip()
    forbidden = {item.strip() for item in forbidden_service_ids if item and item.strip()}
    if not migration_id:
        raise ValueError("migration_service_id_missing")
    if migration_id == learning_id:
        raise ValueError("migration_service_equals_learning_validation")
    if migration_id in forbidden:
        raise ValueError("migration_service_forbidden")
    name = (service_name or "").strip()
    if name == MIGRATION_SERVICE_BASE_NAME:
        raise ValueError("legacy_fixed_migration_service_name_forbidden")
    return {
        "migration_service_distinct": True,
        "migration_service_id_prefix": safe_service_id_prefix(migration_id),
        "learning_validation_service_id_prefix": safe_service_id_prefix(learning_id),
        "service_name_prefix": safe_service_name_prefix(name) if name else "missing",
        "P2_MIGRATION_PREVIOUS_SERVICE_REUSED": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }

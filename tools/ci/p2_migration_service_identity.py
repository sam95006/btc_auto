"""P2 migration 0007 Zeabur service identity guards (no secrets)."""
from __future__ import annotations

from typing import Any

MIGRATION_SERVICE_NAME = "nexus-p2-migration-0007"
LEARNING_VALIDATION_SERVICE_NAME = "nexus-bybit-demo-learning-validation"


def safe_service_id_prefix(service_id: str | None) -> str:
    value = (service_id or "").strip()
    return value[:6] if value else "missing"


def assert_distinct_migration_service(
    migration_service_id: str,
    *,
    learning_validation_service_id: str,
    forbidden_service_ids: set[str],
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
    return {
        "migration_service_distinct": True,
        "migration_service_id_prefix": safe_service_id_prefix(migration_id),
        "learning_validation_service_id_prefix": safe_service_id_prefix(learning_id),
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }

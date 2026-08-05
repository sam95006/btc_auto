"""Public DTO schema versioning."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from backend.nexus_publishing_gateway.constants import SCHEMA
from backend.nexus_publishing_gateway.exceptions import SchemaVersionError

SUPPORTED_SCHEMAS: frozenset[str] = frozenset({SCHEMA, "public.intelligence.v1"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def assert_schema_version(version: str | None) -> str:
    if not version:
        raise SchemaVersionError("schema_version_missing")
    if version not in SUPPORTED_SCHEMAS:
        raise SchemaVersionError(f"schema_version_unsupported:{version}")
    return version


def wrap_public_envelope(
    payload: dict[str, Any],
    *,
    environment: str,
    availability: str = "AVAILABLE",
    schema_version: str = SCHEMA,
) -> dict[str, Any]:
    assert_schema_version(schema_version)
    return {
        "schema_version": schema_version,
        "published_at": utc_now_iso(),
        "environment": environment,
        "availability": availability,
        "lineage_id": str(uuid4()),
        "payload": payload,
        "system_availability": availability,
    }

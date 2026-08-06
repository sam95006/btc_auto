"""JSON Schema + lightweight validation for V17-A Data Source Registry."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.nexus_data_source_registry.constants import (
    AUTHORIZATION_CLAIM_LICENSE_TYPES,
    COST_CLASSES,
    HARD_BAN_SCRAPE_PROVIDERS,
    LEGAL_ACCESS_METHODS,
    REQUIRED_SOURCE_FIELDS,
    REVISION_POLICIES,
    SCHEMA,
    SCHEMA_REL,
    SCHEMA_VERSION,
    SCRAPE_ACCESS_METHODS,
    SOURCE_SCHEMA,
    SOURCE_STATUSES,
)


def build_source_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "nexus://v17_a/data_source_record.schema.json",
        "title": "NEXUS Data Source Record V17-A",
        "description": (
            "Machine-readable data source + license registry entry. "
            "Legal sources only: official APIs, founder-authorized commercial APIs, "
            "self-hosted/public chain, commercial-ok datasets."
        ),
        "schema_name": SOURCE_SCHEMA,
        "type": "object",
        "additionalProperties": False,
        "required": list(REQUIRED_SOURCE_FIELDS),
        "properties": {
            "source_id": {"type": "string", "minLength": 1, "pattern": "^[a-z0-9][a-z0-9_.-]*$"},
            "provider": {"type": "string", "minLength": 1},
            "dataset": {"type": "string", "minLength": 1},
            "asset_class": {"type": "string", "minLength": 1},
            "market_type": {"type": "string", "minLength": 1},
            "exchange": {"type": ["string", "null"]},
            "available_from": {"type": ["string", "null"]},
            "available_until": {"type": ["string", "null"]},
            "resolution": {"type": "string", "minLength": 1},
            "access_method": {"type": "string", "enum": sorted(LEGAL_ACCESS_METHODS)},
            "license_type": {"type": "string", "minLength": 1},
            "commercial_use_allowed": {"type": "boolean"},
            "redistribution_allowed": {"type": "boolean"},
            "training_allowed": {"type": "boolean"},
            "retention_allowed": {"type": "boolean"},
            "revision_policy": {"type": "string", "enum": sorted(REVISION_POLICIES)},
            "point_in_time_capable": {"type": "boolean"},
            "rate_limit": {"type": "string", "minLength": 1},
            "cost_class": {"type": "string", "enum": sorted(COST_CLASSES)},
            "owner": {"type": "string", "minLength": 1},
            "last_verified_at": {"type": "string", "minLength": 1},
            "status": {"type": "string", "enum": list(SOURCE_STATUSES)},
            "adapter_contract_ok": {"type": "boolean"},
            "public_display_allowed": {"type": "boolean"},
            "authorization_claimed": {"type": "boolean"},
            "notes": {"type": "string"},
        },
    }


def build_registry_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "nexus://v17_a/data_source_registry.schema.json",
        "title": "NEXUS Data Source License Registry Document V17-A",
        "schema_name": SCHEMA,
        "type": "object",
        "required": ["schema", "schema_version", "lane", "sources"],
        "properties": {
            "schema": {"const": SCHEMA},
            "schema_version": {"const": SCHEMA_VERSION},
            "lane": {"const": "V17-A"},
            "sources": {
                "type": "array",
                "items": build_source_schema(),
                "minItems": 1,
            },
        },
        "additionalProperties": True,
    }


def build_schema() -> dict[str, Any]:
    """Canonical exported schema (registry document)."""
    return build_registry_schema()


def write_schema_artifact(root: Path | None = None) -> Path:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    path = root / SCHEMA_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_schema(root: Path | None = None) -> dict[str, Any]:
    if root is None:
        root = Path(__file__).resolve().parents[2]
    path = root / SCHEMA_REL
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return build_schema()


def _as_bool(value: Any, field: str, errors: list[str]) -> bool | None:
    if not isinstance(value, bool):
        errors.append(f"bad_bool:{field}")
        return None
    return value


def validate_source_record(record: dict[str, Any]) -> list[str]:
    """Lightweight structural + license policy validation (no jsonschema dep)."""
    errors: list[str] = []
    if not isinstance(record, dict):
        return ["record_not_object"]

    for key in REQUIRED_SOURCE_FIELDS:
        if key not in record:
            errors.append(f"missing_required:{key}")

    sid = record.get("source_id")
    if not isinstance(sid, str) or not sid:
        errors.append("bad_source_id")

    status = record.get("status")
    if status not in SOURCE_STATUSES:
        errors.append(f"bad_status:{status}")

    access = str(record.get("access_method") or "").strip().lower()
    if access in SCRAPE_ACCESS_METHODS:
        errors.append(f"hard_ban_scrape_access:{access}")
    elif access and access not in LEGAL_ACCESS_METHODS:
        errors.append(f"illegal_access_method:{access}")

    provider = str(record.get("provider") or "").strip().lower()
    if provider in HARD_BAN_SCRAPE_PROVIDERS and access in SCRAPE_ACCESS_METHODS.union(
        {"web", "html", "dashboard"}
    ):
        errors.append(f"hard_ban_provider_scrape:{provider}")
    if provider in HARD_BAN_SCRAPE_PROVIDERS and "scrape" in access:
        errors.append(f"hard_ban_provider_scrape:{provider}")

    for flag in (
        "commercial_use_allowed",
        "redistribution_allowed",
        "training_allowed",
        "retention_allowed",
        "point_in_time_capable",
    ):
        _as_bool(record.get(flag), flag, errors)

    rev = record.get("revision_policy")
    if rev is not None and rev not in REVISION_POLICIES:
        errors.append(f"bad_revision_policy:{rev}")

    cost = record.get("cost_class")
    if cost is not None and cost not in COST_CLASSES:
        errors.append(f"bad_cost_class:{cost}")

    license_type = str(record.get("license_type") or "").strip().lower()
    training = record.get("training_allowed")
    redistribution = record.get("redistribution_allowed")
    public_display = record.get("public_display_allowed")
    auth_claimed = record.get("authorization_claimed")
    adapter_ok = record.get("adapter_contract_ok")

    if status == "LICENSE_REVIEW_REQUIRED":
        # Adapter contract OK; NO training; NO public display; NO auth claim.
        if adapter_ok is False:
            errors.append("license_review_adapter_contract_not_ok")
        if adapter_ok is None:
            errors.append("license_review_requires_adapter_contract_ok")
        if training is not False:
            errors.append("license_review_training_forbidden")
        if public_display is True:
            errors.append("license_review_public_display_forbidden")
        if public_display is None:
            # Default-deny: must explicitly mark false.
            errors.append("license_review_requires_public_display_allowed_false")
        if auth_claimed is True:
            errors.append("license_review_authorization_claim_forbidden")
        if auth_claimed is None:
            errors.append("license_review_requires_authorization_claimed_false")
        if license_type in AUTHORIZATION_CLAIM_LICENSE_TYPES:
            errors.append(f"license_review_authorization_license_type:{license_type}")

    if status == "TRAINING_FORBIDDEN" and training is True:
        errors.append("training_forbidden_but_training_allowed_true")

    if status == "REDISTRIBUTION_FORBIDDEN" and redistribution is True:
        errors.append("redistribution_forbidden_but_redistribution_allowed_true")

    if status == "APPROVED_PUBLIC":
        if training is not True and training is not False:
            pass
        if public_display is False:
            errors.append("approved_public_requires_public_display")
        if license_type in {"unknown", "license_unknown"}:
            errors.append("license_unknown_not_production_safe")

    if "bypass" in access or access in {"auth_bypass", "rate_limit_bypass"}:
        errors.append(f"hard_ban_bypass:{access}")

    rate = str(record.get("rate_limit") or "").lower()
    if "bypass" in rate or rate in {"unlimited_bypass", "ignore"}:
        errors.append("hard_ban_rate_limit_bypass")

    return errors


def validate_registry_document(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["document_not_object"]
    if doc.get("schema") != SCHEMA:
        errors.append("bad_schema")
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append("bad_schema_version")
    sources = doc.get("sources")
    if not isinstance(sources, list) or not sources:
        errors.append("sources_missing_or_empty")
        return errors
    seen: set[str] = set()
    for i, src in enumerate(sources):
        if not isinstance(src, dict):
            errors.append(f"source[{i}]_not_object")
            continue
        sid = str(src.get("source_id") or "")
        if sid in seen:
            errors.append(f"duplicate_source_id:{sid}")
        seen.add(sid)
        for err in validate_source_record(src):
            errors.append(f"source[{sid or i}]:{err}")
    return errors

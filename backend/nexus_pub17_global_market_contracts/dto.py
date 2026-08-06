"""Normalized market source DTO for PUB17-A.

Contracts round only: value is always null unless a real LIVE bind is supplied.
Fake Live values are refused.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.nexus_pub17_global_market_contracts.constants import (
    AVAILABILITY_STATES,
    CONTRACT_STATUSES,
    DTO_SCHEMA,
    FRESHNESS_STATES,
    MODES,
    REQUIRED_DTO_FIELDS,
    SCHEMA_VERSION,
)
from backend.nexus_pub17_global_market_contracts.contracts import source_contracts


def utc_iso(dt: datetime | None = None) -> str:
    value = dt or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_lineage_id(domain: str, source_id: str, status: str, retrieved_at: str) -> str:
    raw = f"{domain}|{source_id}|{status}|{retrieved_at}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"pub17a_{digest}"


@dataclass(frozen=True)
class NormalizedMarketSourceDto:
    """Public-safe normalized source DTO — no fabricated Live numbers."""

    schema: str
    schema_version: str
    domain: str
    source_id: str
    status: str
    mode: str
    freshness: str
    availability: str
    provenance: dict[str, Any]
    license_visibility: dict[str, Any]
    value: Any
    unit: str | None
    as_of: str | None
    retrieved_at: str
    lineage_id: str
    fabricated: bool = False
    provider: str = ""
    dataset: str = ""
    access_method: str = ""
    endpoint: str | None = None
    read_only: bool = True
    exchange_write: bool = False
    supports_live_bind: bool = False
    notes: str = ""
    private_strategy_thresholds: bool = False
    member_exchange_write: bool = False

    def to_public_dict(self) -> dict[str, Any]:
        return asdict(self)


class FabricatedLiveValueError(ValueError):
    """Raised when a caller attempts to claim LIVE with fabricated / missing bind."""


# License postures that must never surface as Live on member UI.
_LICENSE_LIVE_FORBIDDEN_STATUSES = frozenset(
    {
        "LICENSE_REVIEW_REQUIRED",
        "TRAINING_FORBIDDEN",
        "REDISTRIBUTION_FORBIDDEN",
    }
)


def _assert_no_fake_live(
    *,
    mode: str,
    value: Any,
    status: str,
    freshness: str,
    live_bind_attested: bool,
    public_display_allowed: bool | None = None,
) -> None:
    if mode == "LIVE" and not live_bind_attested:
        raise FabricatedLiveValueError("fake_live_mode_without_real_bind")
    if mode == "LIVE" and value is None:
        raise FabricatedLiveValueError("live_mode_with_null_value")
    if status == "PROVIDER_REQUIRED" and mode == "LIVE":
        raise FabricatedLiveValueError("provider_required_cannot_be_live")
    if status == "PROVIDER_REQUIRED" and value is not None:
        raise FabricatedLiveValueError("provider_required_cannot_carry_value")
    if freshness == "LIVE" and not live_bind_attested:
        raise FabricatedLiveValueError("fake_live_freshness_without_bind")
    if mode == "LIVE" and status == "CONTRACT_READY" and not live_bind_attested:
        # CONTRACT_READY alone is not a Live bind.
        raise FabricatedLiveValueError("contract_ready_is_not_live")
    # Restricted license postures must never leak to member UI as Live —
    # even if an attacker forges live_bind_attested.
    if status in _LICENSE_LIVE_FORBIDDEN_STATUSES and (
        mode == "LIVE" or freshness == "LIVE"
    ):
        raise FabricatedLiveValueError(f"license_status_cannot_be_live:{status}")
    if public_display_allowed is False and (mode == "LIVE" or freshness == "LIVE"):
        raise FabricatedLiveValueError("public_display_forbidden_cannot_be_live")


def build_normalized_dto(
    contract: dict[str, Any],
    *,
    retrieved_at: str | None = None,
    value: Any = None,
    unit: str | None = None,
    as_of: str | None = None,
    mode: str | None = None,
    freshness: str | None = None,
    availability: str | None = None,
    live_bind_attested: bool = False,
) -> NormalizedMarketSourceDto:
    """Build normalized DTO from a source contract.

    Default path (this round): mode=CONTRACT|PROVIDER_REQUIRED, value=None,
    freshness=UNAVAILABLE|PROVIDER_REQUIRED. Live only when live_bind_attested.
    """
    status = str(contract.get("status") or "")
    # TRAINING_FORBIDDEN / REDISTRIBUTION_FORBIDDEN are private registry
    # postures; refuse them on the public DTO path (must not become Live).
    if status in {"TRAINING_FORBIDDEN", "REDISTRIBUTION_FORBIDDEN"}:
        raise FabricatedLiveValueError(f"private_license_status_refused:{status}")
    if status not in CONTRACT_STATUSES:
        raise ValueError(f"bad_status:{status}")

    vis = contract.get("license_visibility") if isinstance(contract.get("license_visibility"), dict) else {}
    public_display_allowed = contract.get("public_display_allowed")
    if public_display_allowed is None and isinstance(vis, dict):
        public_display_allowed = vis.get("public_display_allowed")

    retrieved = retrieved_at or utc_iso()
    if status == "PROVIDER_REQUIRED":
        if value is not None:
            raise FabricatedLiveValueError("provider_required_cannot_carry_value")
        if mode == "LIVE" or freshness == "LIVE":
            raise FabricatedLiveValueError("provider_required_cannot_be_live")
        resolved_mode = mode or "PROVIDER_REQUIRED"
        resolved_freshness = freshness or "PROVIDER_REQUIRED"
        resolved_availability = availability or "PROVIDER_REQUIRED"
        resolved_value = None
        resolved_as_of = None
        resolved_unit = None
    elif status == "LICENSE_REVIEW_REQUIRED":
        # Adapter contract OK only — never Live chrome / Live values on member UI.
        if mode == "LIVE" or freshness == "LIVE":
            raise FabricatedLiveValueError("license_review_cannot_be_live")
        resolved_mode = mode or "CONTRACT"
        if resolved_mode == "LIVE":
            raise FabricatedLiveValueError("license_review_cannot_be_live")
        resolved_freshness = freshness or "BLOCKED"
        resolved_availability = availability or "BLOCKED"
        resolved_value = None
        resolved_as_of = None
        resolved_unit = None
        # Forged live_bind_attested must still fail closed for this status.
        live_bind_attested = False
    else:
        resolved_mode = mode or "CONTRACT"
        resolved_freshness = freshness or "UNAVAILABLE"
        resolved_availability = availability or "CONTRACT_READY"
        resolved_value = value
        resolved_as_of = as_of
        resolved_unit = unit

    _assert_no_fake_live(
        mode=resolved_mode,
        value=resolved_value,
        status=status,
        freshness=resolved_freshness,
        live_bind_attested=live_bind_attested,
        public_display_allowed=bool(public_display_allowed)
        if public_display_allowed is not None
        else None,
    )

    if resolved_mode not in MODES:
        raise ValueError(f"bad_mode:{resolved_mode}")
    if resolved_freshness not in FRESHNESS_STATES:
        raise ValueError(f"bad_freshness:{resolved_freshness}")
    if resolved_availability not in AVAILABILITY_STATES:
        raise ValueError(f"bad_availability:{resolved_availability}")

    domain = str(contract["domain"])
    source_id = str(contract["source_id"])
    return NormalizedMarketSourceDto(
        schema=DTO_SCHEMA,
        schema_version=SCHEMA_VERSION,
        domain=domain,
        source_id=source_id,
        status=status,
        mode=resolved_mode,
        freshness=resolved_freshness,
        availability=resolved_availability,
        provenance=deepcopy(contract.get("provenance") or {}),
        license_visibility=deepcopy(contract.get("license_visibility") or {}),
        value=resolved_value,
        unit=resolved_unit,
        as_of=resolved_as_of,
        retrieved_at=retrieved,
        lineage_id=make_lineage_id(domain, source_id, status, retrieved),
        fabricated=False,
        provider=str(contract.get("provider") or ""),
        dataset=str(contract.get("dataset") or ""),
        access_method=str(contract.get("access_method") or ""),
        endpoint=contract.get("endpoint"),
        read_only=bool(contract.get("read_only", True)),
        exchange_write=False,
        supports_live_bind=bool(contract.get("supports_live_bind", False)),
        notes=str(contract.get("notes") or ""),
        private_strategy_thresholds=False,
        member_exchange_write=False,
    )


def build_all_normalized_dtos(*, retrieved_at: str | None = None) -> list[dict[str, Any]]:
    retrieved = retrieved_at or utc_iso()
    return [
        build_normalized_dto(c, retrieved_at=retrieved).to_public_dict()
        for c in source_contracts()
    ]


def validate_dto(dto: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(dto, dict):
        return ["dto_not_object"]
    for key in REQUIRED_DTO_FIELDS:
        if key not in dto:
            errors.append(f"missing_dto_field:{key}")
    if dto.get("schema") != DTO_SCHEMA:
        errors.append("bad_dto_schema")
    if dto.get("fabricated") is True:
        errors.append("fabricated_flag_true")
    if dto.get("exchange_write") is True:
        errors.append("exchange_write_true")
    if dto.get("member_exchange_write") is True:
        errors.append("member_exchange_write_true")
    if dto.get("private_strategy_thresholds") is True:
        errors.append("private_strategy_thresholds_true")
    status = dto.get("status")
    mode = dto.get("mode")
    value = dto.get("value")
    freshness = dto.get("freshness")
    if status == "PROVIDER_REQUIRED":
        if value is not None:
            errors.append("provider_required_has_value")
        if mode == "LIVE":
            errors.append("provider_required_live_mode")
        if freshness == "LIVE":
            errors.append("provider_required_live_freshness")
    if status in {"LICENSE_REVIEW_REQUIRED", "TRAINING_FORBIDDEN", "REDISTRIBUTION_FORBIDDEN"}:
        if mode == "LIVE":
            errors.append(f"license_status_live_mode:{status}")
        if freshness == "LIVE":
            errors.append(f"license_status_live_freshness:{status}")
        if value is not None and mode == "LIVE":
            errors.append(f"license_status_live_value:{status}")
    if mode == "LIVE" and value is None:
        errors.append("live_null_value")
    if mode == "CONTRACT" and freshness == "LIVE":
        errors.append("contract_mode_live_freshness")
    if dto.get("read_only") is False:
        errors.append("not_read_only")
    vis = dto.get("license_visibility") if isinstance(dto.get("license_visibility"), dict) else {}
    if vis.get("public_display_allowed") is False and mode == "LIVE":
        errors.append("public_display_forbidden_live_mode")
    return errors

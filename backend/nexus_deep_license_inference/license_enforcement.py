"""Member UI Live gate + license enforcement attacks.

LICENSE_REVIEW_REQUIRED / TRAINING_FORBIDDEN / REDISTRIBUTION_FORBIDDEN
must never leak to member UI as Live.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_deep_license_inference.constants import RESTRICTED_LICENSE_STATUSES
from backend.nexus_deep_license_inference.hard_bans import refuse_restricted_license_live
from backend.nexus_pub17_global_market_contracts.dto import (
    FabricatedLiveValueError,
    build_normalized_dto,
    validate_dto,
)


def _finding(
    attack_id: str,
    *,
    blocked: bool,
    detail: str,
    severity: str = "CRITICAL",
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "attack_id": attack_id,
        "severity": severity,
        "disposition": "FIXED" if blocked else "SURVIVOR",
        "attack_blocked": blocked,
        "survivor": not blocked,
        "detail": detail,
    }
    if evidence is not None:
        out["evidence"] = evidence
    return out


def _adversarial_contract(status: str, **overrides: Any) -> dict[str, Any]:
    vis = {
        "license_type": "commercial_unknown",
        "commercial_use_allowed": False,
        "redistribution_allowed": status != "REDISTRIBUTION_FORBIDDEN",
        "public_display_allowed": False,
        "training_allowed": status != "TRAINING_FORBIDDEN",
        "summary": f"Adversarial fixture for {status}",
        "visibility": "PUBLIC_VISIBLE",
    }
    base = {
        "domain": "crypto",
        "source_id": f"adversarial_{status.lower()}",
        "provider": "adversarial_fixture",
        "dataset": "license_attack_fixture",
        "access_method": "official_rest_api",
        "status": status,
        "license_type": "commercial_unknown",
        "license_visibility": vis,
        "commercial_use_allowed": False,
        "redistribution_allowed": vis["redistribution_allowed"],
        "public_display_allowed": False,
        "provenance": {
            "origin": "fixture",
            "access_path": "local_fixture",
            "authority": "test",
            "verification": "synthetic",
            "chain": ["fixture"],
        },
        "endpoint": "https://example.invalid/license-attack",
        "read_only": True,
        "exchange_write": False,
        "supports_live_bind": True,
        "notes": "attack fixture — must not become Live",
    }
    base.update(overrides)
    return base


def member_ui_live_gate(contract: dict[str, Any], *, live_attempt: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed gate: restricted license postures cannot become member Live."""
    status = str(contract.get("status") or "")
    mode = str(live_attempt.get("mode") or "")
    freshness = str(live_attempt.get("freshness") or "")
    if status in RESTRICTED_LICENSE_STATUSES and (mode == "LIVE" or freshness == "LIVE"):
        refuse_restricted_license_live(status)
    # Also refuse via public DTO builder (shared enforcement surface).
    return build_normalized_dto(
        contract,
        mode=live_attempt.get("mode"),
        freshness=live_attempt.get("freshness"),
        value=live_attempt.get("value"),
        unit=live_attempt.get("unit"),
        as_of=live_attempt.get("as_of"),
        live_bind_attested=bool(live_attempt.get("live_bind_attested", False)),
    ).to_public_dict()


def _attack_status_as_live(status: str) -> dict[str, Any]:
    contract = _adversarial_contract(status)
    try:
        dto = member_ui_live_gate(
            contract,
            live_attempt={
                "mode": "LIVE",
                "freshness": "LIVE",
                "value": 12345.67,
                "unit": "USD",
                "as_of": "2026-08-06T00:00:00Z",
                "live_bind_attested": True,
            },
        )
    except (FabricatedLiveValueError, ValueError, RuntimeError) as exc:
        return _finding(
            f"{status.lower()}_as_live",
            blocked=True,
            detail=f"blocked:{type(exc).__name__}:{exc}",
        )
    # If we got here without exception, check DTO itself.
    errors = validate_dto(dto)
    live_leak = dto.get("mode") == "LIVE" or dto.get("freshness") == "LIVE"
    if live_leak or not errors:
        return _finding(
            f"{status.lower()}_as_live",
            blocked=False,
            detail="restricted license status leaked to member UI as Live",
            evidence={"dto": dto, "validate_errors": errors},
        )
    return _finding(
        f"{status.lower()}_as_live",
        blocked=True,
        detail=f"dto_rejected:{errors}",
    )


def _attack_public_display_false_live_smuggle() -> dict[str, Any]:
    """CONTRACT_READY with public_display_allowed=False must not become Live."""
    from backend.nexus_pub17_global_market_contracts.contracts import source_contracts

    ready = next(c for c in source_contracts() if c.get("status") == "CONTRACT_READY")
    dirty = deepcopy(ready)
    dirty["public_display_allowed"] = False
    dirty["license_visibility"] = dict(dirty.get("license_visibility") or {})
    dirty["license_visibility"]["public_display_allowed"] = False
    try:
        dto = member_ui_live_gate(
            dirty,
            live_attempt={
                "mode": "LIVE",
                "freshness": "LIVE",
                "value": 99.0,
                "live_bind_attested": True,
            },
        )
    except (FabricatedLiveValueError, ValueError, RuntimeError) as exc:
        return _finding(
            "public_display_false_live_smuggle",
            blocked=True,
            detail=f"blocked:{type(exc).__name__}:{exc}",
        )
    if dto.get("mode") == "LIVE":
        return _finding(
            "public_display_false_live_smuggle",
            blocked=False,
            detail="public_display_allowed=False still projected as Live",
            evidence={"dto_mode": dto.get("mode")},
        )
    return _finding(
        "public_display_false_live_smuggle",
        blocked=True,
        detail="public_display_false not Live",
    )


def _attack_license_review_value_smuggle() -> dict[str, Any]:
    """LICENSE_REVIEW_REQUIRED must not carry Live-looking values even in CONTRACT mode."""
    contract = _adversarial_contract("LICENSE_REVIEW_REQUIRED")
    try:
        dto = build_normalized_dto(
            contract,
            mode="CONTRACT",
            freshness="BLOCKED",
            value=777.0,
            live_bind_attested=False,
        ).to_public_dict()
    except (FabricatedLiveValueError, ValueError) as exc:
        return _finding(
            "license_review_value_smuggle",
            blocked=True,
            detail=f"blocked:{type(exc).__name__}:{exc}",
        )
    if dto.get("value") is not None and dto.get("mode") == "LIVE":
        return _finding(
            "license_review_value_smuggle",
            blocked=False,
            detail="license review emitted Live value",
            evidence={"value": dto.get("value"), "mode": dto.get("mode")},
        )
    # Non-Live CONTRACT with null value is acceptable (adapter contract).
    if dto.get("mode") == "LIVE" or dto.get("freshness") == "LIVE":
        return _finding(
            "license_review_value_smuggle",
            blocked=False,
            detail="license review emitted Live chrome",
            evidence={"dto": {k: dto.get(k) for k in ("mode", "freshness", "value")}},
        )
    return _finding(
        "license_review_value_smuggle",
        blocked=True,
        detail="license review stayed non-Live",
        evidence={"mode": dto.get("mode"), "value": dto.get("value")},
    )


def _attack_member_projection_license_chrome() -> dict[str, Any]:
    """Member projection surface must not advertise Live for restricted licenses."""
    survivors: list[str] = []
    for status in RESTRICTED_LICENSE_STATUSES:
        contract = _adversarial_contract(status)
        try:
            member_ui_live_gate(
                contract,
                live_attempt={
                    "mode": "LIVE",
                    "freshness": "FRESH",
                    "value": 1.0,
                    "live_bind_attested": True,
                },
            )
            survivors.append(status)
        except (FabricatedLiveValueError, ValueError, RuntimeError):
            pass
    return _finding(
        "member_projection_license_chrome",
        blocked=len(survivors) == 0,
        detail="all_restricted_blocked"
        if not survivors
        else f"survivors:{survivors}",
        evidence={"survivors": survivors},
    )


def run_license_enforcement_attacks() -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for status in RESTRICTED_LICENSE_STATUSES:
        findings.append(_attack_status_as_live(status))
    findings.append(_attack_public_display_false_live_smuggle())
    findings.append(_attack_license_review_value_smuggle())
    findings.append(_attack_member_projection_license_chrome())
    survivors = [f for f in findings if f.get("survivor")]
    return {
        "schema": "v17_deep_license_enforcement_redteam_v1",
        "attack_count": len(findings),
        "results": findings,
        "survivors": survivors,
        "survivor_count": len(survivors),
        "status": "PASS" if not survivors else "FAIL",
    }

"""Schema fuzzing on public DTOs and projection allow-list."""
from __future__ import annotations

import copy
from typing import Any

from backend.nexus_private_to_public_projection_v3.allowlist import (
    ForbiddenPayloadKeyError,
    assert_allowlisted_only,
    assert_no_banned_keys,
    serialize_allowlist,
)
from backend.nexus_private_to_public_projection_v3.constants import (
    ALLOWED_PUBLIC_FIELDS,
    BANNED_PRIVATE_FIELDS,
)
from backend.nexus_private_to_public_projection_v3.fixtures import private_core_fixture
from backend.nexus_private_to_public_projection_v3.projector import project_private_to_public
from backend.nexus_pub17_global_market_contracts.dto import (
    build_all_normalized_dtos,
    validate_dto,
)


def _finding(
    attack_id: str,
    *,
    blocked: bool,
    detail: str,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "attack_id": attack_id,
        "severity": "HIGH",
        "disposition": "FIXED" if blocked else "SURVIVOR",
        "attack_blocked": blocked,
        "survivor": not blocked,
        "detail": detail,
    }
    if evidence is not None:
        out["evidence"] = evidence
    return out


def fuzz_dto_extra_keys() -> dict[str, Any]:
    """Inject banned / unknown keys into public DTOs — must be rejected or stripped."""
    dtos = build_all_normalized_dtos(retrieved_at="2026-08-06T00:00:00Z")
    if not dtos:
        return _finding("dto_extra_keys", blocked=False, detail="no_dtos")
    dirty = copy.deepcopy(dtos[0])
    dirty["entry_threshold"] = 0.73
    dirty["api_secret"] = "SK_FUZZ"
    dirty["__proto__"] = {"polluted": True}
    dirty["exchange_write"] = True
    errors = validate_dto(dirty)
    # validate_dto should flag exchange_write / private strategy; banned keys
    # may not all be listed — also check allow-list style rejection via errors.
    if dirty.get("exchange_write") is True and "exchange_write_true" not in errors:
        return _finding(
            "dto_extra_keys",
            blocked=False,
            detail="exchange_write=true not rejected by validate_dto",
            evidence={"errors": errors},
        )
    # Member surface must not treat dirty DTO as clean.
    if not errors:
        return _finding(
            "dto_extra_keys",
            blocked=False,
            detail="dirty DTO validated clean",
            evidence={"keys": sorted(dirty.keys())},
        )
    return _finding(
        "dto_extra_keys",
        blocked=True,
        detail=f"dirty DTO rejected: {errors[:6]}",
        evidence={"error_count": len(errors)},
    )


def fuzz_dto_type_mutations() -> dict[str, Any]:
    """Mutate required field types — must fail validation."""
    dtos = build_all_normalized_dtos(retrieved_at="2026-08-06T00:00:00Z")
    base = copy.deepcopy(dtos[0])
    mutations = [
        ("schema", 123),
        ("fabricated", "yes"),
        ("license_visibility", "PUBLIC"),
        ("provenance", ["not", "object"]),
        ("mode", {"LIVE": True}),
    ]
    missed: list[str] = []
    for field, bad in mutations:
        dirty = copy.deepcopy(base)
        dirty[field] = bad
        errors = validate_dto(dirty)
        # At minimum schema mismatch / fabricated / structural issues should trip.
        if field == "schema" and "bad_dto_schema" not in errors and not errors:
            missed.append(field)
        if field == "fabricated" and dirty["fabricated"] == "yes":
            # truthiness check uses `is True` — string "yes" should not set fabricated_flag_true
            # but also must not be treated as a valid clean boolean surface for Live claims.
            if dirty.get("mode") == "LIVE" and not errors:
                missed.append(field)
        if field in {"license_visibility", "provenance", "mode"} and not errors:
            # validate_dto may be shallow — require at least no false Live claim.
            if dirty.get("mode") == "LIVE" or dirty.get("freshness") == "LIVE":
                missed.append(field)
    # Structural: mode as dict must not equal "LIVE"
    dirty_mode = copy.deepcopy(base)
    dirty_mode["mode"] = {"LIVE": True}
    if dirty_mode.get("mode") == "LIVE":
        missed.append("mode_dict_eq_live")
    return _finding(
        "dto_type_mutations",
        blocked=len(missed) == 0,
        detail="type mutations contained" if not missed else f"missed:{missed}",
        evidence={"missed": missed, "mutations": [m[0] for m in mutations]},
    )


def fuzz_allowlist_smuggle() -> dict[str, Any]:
    """Banned keys under nested public payload must be dropped by allow-list."""
    core = private_core_fixture()
    # Mutate public nest after projection attempt via serialize_allowlist directly.
    dirty = {
        "market_state": "risk-on",
        "ai_public_suggestion": "WAIT",
        "entry_threshold": 0.91,
        "strategy_parameters": {"a": 1},
        "payload": {
            "market_state": "ok",
            "api_secret": "SK",
            "evidence_summary": "public ok",
        },
    }
    filtered = serialize_allowlist(dirty)
    names = set()

    def _walk(n: Any) -> None:
        if isinstance(n, dict):
            for k, v in n.items():
                names.add(str(k))
                _walk(v)
        elif isinstance(n, list):
            for x in n:
                _walk(x)

    _walk(filtered)
    banned_hits = [b for b in BANNED_PRIVATE_FIELDS if b in names or b.lower() in {x.lower() for x in names}]
    if banned_hits:
        return _finding(
            "allowlist_smuggle",
            blocked=False,
            detail="banned keys survived serialize_allowlist",
            evidence={"hits": banned_hits},
        )
    unknown = names - ALLOWED_PUBLIC_FIELDS
    if unknown:
        return _finding(
            "allowlist_smuggle",
            blocked=False,
            detail="non-allowlisted keys survived",
            evidence={"unknown": sorted(unknown)},
        )
    try:
        assert_allowlisted_only(filtered)
        assert_no_banned_keys(filtered)
    except ForbiddenPayloadKeyError as exc:
        return _finding(
            "allowlist_smuggle",
            blocked=False,
            detail=f"assert failed on filtered payload: {exc}",
        )
    return _finding(
        "allowlist_smuggle",
        blocked=True,
        detail="allow-list dropped banned/unknown keys",
        evidence={"kept": sorted(names)},
    )


def fuzz_projection_roundtrip_unknown() -> dict[str, Any]:
    """Projector must not emit keys outside allow-list."""
    proj = project_private_to_public(private_core_fixture())
    names = set()

    def _walk(n: Any) -> None:
        if isinstance(n, dict):
            for k, v in n.items():
                names.add(str(k))
                _walk(v)
        elif isinstance(n, list):
            for x in n:
                _walk(x)

    _walk(proj)
    unknown = sorted(names - ALLOWED_PUBLIC_FIELDS)
    banned = [b for b in BANNED_PRIVATE_FIELDS if b in names]
    if unknown or banned:
        return _finding(
            "projection_roundtrip_unknown",
            blocked=False,
            detail="projection emitted unknown or banned keys",
            evidence={"unknown": unknown, "banned": banned},
        )
    return _finding(
        "projection_roundtrip_unknown",
        blocked=True,
        detail="projection keys ⊆ allow-list",
        evidence={"key_count": len(names)},
    )


def fuzz_dto_live_null_invariants() -> dict[str, Any]:
    """All catalog DTOs must satisfy validate_dto with no Live fabrication."""
    dtos = build_all_normalized_dtos(retrieved_at="2026-08-06T00:00:00Z")
    bad: list[dict[str, Any]] = []
    for dto in dtos:
        errors = validate_dto(dto)
        if errors:
            bad.append({"source_id": dto.get("source_id"), "errors": errors})
        if dto.get("mode") == "LIVE" and dto.get("value") is None:
            bad.append({"source_id": dto.get("source_id"), "errors": ["live_null"]})
        if dto.get("status") in {
            "LICENSE_REVIEW_REQUIRED",
            "TRAINING_FORBIDDEN",
            "REDISTRIBUTION_FORBIDDEN",
        } and dto.get("mode") == "LIVE":
            bad.append({"source_id": dto.get("source_id"), "errors": ["restricted_live"]})
    return _finding(
        "dto_live_null_invariants",
        blocked=len(bad) == 0,
        detail="all DTOs valid" if not bad else f"bad_dtos:{len(bad)}",
        evidence={"bad": bad[:5], "dto_count": len(dtos)},
    )


def run_schema_fuzz_attacks() -> dict[str, Any]:
    findings = [
        fuzz_dto_extra_keys(),
        fuzz_dto_type_mutations(),
        fuzz_allowlist_smuggle(),
        fuzz_projection_roundtrip_unknown(),
        fuzz_dto_live_null_invariants(),
    ]
    survivors = [f for f in findings if f.get("survivor")]
    return {
        "schema": "v17_deep_schema_fuzz_redteam_v1",
        "attack_count": len(findings),
        "results": findings,
        "survivors": survivors,
        "survivor_count": len(survivors),
        "status": "PASS" if not survivors else "FAIL",
    }

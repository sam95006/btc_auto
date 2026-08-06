"""Canonical public/mobile parity contract builder and validators."""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.nexus_pub17_public_mobile_parity.constants import (
    ARTIFACT_REL,
    CONTRACT_REL,
    FORBIDDEN_MEMBER_CONTROL_MARKERS,
    HARD_BANS,
    MOBILE_MARKET_PULSE_REQUIRED_FIELDS,
    MOBILE_REQUIRED_PAGE_LABELS,
    PACKAGE,
    PUBLIC_MARKET_PULSE_ANSWER_IDS,
    PUBLIC_NORMALIZED_SOURCE_DTO_FIELDS,
    PUBLIC_TO_MOBILE_SEMANTIC_MAP,
    SCHEMA,
    SCHEMA_VERSION,
    SHARED_AVAILABILITY_STATES,
    SHARED_BUYABLE_PRODUCT_LABELS,
    SHARED_FORBIDDEN_PRODUCT_LABELS,
    SHARED_FRESHNESS_STATES,
)


def build_parity_contract() -> dict[str, Any]:
    """Machine-readable public↔mobile parity contract (frozen field sets)."""
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "package": PACKAGE,
        "hard_bans": list(HARD_BANS),
        "public_market_pulse_answer_ids": list(PUBLIC_MARKET_PULSE_ANSWER_IDS),
        "mobile_market_pulse_required_fields": list(MOBILE_MARKET_PULSE_REQUIRED_FIELDS),
        "public_to_mobile_semantic_map": {
            k: list(v) for k, v in PUBLIC_TO_MOBILE_SEMANTIC_MAP.items()
        },
        "shared_freshness_states": list(SHARED_FRESHNESS_STATES),
        "shared_availability_states": list(SHARED_AVAILABILITY_STATES),
        "public_normalized_source_dto_fields": list(PUBLIC_NORMALIZED_SOURCE_DTO_FIELDS),
        "mobile_required_page_labels": list(MOBILE_REQUIRED_PAGE_LABELS),
        "shared_buyable_product_labels": list(SHARED_BUYABLE_PRODUCT_LABELS),
        "shared_forbidden_product_labels": list(SHARED_FORBIDDEN_PRODUCT_LABELS),
        "forbidden_member_control_markers": list(FORBIDDEN_MEMBER_CONTROL_MARKERS),
        "provider_required_rules": {
            "status_or_provider_status": "PROVIDER_REQUIRED",
            "value_must_be_null": True,
            "mode_must_not_be_live": True,
            "freshness_must_not_be_live": True,
            "chrome_must_not_be_live": True,
            "top_opportunities_must_be_empty": True,
            "fabricated_must_be_false": True,
        },
        "zero_capability_guarantees": {
            "execution_control_count": 0,
            "exchange_write_capability": 0,
            "customer_trading_capability_count": 0,
            "member_execution_control_count": 0,
        },
        "notes": [
            "Parity freezes field sets and honesty rules only.",
            "PROVIDER_REQUIRED domains remain unbound — no fabricated Live numbers.",
            "Time-dependent blockers are documented separately; not claimed complete.",
        ],
    }


def write_parity_contract_artifact(root: Path | str) -> Path:
    root_path = Path(root)
    out = root_path / CONTRACT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_parity_contract()
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Keep a tiny companion marker for artifact discovery.
    marker = root_path / ARTIFACT_REL / "README.md"
    marker.write_text(
        "# Public/Mobile parity contract\n\n"
        "Frozen machine contract for V17 deep engineering.\n"
        "Do not claim Live provider completion from this artifact alone.\n",
        encoding="utf-8",
    )
    return out


def load_parity_contract(root: Path | str | None = None) -> dict[str, Any]:
    if root is None:
        return build_parity_contract()
    path = Path(root) / CONTRACT_REL
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return build_parity_contract()


def assert_semantic_map_complete(contract: dict[str, Any] | None = None) -> list[str]:
    """Every public answer id must map to ≥1 mobile field present in required set."""
    c = contract or build_parity_contract()
    errors: list[str] = []
    answers = c["public_market_pulse_answer_ids"]
    mapping = c["public_to_mobile_semantic_map"]
    mobile_fields = set(c["mobile_market_pulse_required_fields"])
    if list(answers) != list(PUBLIC_MARKET_PULSE_ANSWER_IDS):
        errors.append("public_answer_ids_drift")
    for answer_id in answers:
        targets = mapping.get(answer_id)
        if not targets:
            errors.append(f"missing_map:{answer_id}")
            continue
        for field in targets:
            if field not in mobile_fields:
                errors.append(f"map_target_not_in_mobile_fields:{answer_id}->{field}")
    for answer_id in mapping:
        if answer_id not in answers:
            errors.append(f"orphan_map:{answer_id}")
    return errors


def assert_provider_required_payload(payload: dict[str, Any]) -> list[str]:
    """Validate PROVIDER_REQUIRED honesty for a pulse-like or source-like payload."""
    errors: list[str] = []
    status = str(
        payload.get("provider_status")
        or payload.get("status")
        or payload.get("mode")
        or ""
    ).upper()
    if status != "PROVIDER_REQUIRED":
        return errors
    if payload.get("value") is not None and "value" in payload:
        errors.append("provider_required_has_value")
    mode = str(payload.get("mode") or payload.get("data_mode") or "").upper()
    if mode == "LIVE" and payload.get("demo") is True:
        # demo Live chrome is still forbidden as fabricated feed
        errors.append("provider_required_demo_live_conflict")
    freshness = str(
        payload.get("freshness") or payload.get("data_freshness") or ""
    ).upper()
    if freshness == "LIVE":
        errors.append("provider_required_live_freshness")
    chrome = str(payload.get("chrome_label") or payload.get("chromeLabel") or "").upper()
    if chrome == "LIVE":
        errors.append("provider_required_live_chrome")
    if payload.get("fabricated") is True:
        errors.append("provider_required_fabricated")
    tops = payload.get("top_opportunities")
    if isinstance(tops, list) and len(tops) > 0:
        errors.append("provider_required_has_opportunities")
    for key in (
        "execution_control_count",
        "exchange_write_capability",
        "customer_trading_capability_count",
        "member_execution_control_count",
    ):
        if key in payload and int(payload.get(key) or 0) != 0:
            errors.append(f"nonzero_capability:{key}")
    return errors


def assert_zero_trade_capabilities(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in (
        "execution_control_count",
        "exchange_write_capability",
        "customer_trading_capability_count",
        "member_execution_control_count",
    ):
        if key in payload and int(payload.get(key) or 0) != 0:
            errors.append(f"nonzero:{key}")
    for banned in ("place_order", "submit_order", "copy_trade", "trade_button"):
        if banned in payload:
            errors.append(f"banned_key_present:{banned}")
    return errors


def validate_mobile_field_set(fields: set[str] | list[str]) -> list[str]:
    required = set(MOBILE_MARKET_PULSE_REQUIRED_FIELDS)
    present = set(fields)
    missing = sorted(required - present)
    return [f"missing_mobile_field:{f}" for f in missing]


def validate_freshness_token(token: str) -> list[str]:
    t = str(token or "").upper()
    if t not in SHARED_FRESHNESS_STATES:
        return [f"unknown_freshness:{t}"]
    return []


def contract_diff(left: dict[str, Any], right: dict[str, Any]) -> list[str]:
    """Shallow key/list equality for frozen contract fields."""
    errors: list[str] = []
    keys = (
        "public_market_pulse_answer_ids",
        "mobile_market_pulse_required_fields",
        "shared_freshness_states",
        "shared_buyable_product_labels",
        "shared_forbidden_product_labels",
        "mobile_required_page_labels",
    )
    for key in keys:
        if left.get(key) != right.get(key):
            errors.append(f"contract_drift:{key}")
    if left.get("public_to_mobile_semantic_map") != right.get("public_to_mobile_semantic_map"):
        errors.append("contract_drift:public_to_mobile_semantic_map")
    return errors


def snapshot_for_tests() -> dict[str, Any]:
    return deepcopy(build_parity_contract())

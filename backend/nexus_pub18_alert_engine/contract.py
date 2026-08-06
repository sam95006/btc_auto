"""PUB18 Alert Engine — machine contract builder + envelope validator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from backend.nexus_pub18_alert_engine.constants import (
    ALERT_KIND_LABELS,
    ALERT_KINDS,
    ARTIFACT_REL,
    CONTRACT_REL,
    DATA_CLASS_LABELS,
    FORBIDDEN_PAYLOAD_KEYS,
    FRESHNESS_STATES,
    HARD_BANS,
    HYPE_PHRASES,
    PACKAGE,
    PROGRAM_ID,
    REQUIRED_FIELDS,
    SCHEMA,
    SCHEMA_VERSION,
    SEVERITIES,
)
from backend.nexus_pub18_alert_engine.hard_bans import (
    HardBanViolation,
    assert_no_forbidden_keys,
    assert_no_hype_phrases,
    assert_public_safe,
    assert_stale_has_indicator,
)


def build_alert_engine_contract() -> dict[str, Any]:
    """Frozen shared web/mobile Alert Engine read-only contract."""
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "package": PACKAGE,
        "program_id": PROGRAM_ID,
        "mode": "READ_ONLY",
        "shared_surfaces": ["web", "mobile"],
        "alert_kinds": list(ALERT_KINDS),
        "alert_kind_labels": dict(ALERT_KIND_LABELS),
        "required_fields": list(REQUIRED_FIELDS),
        "severities": list(SEVERITIES),
        "freshness_states": list(FRESHNESS_STATES),
        "data_class_labels": list(DATA_CLASS_LABELS),
        "hype_phrases_banned": list(HYPE_PHRASES),
        "forbidden_payload_keys": sorted(FORBIDDEN_PAYLOAD_KEYS),
        "hard_bans": list(HARD_BANS),
        "guarantees": {
            "read_only": True,
            "actionable_trade": False,
            "public_safe_required": True,
            "execution_control_count": 0,
            "exchange_write_capability": 0,
            "member_execution_control_count": 0,
            "fabricated_live_alerts": 0,
            "unavailable_as_zero": 0,
            "stale_without_indicator": 0,
        },
        "notes": [
            "Contract freezes kinds + honesty fields for web and mobile parity.",
            "Alerts are informational only — never claim orders already placed.",
            "LIVE_READ_ONLY requires non-demo freshness; otherwise use FIXTURE/DEMO_DATA.",
        ],
    }


def write_alert_engine_contract_artifact(root: Path | str) -> Path:
    root_path = Path(root)
    out = root_path / CONTRACT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_alert_engine_contract()
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    marker = root_path / ARTIFACT_REL / "README.md"
    marker.write_text(
        "# PUB18 Alert Engine read-only contract\n\n"
        "Shared web/mobile alert kinds and honesty fields.\n"
        "Informational only — no execution controls.\n",
        encoding="utf-8",
    )
    return out


def validate_alert_envelope(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a candidate alert envelope against the shared contract."""
    errors: list[str] = []
    data = dict(payload)

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"missing_required_field:{field}")

    kind = data.get("kind")
    if kind not in ALERT_KINDS:
        errors.append(f"unsupported_kind:{kind}")

    if data.get("severity") not in SEVERITIES:
        errors.append(f"unsupported_severity:{data.get('severity')}")

    if data.get("freshness") not in FRESHNESS_STATES:
        errors.append(f"unsupported_freshness:{data.get('freshness')}")

    if data.get("data_class") not in DATA_CLASS_LABELS:
        errors.append(f"unsupported_data_class:{data.get('data_class')}")

    try:
        assert_public_safe(data)
    except HardBanViolation as exc:
        errors.append(str(exc))

    try:
        assert_no_forbidden_keys(data)
    except HardBanViolation as exc:
        errors.append(str(exc))

    try:
        assert_no_hype_phrases(
            str(data.get("title") or ""),
            str(data.get("body") or ""),
            str(data.get("reason") or ""),
        )
    except HardBanViolation as exc:
        errors.append(str(exc))

    try:
        assert_stale_has_indicator(
            freshness=str(data.get("freshness") or ""),
            data_class=str(data.get("data_class") or ""),
        )
    except HardBanViolation as exc:
        errors.append(str(exc))

    if data.get("data_class") == "LIVE_READ_ONLY" and data.get("freshness") in {
        "DEMO_DATA",
        "FIXTURE",
        "UNAVAILABLE",
    }:
        errors.append("fabricated_live_alert")

    if data.get("actionable_trade") is True:
        errors.append("actionable_trade_forbidden")

    if data.get("read_only") is False:
        errors.append("read_only_required")

    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "kind": kind,
        "public_safe": data.get("public_safe"),
    }

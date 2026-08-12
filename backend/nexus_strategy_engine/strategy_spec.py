"""NEXUS_STRATEGY_SPEC_V1 — declarative strategy definitions."""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from backend.nexus_strategy_engine.constants import STRATEGY_SPEC_SCHEMA_VERSION

REQUIRED_SPEC_KEYS = (
    "strategy_id",
    "strategy_family",
    "economic_mechanism",
    "required_data_capabilities",
    "eligible_symbol_profile",
    "excluded_symbol_conditions",
    "eligible_regimes",
    "excluded_regimes",
    "context_timeframe",
    "event_timeframe",
    "entry_timeframe",
    "execution_resolution_timeframe",
    "context_definition",
    "event_definition",
    "confirmation_definition",
    "entry_definition",
    "late_entry_definition",
    "stop_definition",
    "target_definition",
    "exit_definition",
    "maximum_holding_period",
    "cost_buffer_definition",
    "spread_limit_definition",
    "slippage_limit_definition",
    "liquidity_requirement",
    "risk_model_reference",
    "position_size_model_reference",
    "development_interval_ids",
    "replay_interval_ids",
    "excluded_interval_ids",
    "parameter_source",
    "economic_rationale",
    "preregistration_timestamp",
    "strategy_checksum",
    "semantic_checksum",
    "AI_provider_identities",
    "prompt_schema_versions",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def strategy_spec_schema() -> dict[str, Any]:
    return {
        "schema": STRATEGY_SPEC_SCHEMA_VERSION,
        "required": list(REQUIRED_SPEC_KEYS),
        "notes": [
            "Executable without per-hypothesis Python edits",
            "Checksums frozen before development research execution",
            "Not a qualification status carrier",
        ],
    }


def semantic_payload(spec: dict[str, Any]) -> dict[str, Any]:
    """Economic identity only — excludes timestamps and provider run ids."""
    keys = (
        "strategy_family",
        "economic_mechanism",
        "required_data_capabilities",
        "eligible_symbol_profile",
        "excluded_symbol_conditions",
        "eligible_regimes",
        "excluded_regimes",
        "context_timeframe",
        "event_timeframe",
        "entry_timeframe",
        "execution_resolution_timeframe",
        "context_definition",
        "event_definition",
        "confirmation_definition",
        "entry_definition",
        "late_entry_definition",
        "stop_definition",
        "target_definition",
        "exit_definition",
        "maximum_holding_period",
        "cost_buffer_definition",
        "spread_limit_definition",
        "slippage_limit_definition",
        "liquidity_requirement",
        "parameter_source",
        "economic_rationale",
    )
    return {k: deepcopy(spec.get(k)) for k in keys}


def compute_strategy_checksum(spec: dict[str, Any]) -> str:
    body = {k: deepcopy(spec.get(k)) for k in REQUIRED_SPEC_KEYS if k not in {"strategy_checksum", "semantic_checksum"}}
    return sha_obj(body)


def compute_semantic_checksum(spec: dict[str, Any]) -> str:
    return sha_obj(semantic_payload(spec))


def freeze_spec(spec: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(spec)
    if not out.get("preregistration_timestamp"):
        out["preregistration_timestamp"] = _utc()
    out["semantic_checksum"] = compute_semantic_checksum(out)
    out["strategy_checksum"] = compute_strategy_checksum(out)
    missing = [k for k in REQUIRED_SPEC_KEYS if k not in out]
    if missing:
        raise ValueError(f"strategy_spec_missing:{missing}")
    return out


def validate_spec(spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for k in REQUIRED_SPEC_KEYS:
        if k not in spec:
            errors.append(f"missing:{k}")
    if spec.get("strategy_checksum") != compute_strategy_checksum(spec):
        errors.append("strategy_checksum_mismatch")
    if spec.get("semantic_checksum") != compute_semantic_checksum(spec):
        errors.append("semantic_checksum_mismatch")
    return errors

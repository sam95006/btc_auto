"""Silver instrument schema validation."""
from __future__ import annotations

from typing import Any

from backend.nexus_silver_symbol_identity.constants import (
    CANONICAL_IDENTITY_FIELDS,
    MARGIN_KINDS,
    MARKET_TYPES,
    SCHEMA,
)
from backend.nexus_silver_symbol_identity.identity import (
    build_canonical_asset_id,
    build_canonical_instrument_id,
)


REQUIRED_FIELDS = CANONICAL_IDENTITY_FIELDS


def build_schema() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "title": "NEXUS Silver Symbol Identity",
        "type": "object",
        "required": list(REQUIRED_FIELDS),
        "properties": {
            "canonical_asset_id": {"type": "string", "pattern": r"^asset:[a-z0-9_\-]+$"},
            "canonical_instrument_id": {"type": "string", "pattern": r"^inst:"},
            "exchange": {"type": "string", "minLength": 1},
            "exchange_symbol": {"type": "string", "minLength": 1},
            "market_type": {"enum": list(MARKET_TYPES)},
            "quote_asset": {"type": "string", "minLength": 1},
            "base_asset": {"type": "string", "minLength": 1},
            "contract_multiplier": {"type": "number"},
            "margin_kind": {"enum": list(MARGIN_KINDS)},
            "tick_size": {"type": "number", "exclusiveMinimum": 0},
            "lot_size": {"type": "number", "exclusiveMinimum": 0},
            "min_notional": {"type": "number", "minimum": 0},
            "listing_time": {"type": ["string", "null"]},
            "delisting_time": {"type": ["string", "null"]},
            "contract_rule_version": {"type": "string", "minLength": 1},
            "rename_lineage_id": {"type": ["string", "null"]},
            "predecessor_instrument_id": {"type": ["string", "null"]},
            "successor_instrument_id": {"type": ["string", "null"]},
            "status": {"enum": ["active", "delisted", "renamed"]},
            "depeg_periods": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["asset", "start_time", "end_time", "peg_asset"],
                },
            },
        },
        "additionalProperties": True,
    }


def validate_silver_instrument(record: dict[str, Any]) -> dict[str, Any]:
    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        return {"ok": False, "status": "MISSING_FIELDS", "missing": missing}

    mt = record.get("market_type")
    if mt not in MARKET_TYPES:
        return {"ok": False, "status": "INVALID_MARKET_TYPE", "market_type": mt}

    mk = record.get("margin_kind")
    if mk not in MARGIN_KINDS:
        return {"ok": False, "status": "INVALID_MARGIN_KIND", "margin_kind": mk}
    if mt == "spot" and mk != "na":
        return {"ok": False, "status": "SPOT_MUST_BE_NA_MARGIN", "margin_kind": mk}
    if mt != "spot" and mk == "na":
        return {"ok": False, "status": "DERIVATIVE_REQUIRES_MARGIN_KIND", "margin_kind": mk}

    for num_field in ("tick_size", "lot_size", "min_notional", "contract_multiplier"):
        try:
            val = float(record[num_field])
        except (TypeError, ValueError, KeyError):
            return {"ok": False, "status": "INVALID_NUMERIC", "field": num_field}
        if num_field in ("tick_size", "lot_size") and val <= 0:
            return {"ok": False, "status": "NON_POSITIVE_SIZE", "field": num_field}

    expected_asset = build_canonical_asset_id(str(record["base_asset"]))
    if record.get("canonical_asset_id") != expected_asset:
        return {
            "ok": False,
            "status": "ASSET_ID_MISMATCH",
            "expected": expected_asset,
            "actual": record.get("canonical_asset_id"),
        }

    expected_inst = build_canonical_instrument_id(
        exchange=str(record["exchange"]),
        exchange_symbol=str(record["exchange_symbol"]),
        market_type=str(record["market_type"]),
        quote_asset=str(record["quote_asset"]),
        margin_kind=str(record["margin_kind"]),
        contract_multiplier=record["contract_multiplier"],
        contract_rule_version=str(record["contract_rule_version"]),
    )
    if record.get("canonical_instrument_id") != expected_inst:
        return {
            "ok": False,
            "status": "INSTRUMENT_ID_MISMATCH",
            "expected": expected_inst,
            "actual": record.get("canonical_instrument_id"),
        }

    return {"ok": True, "status": "PASS"}

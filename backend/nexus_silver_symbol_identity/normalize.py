"""Normalize raw/bronze instrument observations into silver identity records."""
from __future__ import annotations

from typing import Any

from backend.nexus_silver_symbol_identity.identity import (
    build_canonical_asset_id,
    build_canonical_instrument_id,
    normalize_asset_code,
)
from backend.nexus_silver_symbol_identity.schema import validate_silver_instrument


def _as_float(value: Any, default: float) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def normalize_raw_instrument(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a raw exchange instrument observation to a silver identity record.

    Does not call exchanges. Fixture / bronze-lake inputs only.
    """
    exchange = str(raw.get("exchange") or raw.get("venue") or "").strip().lower()
    exchange_symbol = str(raw.get("exchange_symbol") or raw.get("symbol") or "").strip().upper()
    market_type = str(raw.get("market_type") or raw.get("product_type") or "").strip().lower()
    base_asset = normalize_asset_code(str(raw.get("base_asset") or raw.get("base_coin") or ""))
    quote_asset = normalize_asset_code(str(raw.get("quote_asset") or raw.get("quote_coin") or ""))
    margin_kind = str(raw.get("margin_kind") or raw.get("contract_type") or "").strip().lower()
    if market_type == "spot":
        margin_kind = "na"
    elif margin_kind in {"linear", "inverse"}:
        pass
    else:
        # Infer linear USDT-settled perps when unspecified.
        settle = normalize_asset_code(str(raw.get("settle_asset") or raw.get("settle_coin") or ""))
        margin_kind = "inverse" if settle and settle == base_asset else "linear"

    contract_rule_version = str(
        raw.get("contract_rule_version") or raw.get("spec_version") or "v1"
    ).strip()
    contract_multiplier = _as_float(raw.get("contract_multiplier", 1), 1.0)
    tick_size = _as_float(raw.get("tick_size"), 0.01)
    lot_size = _as_float(raw.get("lot_size") or raw.get("qty_step"), 0.001)
    min_notional = _as_float(raw.get("min_notional") or raw.get("minimum_notional"), 0.0)
    listing_time = raw.get("listing_time") or raw.get("listing_time_iso") or raw.get("listing_ms")
    delisting_time = raw.get("delisting_time") or raw.get("delisting_time_iso") or raw.get("delisting_ms")
    if isinstance(listing_time, (int, float)):
        listing_time = _ms_to_iso(int(listing_time))
    if isinstance(delisting_time, (int, float)):
        delisting_time = _ms_to_iso(int(delisting_time))

    status = "active"
    if delisting_time:
        status = "delisted"
    if raw.get("renamed_to") or raw.get("successor_symbol"):
        status = "renamed"

    record = {
        "canonical_asset_id": build_canonical_asset_id(base_asset),
        "canonical_instrument_id": build_canonical_instrument_id(
            exchange=exchange,
            exchange_symbol=exchange_symbol,
            market_type=market_type,
            quote_asset=quote_asset,
            margin_kind=margin_kind,
            contract_multiplier=contract_multiplier,
            contract_rule_version=contract_rule_version,
        ),
        "exchange": exchange,
        "exchange_symbol": exchange_symbol,
        "market_type": market_type,
        "quote_asset": quote_asset,
        "base_asset": base_asset,
        "contract_multiplier": contract_multiplier,
        "margin_kind": margin_kind,
        "tick_size": tick_size,
        "lot_size": lot_size,
        "min_notional": min_notional,
        "listing_time": listing_time,
        "delisting_time": delisting_time,
        "contract_rule_version": contract_rule_version,
        "rename_lineage_id": raw.get("rename_lineage_id"),
        "predecessor_instrument_id": raw.get("predecessor_instrument_id"),
        "successor_instrument_id": raw.get("successor_instrument_id"),
        "status": status,
        "depeg_periods": list(raw.get("depeg_periods") or []),
    }
    check = validate_silver_instrument(record)
    if not check["ok"]:
        raise ValueError(f"silver_normalize_failed:{check}")
    return record


def _ms_to_iso(ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

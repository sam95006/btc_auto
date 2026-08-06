"""Symbol rename lineage — old identities retained, never silently remapped."""
from __future__ import annotations

import hashlib
import json
from typing import Any


def build_rename_lineage_id(
    *,
    exchange: str,
    old_symbol: str,
    new_symbol: str,
    effective_time: str,
) -> str:
    material = {
        "exchange": str(exchange).lower(),
        "old_symbol": str(old_symbol).upper(),
        "new_symbol": str(new_symbol).upper(),
        "effective_time": str(effective_time),
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:20]
    return f"rename:{material['exchange']}:{material['old_symbol']}->{material['new_symbol']}:{digest}"


def apply_symbol_rename(
    *,
    old_record: dict[str, Any],
    new_symbol: str,
    effective_time: str,
    new_contract_rule_version: str | None = None,
    normalize_fn,
) -> dict[str, Any]:
    """Return lineage payload retaining both old and new silver records.

    Old record is marked ``renamed`` (not erased). New record links back via
    ``predecessor_instrument_id`` and shared ``rename_lineage_id``.
    """
    if str(old_record.get("exchange_symbol") or "").upper() == str(new_symbol).upper():
        raise ValueError("rename_requires_distinct_symbol")

    lineage_id = build_rename_lineage_id(
        exchange=str(old_record["exchange"]),
        old_symbol=str(old_record["exchange_symbol"]),
        new_symbol=new_symbol,
        effective_time=effective_time,
    )

    raw_new = {
        "exchange": old_record["exchange"],
        "exchange_symbol": new_symbol,
        "market_type": old_record["market_type"],
        "base_asset": old_record["base_asset"],
        "quote_asset": old_record["quote_asset"],
        "margin_kind": old_record["margin_kind"],
        "contract_multiplier": old_record["contract_multiplier"],
        "tick_size": old_record["tick_size"],
        "lot_size": old_record["lot_size"],
        "min_notional": old_record["min_notional"],
        "listing_time": effective_time,
        "delisting_time": None,
        "contract_rule_version": new_contract_rule_version
        or old_record["contract_rule_version"],
        "depeg_periods": list(old_record.get("depeg_periods") or []),
    }
    new_record = normalize_fn(raw_new)

    retained_old = dict(old_record)
    retained_old["status"] = "renamed"
    retained_old["delisting_time"] = retained_old.get("delisting_time") or effective_time
    retained_old["rename_lineage_id"] = lineage_id
    retained_old["successor_instrument_id"] = new_record["canonical_instrument_id"]

    new_record["status"] = "active"
    new_record["rename_lineage_id"] = lineage_id
    new_record["predecessor_instrument_id"] = old_record["canonical_instrument_id"]

    return {
        "ok": True,
        "rename_lineage_id": lineage_id,
        "effective_time": effective_time,
        "old": retained_old,
        "new": new_record,
        "erased_old": False,
    }


def detect_silent_rename(
    *,
    previous_symbol: str,
    observed_symbol: str,
    rename_lineage_id: str | None,
) -> dict[str, Any]:
    """Fail-closed: symbol remapping without lineage is blocked."""
    changed = str(previous_symbol).upper() != str(observed_symbol).upper()
    silent = changed and not rename_lineage_id
    return {
        "ok": not silent,
        "status": "SILENT_RENAME" if silent else "PASS",
        "previous_symbol": previous_symbol,
        "observed_symbol": observed_symbol,
        "rename_lineage_id": rename_lineage_id,
    }

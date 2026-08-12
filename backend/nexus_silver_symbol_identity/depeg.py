"""Stablecoin depeg period retention on silver identity records."""
from __future__ import annotations

from typing import Any

from backend.nexus_silver_symbol_identity.identity import normalize_asset_code


def make_depeg_period(
    *,
    asset: str,
    peg_asset: str,
    start_time: str,
    end_time: str | None,
    max_deviation_bps: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    period = {
        "asset": normalize_asset_code(asset),
        "peg_asset": normalize_asset_code(peg_asset),
        "start_time": str(start_time),
        "end_time": end_time,
        "max_deviation_bps": max_deviation_bps,
        "note": note,
        "retained": True,
    }
    return period


def attach_depeg_period(record: dict[str, Any], period: dict[str, Any]) -> dict[str, Any]:
    """Attach a depeg interval without dropping prior periods."""
    out = dict(record)
    existing = list(out.get("depeg_periods") or [])
    # Dedup on asset+start+end; never drop history.
    key = (period["asset"], period["start_time"], period.get("end_time"))
    keys = {(p.get("asset"), p.get("start_time"), p.get("end_time")) for p in existing}
    if key not in keys:
        existing.append(dict(period))
    out["depeg_periods"] = existing
    return out


def retained_depeg_periods(record: dict[str, Any], *, asset: str | None = None) -> list[dict[str, Any]]:
    periods = list(record.get("depeg_periods") or [])
    if asset is None:
        return periods
    code = normalize_asset_code(asset)
    return [p for p in periods if normalize_asset_code(str(p.get("asset") or "")) == code]


def assert_depeg_periods_retained(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Normalization / upsert must not drop previously retained depeg intervals."""
    before_keys = {
        (p.get("asset"), p.get("start_time"), p.get("end_time"))
        for p in (before.get("depeg_periods") or [])
    }
    after_keys = {
        (p.get("asset"), p.get("start_time"), p.get("end_time"))
        for p in (after.get("depeg_periods") or [])
    }
    dropped = sorted(before_keys - after_keys)
    return {
        "ok": len(dropped) == 0,
        "status": "DEPEG_PERIODS_DROPPED" if dropped else "PASS",
        "dropped": [
            {"asset": a, "start_time": s, "end_time": e} for a, s, e in dropped
        ],
    }

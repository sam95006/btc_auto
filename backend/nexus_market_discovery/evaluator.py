"""Per-instrument Point-in-Time eligibility evaluation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_market_discovery.constants import DEFAULT_THRESHOLDS, EVALUATION_DIMENSIONS


@dataclass
class InstrumentEvaluation:
    symbol: str
    eligible: bool
    rejection_reasons: list[str] = field(default_factory=list)
    dimension_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    observation_ms: int | None = None
    listing_ms: int | None = None
    delisting_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _dim(ok: bool, *, value: Any = None, detail: str | None = None) -> dict[str, Any]:
    return {"ok": bool(ok), "value": value, "detail": detail}


def evaluate_instrument(
    row: dict[str, Any],
    *,
    as_of_ms: int,
    thresholds: dict[str, Any] | None = None,
) -> InstrumentEvaluation:
    """Evaluate one instrument observation strictly as-of as_of_ms."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    symbol = str(row.get("symbol") or "")
    reasons: list[str] = []
    dims: dict[str, dict[str, Any]] = {}

    obs = row.get("observation_ms")
    obs_i = int(obs) if obs is not None else None
    if obs_i is not None and obs_i > int(as_of_ms):
        reasons.append("FUTURE_OBSERVATION_LEAK")
        dims["staleness"] = _dim(False, value=obs_i, detail="observation_after_as_of")
        # Fail-closed: do not continue scoring with future data
        for d in EVALUATION_DIMENSIONS:
            dims.setdefault(d, _dim(False, detail="aborted_future_leak"))
        return InstrumentEvaluation(
            symbol=symbol,
            eligible=False,
            rejection_reasons=reasons,
            dimension_results=dims,
            observation_ms=obs_i,
            listing_ms=int(row["listing_ms"]) if row.get("listing_ms") is not None else None,
            delisting_ms=int(row["delisting_ms"]) if row.get("delisting_ms") not in (None, 0, "") else None,
        )

    listing = row.get("listing_ms")
    listing_i = int(listing) if listing is not None else None
    delisting = row.get("delisting_ms")
    delisting_i = int(delisting) if delisting not in (None, 0, "") else None

    status = str(row.get("status") or "")
    available = status == "Trading"
    dims["availability"] = _dim(available, value=status)
    if not available:
        reasons.append("NOT_AVAILABLE")

    listed = listing_i is not None and listing_i <= int(as_of_ms)
    dims["listing_timestamp"] = _dim(listed, value=listing_i)
    if listing_i is None or listing_i > int(as_of_ms):
        reasons.append("NOT_YET_LISTED")

    still_listed = delisting_i is None or delisting_i > int(as_of_ms)
    dims["delisting_state"] = _dim(still_listed, value=delisting_i)
    if not still_listed:
        reasons.append("DELISTED")

    liq = float(row.get("liquidity_score") or 0.0)
    dims["liquidity"] = _dim(liq >= float(th["min_liquidity_score"]), value=liq)
    if liq < float(th["min_liquidity_score"]):
        reasons.append("INSUFFICIENT_LIQUIDITY")

    vol = float(row.get("volume_usdt") or 0.0)
    turnover = float(row.get("turnover_usdt") or 0.0)
    vol_ok = vol >= float(th["min_volume_usdt"]) and turnover >= float(th["min_turnover_usdt"])
    dims["volume"] = _dim(vol_ok, value={"volume_usdt": vol, "turnover_usdt": turnover})
    if not vol_ok:
        reasons.append("INSUFFICIENT_VOLUME")

    spread = row.get("spread_bps")
    spread_f = float(spread) if spread is not None else None
    spread_ok = spread_f is not None and spread_f <= float(th["max_spread_bps"])
    dims["spread"] = _dim(spread_ok, value=spread_f)
    if not spread_ok:
        reasons.append("SPREAD_TOO_WIDE")

    depth = float(row.get("depth_usdt") or 0.0)
    dims["depth"] = _dim(depth >= float(th["min_depth_usdt"]), value=depth)
    if depth < float(th["min_depth_usdt"]):
        reasons.append("INSUFFICIENT_DEPTH")

    oi = row.get("open_interest_usdt")
    oi_f = float(oi) if oi is not None else None
    oi_ok = (not th["require_oi"]) or (oi_f is not None and oi_f >= float(th["min_open_interest_usdt"]))
    dims["open_interest"] = _dim(oi_ok, value=oi_f)
    if not oi_ok:
        reasons.append("OPEN_INTEREST_MISSING_OR_LOW")

    funding = bool(row.get("funding_available"))
    funding_ok = (not th["require_funding"]) or funding
    dims["funding_availability"] = _dim(funding_ok, value=funding)
    if not funding_ok:
        reasons.append("FUNDING_UNAVAILABLE")

    completeness = float(row.get("data_completeness") or 0.0)
    dims["data_completeness"] = _dim(completeness >= float(th["min_completeness"]), value=completeness)
    if completeness < float(th["min_completeness"]):
        reasons.append("INCOMPLETE_DATA")

    staleness = int(row.get("staleness_ms") or 0)
    # Also treat observation age vs as_of
    if obs_i is not None:
        age = max(0, int(as_of_ms) - obs_i)
        staleness = max(staleness, age)
    stale_ok = staleness <= int(th["max_staleness_ms"])
    dims["staleness"] = _dim(stale_ok, value=staleness)
    if not stale_ok:
        reasons.append("STALE_OBSERVATION")

    mapping = row.get("symbol_mapping")
    map_ok = bool(mapping)
    dims["symbol_mapping"] = _dim(map_ok, value=mapping)
    if not map_ok:
        reasons.append("MAPPING_MISSING")

    spec = row.get("contract_specification") or {}
    contract_ok = (
        str(row.get("contract_type") or spec.get("contract_type") or "") == "LinearPerpetual"
        and str(row.get("quote_coin") or "") == "USDT"
        and str(row.get("settle_coin") or "") == "USDT"
    )
    dims["contract_specification"] = _dim(contract_ok, value=spec or row.get("contract_type"))
    if not contract_ok:
        reasons.append("INVALID_CONTRACT_SPEC")

    min_notional = row.get("minimum_notional")
    try:
        mn = float(min_notional) if min_notional is not None else None
    except (TypeError, ValueError):
        mn = None
    mn_ok = mn is not None and mn > 0
    dims["minimum_notional"] = _dim(mn_ok, value=mn)
    if not mn_ok:
        reasons.append("INVALID_MIN_NOTIONAL")

    tick = row.get("tick_size")
    try:
        tick_f = float(tick) if tick is not None else None
    except (TypeError, ValueError):
        tick_f = None
    tick_ok = tick_f is not None and tick_f > 0
    dims["tick_size"] = _dim(tick_ok, value=tick_f)
    if not tick_ok:
        reasons.append("INVALID_TICK_SIZE")

    qty = row.get("qty_step")
    try:
        qty_f = float(qty) if qty is not None else None
    except (TypeError, ValueError):
        qty_f = None
    qty_ok = qty_f is not None and qty_f > 0
    dims["quantity_step"] = _dim(qty_ok, value=qty_f)
    if not qty_ok:
        reasons.append("INVALID_QTY_STEP")

    # Deduplicate reasons preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            ordered.append(r)

    return InstrumentEvaluation(
        symbol=symbol,
        eligible=len(ordered) == 0,
        rejection_reasons=ordered,
        dimension_results=dims,
        observation_ms=obs_i,
        listing_ms=listing_i,
        delisting_ms=delisting_i,
    )

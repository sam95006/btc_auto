"""Deterministic microstructure feature extractors (descriptive only)."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from backend.nexus_micro_feature_lab.catalog import FEATURE_CATALOG
from backend.nexus_micro_feature_lab.constants import DEFAULT_WINDOW_MS, FEATURE_IDS
from backend.nexus_micro_feature_lab.pit import observation, select_window_pit


def _sorted_trades(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        events,
        key=lambda e: (
            int(e.get("exchange_timestamp") or 0),
            str(e.get("sequence_or_dedup_key") or ""),
            str(e.get("event_id") or ""),
        ),
    )


def _side(e: dict[str, Any]) -> str:
    return str(e.get("side") or "UNKNOWN").upper()


def _notional(e: dict[str, Any]) -> float:
    if e.get("notional") is not None:
        return float(e["notional"])
    return float(e.get("price") or 0) * float(e.get("quantity") or 0)


def _percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _net_aggressive(events: list[dict[str, Any]]) -> tuple[float, float, float]:
    buy = 0.0
    sell = 0.0
    for e in events:
        s = _side(e)
        n = _notional(e)
        if s == "BUY":
            buy += n
        elif s == "SELL":
            sell += n
    return buy, sell, buy - sell


def _log_returns(prices: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(prices)):
        a, b = prices[i - 1], prices[i]
        if a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    var = sum((x - m) ** 2 for x in vals) / (len(vals) - 1)
    return math.sqrt(var)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    deny = math.sqrt(sum((y - my) ** 2 for y in ys))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def _sub_nets(
    events: list[dict[str, Any]],
    *,
    window_start_ms: int,
    window_end_ms: int,
    sub_window_ms: int,
) -> list[float]:
    buckets: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for e in events:
        ts = int(e["exchange_timestamp"])
        key = ((ts - window_start_ms) // sub_window_ms) * sub_window_ms + window_start_ms
        buckets[key].append(e)
    n_subs = max(1, (window_end_ms - window_start_ms) // sub_window_ms)
    out: list[float] = []
    for i in range(n_subs):
        start = window_start_ms + i * sub_window_ms
        _, _, net = _net_aggressive(buckets.get(start, []))
        out.append(net)
    return out


def extract_aggressive_buy_sell_imbalance(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
) -> dict[str, Any]:
    eligible, not_yet = select_window_pit(
        [t for t in trades if t.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    if not eligible and not_yet:
        return observation(
            feature_id="aggressive_buy_sell_imbalance",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    buy, sell, _ = _net_aggressive(eligible)
    denom = buy + sell
    if denom <= 0:
        return observation(
            feature_id="aggressive_buy_sell_imbalance",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="MISSING" if not eligible else "PARTIAL",
            source_events=eligible,
            extras={"buy_aggressor_notional": buy, "sell_aggressor_notional": sell},
        )
    return observation(
        feature_id="aggressive_buy_sell_imbalance",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=(buy - sell) / denom,
        availability="AVAILABLE",
        source_events=eligible,
        extras={"buy_aggressor_notional": buy, "sell_aggressor_notional": sell},
    )


def extract_trade_intensity(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
) -> dict[str, Any]:
    eligible, not_yet = select_window_pit(
        [t for t in trades if t.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    window_s = max(1e-12, (window_end_ms - window_start_ms) / 1000.0)
    if not eligible and not_yet:
        return observation(
            feature_id="trade_intensity",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    return observation(
        feature_id="trade_intensity",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=len(eligible) / window_s,
        availability="AVAILABLE",
        source_events=eligible,
    )


def extract_trade_size_distribution(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
) -> dict[str, Any]:
    eligible, not_yet = select_window_pit(
        [t for t in trades if t.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    if not eligible and not_yet:
        return observation(
            feature_id="trade_size_distribution",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    if not eligible:
        return observation(
            feature_id="trade_size_distribution",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="MISSING",
            source_events=[],
        )
    notionals = sorted(_notional(e) for e in eligible)
    mean = sum(notionals) / len(notionals)
    value = {
        "count": len(notionals),
        "mean": mean,
        "std": _std(notionals),
        "p50": _percentile(notionals, 50),
        "p90": _percentile(notionals, 90),
        "p99": _percentile(notionals, 99),
    }
    return observation(
        feature_id="trade_size_distribution",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=value,
        availability="AVAILABLE",
        source_events=eligible,
    )


def extract_liquidation_intensity(
    liquidations: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
) -> dict[str, Any]:
    eligible, not_yet = select_window_pit(
        [e for e in liquidations if e.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    window_s = max(1e-12, (window_end_ms - window_start_ms) / 1000.0)
    if not eligible and not_yet:
        return observation(
            feature_id="liquidation_intensity",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    return observation(
        feature_id="liquidation_intensity",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=len(eligible) / window_s,
        availability="AVAILABLE",
        source_events=eligible,
    )


def extract_liquidation_clustering(
    liquidations: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
    cluster_bucket_ms: int = 5_000,
) -> dict[str, Any]:
    eligible, not_yet = select_window_pit(
        [e for e in liquidations if e.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    if not eligible and not_yet:
        return observation(
            feature_id="liquidation_clustering",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    if len(eligible) < 2:
        return observation(
            feature_id="liquidation_clustering",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="MISSING" if not eligible else "PARTIAL",
            source_events=eligible,
        )
    window_ms = max(1, window_end_ms - window_start_ms)
    counts: dict[int, int] = defaultdict(int)
    for e in eligible:
        ts = int(e["exchange_timestamp"])
        key = ((ts - window_start_ms) // cluster_bucket_ms) * cluster_bucket_ms
        counts[key] += 1
    max_bucket = max(counts.values()) if counts else 0
    expected = len(eligible) * (cluster_bucket_ms / window_ms)
    value = (max_bucket / expected) if expected > 0 else None
    return observation(
        feature_id="liquidation_clustering",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=value,
        availability="AVAILABLE" if value is not None else "PARTIAL",
        source_events=eligible,
        extras={"max_bucket_count": max_bucket, "expected_uniform": expected},
    )


def _persistence_pair_stats(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
    sub_window_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float | None, str]:
    eligible, not_yet = select_window_pit(
        [t for t in trades if t.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    if not eligible and not_yet:
        return [], not_yet, None, "NOT_YET_AVAILABLE"
    if len(eligible) < 2:
        return eligible, not_yet, None, ("MISSING" if not eligible else "PARTIAL")
    nets = _sub_nets(
        eligible,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        sub_window_ms=sub_window_ms,
    )
    signs = [0 if n == 0 else (1 if n > 0 else -1) for n in nets]
    comparable = 0
    agree = 0
    for a, b in zip(signs, signs[1:]):
        if a == 0 or b == 0:
            continue
        comparable += 1
        if a == b:
            agree += 1
    if comparable == 0:
        return eligible, not_yet, None, "PARTIAL"
    return eligible, not_yet, agree / comparable, "AVAILABLE"


def extract_flow_persistence(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
    sub_window_ms: int = 10_000,
) -> dict[str, Any]:
    eligible, _not_yet, pers, avail = _persistence_pair_stats(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        sub_window_ms=sub_window_ms,
    )
    return observation(
        feature_id="flow_persistence",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=pers,
        availability=avail,
        source_events=eligible,
    )


def extract_flow_reversal(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
    sub_window_ms: int = 10_000,
) -> dict[str, Any]:
    eligible, _not_yet, pers, avail = _persistence_pair_stats(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        sub_window_ms=sub_window_ms,
    )
    value = (1.0 - pers) if pers is not None else None
    return observation(
        feature_id="flow_reversal",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=value,
        availability=avail,
        source_events=eligible,
    )


def extract_price_impact(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
) -> dict[str, Any]:
    eligible, not_yet = select_window_pit(
        [t for t in trades if t.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    if not eligible and not_yet:
        return observation(
            feature_id="price_impact",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    ordered = _sorted_trades(eligible)
    if len(ordered) < 2:
        return observation(
            feature_id="price_impact",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="MISSING" if not ordered else "PARTIAL",
            source_events=eligible,
        )
    first = float(ordered[0]["price"])
    last = float(ordered[-1]["price"])
    if first == 0:
        return observation(
            feature_id="price_impact",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="PARTIAL",
            source_events=eligible,
        )
    return observation(
        feature_id="price_impact",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=(last - first) / first,
        availability="AVAILABLE",
        source_events=eligible,
        extras={"first_price": first, "last_price": last},
    )


def extract_absorption_proxy(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
) -> dict[str, Any]:
    eligible, not_yet = select_window_pit(
        [t for t in trades if t.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    if not eligible and not_yet:
        return observation(
            feature_id="absorption_proxy",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    ordered = _sorted_trades(eligible)
    if len(ordered) < 2:
        return observation(
            feature_id="absorption_proxy",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="MISSING" if not ordered else "PARTIAL",
            source_events=eligible,
        )
    buy, sell, net = _net_aggressive(ordered)
    first = float(ordered[0]["price"])
    last = float(ordered[-1]["price"])
    if first <= 0:
        return observation(
            feature_id="absorption_proxy",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="PARTIAL",
            source_events=eligible,
        )
    frac = abs((last - first) / first)
    vol = sum(float(e.get("quantity") or 0) for e in ordered)
    mid = 0.5 * (first + last)
    denom = 1e-12 + frac * mid * vol
    return observation(
        feature_id="absorption_proxy",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=abs(net) / denom,
        availability="AVAILABLE",
        source_events=eligible,
        extras={"net_aggressive_notional": net, "buy": buy, "sell": sell},
    )


def extract_vol_adjusted_flow(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
) -> dict[str, Any]:
    eligible, not_yet = select_window_pit(
        [t for t in trades if t.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    if not eligible and not_yet:
        return observation(
            feature_id="vol_adjusted_flow",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    ordered = _sorted_trades(eligible)
    if len(ordered) < 3:
        return observation(
            feature_id="vol_adjusted_flow",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="MISSING" if not ordered else "PARTIAL",
            source_events=eligible,
        )
    prices = [float(e["price"]) for e in ordered]
    rets = _log_returns(prices)
    vol = _std(rets)
    _, _, net = _net_aggressive(ordered)
    if vol <= 0:
        return observation(
            feature_id="vol_adjusted_flow",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="PARTIAL",
            source_events=eligible,
            extras={"realized_vol": vol, "net_aggressive_notional": net},
        )
    return observation(
        feature_id="vol_adjusted_flow",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=net / vol,
        availability="AVAILABLE",
        source_events=eligible,
        extras={"realized_vol": vol, "net_aggressive_notional": net},
    )


def extract_cross_symbol_flow(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
    peer_symbols: list[str] | None = None,
    sub_window_ms: int = 10_000,
) -> dict[str, Any]:
    primary, not_yet = select_window_pit(
        [t for t in trades if t.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    if not primary and not_yet:
        return observation(
            feature_id="cross_symbol_flow",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    if len(primary) < 3:
        return observation(
            feature_id="cross_symbol_flow",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="MISSING" if not primary else "PARTIAL",
            source_events=primary,
        )
    if peer_symbols is None:
        peer_symbols = sorted({str(t["symbol"]) for t in trades if t.get("symbol") != symbol})
    primary_nets = _sub_nets(
        primary,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        sub_window_ms=sub_window_ms,
    )
    corr_map: dict[str, float] = {}
    used: list[dict[str, Any]] = list(primary)
    for peer in peer_symbols:
        peer_el, _ = select_window_pit(
            [t for t in trades if t.get("symbol") == peer],
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
        )
        used.extend(peer_el)
        peer_nets = _sub_nets(
            peer_el,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            sub_window_ms=sub_window_ms,
        )
        c = _pearson(primary_nets, peer_nets)
        if c is not None:
            corr_map[peer] = c
    if not corr_map:
        return observation(
            feature_id="cross_symbol_flow",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="PARTIAL",
            source_events=primary,
        )
    return observation(
        feature_id="cross_symbol_flow",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=corr_map,
        availability="AVAILABLE",
        source_events=used,
    )


def extract_regime_context(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
    intensity_ref: list[float] | None = None,
    vol_ref: list[float] | None = None,
) -> dict[str, Any]:
    eligible, not_yet = select_window_pit(
        [t for t in trades if t.get("symbol") == symbol],
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    if not eligible and not_yet:
        return observation(
            feature_id="regime_context",
            symbol=symbol,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            as_of_ms=as_of_ms,
            value=None,
            availability="NOT_YET_AVAILABLE",
            source_events=[],
        )
    window_s = max(1e-12, (window_end_ms - window_start_ms) / 1000.0)
    intensity = len(eligible) / window_s
    ordered = _sorted_trades(eligible)
    prices = [float(e["price"]) for e in ordered]
    vol = _std(_log_returns(prices)) if len(prices) >= 3 else 0.0
    if not eligible:
        label = "SPARSE"
        avail = "AVAILABLE"
    else:
        iref = sorted(intensity_ref or [intensity])
        vref = sorted(vol_ref or [vol])
        i_hi = iref[int(0.66 * (len(iref) - 1))] if iref else intensity
        v_hi = vref[int(0.66 * (len(vref) - 1))] if vref else vol
        i_lo = iref[int(0.33 * (len(iref) - 1))] if iref else intensity
        if intensity <= i_lo and intensity == 0:
            label = "SPARSE"
        elif intensity >= i_hi and vol >= v_hi:
            label = "HIGH_ACTIVITY_HIGH_VOL"
        elif intensity >= i_hi and vol < v_hi:
            label = "HIGH_ACTIVITY_LOW_VOL"
        elif intensity <= i_lo:
            label = "LOW_ACTIVITY"
        else:
            label = "BALANCED"
        avail = "AVAILABLE"
    return observation(
        feature_id="regime_context",
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        value=label,
        availability=avail,
        source_events=eligible,
        extras={"trade_intensity": intensity, "realized_vol": vol},
    )


EXTRACTORS = {
    "aggressive_buy_sell_imbalance": extract_aggressive_buy_sell_imbalance,
    "trade_intensity": extract_trade_intensity,
    "trade_size_distribution": extract_trade_size_distribution,
    "liquidation_intensity": extract_liquidation_intensity,
    "liquidation_clustering": extract_liquidation_clustering,
    "flow_persistence": extract_flow_persistence,
    "flow_reversal": extract_flow_reversal,
    "price_impact": extract_price_impact,
    "absorption_proxy": extract_absorption_proxy,
    "vol_adjusted_flow": extract_vol_adjusted_flow,
    "cross_symbol_flow": extract_cross_symbol_flow,
    "regime_context": extract_regime_context,
}


def extract_all_features(
    *,
    trades: list[dict[str, Any]],
    liquidations: list[dict[str, Any]],
    symbol: str,
    window_start_ms: int,
    window_end_ms: int,
    as_of_ms: int,
    peer_symbols: list[str] | None = None,
    intensity_ref: list[float] | None = None,
    vol_ref: list[float] | None = None,
) -> dict[str, dict[str, Any]]:
    assert set(EXTRACTORS) == set(FEATURE_IDS) == set(FEATURE_CATALOG)
    out: dict[str, dict[str, Any]] = {}
    out["aggressive_buy_sell_imbalance"] = extract_aggressive_buy_sell_imbalance(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["trade_intensity"] = extract_trade_intensity(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["trade_size_distribution"] = extract_trade_size_distribution(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["liquidation_intensity"] = extract_liquidation_intensity(
        liquidations,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["liquidation_clustering"] = extract_liquidation_clustering(
        liquidations,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["flow_persistence"] = extract_flow_persistence(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["flow_reversal"] = extract_flow_reversal(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["price_impact"] = extract_price_impact(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["absorption_proxy"] = extract_absorption_proxy(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["vol_adjusted_flow"] = extract_vol_adjusted_flow(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
    )
    out["cross_symbol_flow"] = extract_cross_symbol_flow(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        peer_symbols=peer_symbols,
    )
    out["regime_context"] = extract_regime_context(
        trades,
        symbol=symbol,
        window_start_ms=window_start_ms,
        window_end_ms=window_end_ms,
        as_of_ms=as_of_ms,
        intensity_ref=intensity_ref,
        vol_ref=vol_ref,
    )
    return out


def extract_bundle_from_capture(
    capture: dict[str, Any],
    *,
    symbol: str,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    window_start = int(capture["window_start_ms"])
    window_end = int(capture["window_end_ms"])
    if as_of_ms is None:
        # Default: fully received view — max receive among all events.
        all_rx = [
            int(e.get("receive_timestamp") or 0)
            for e in list(capture.get("trades") or []) + list(capture.get("liquidations") or [])
        ]
        as_of_ms = max(all_rx) if all_rx else window_end
    symbols = list(capture.get("symbols") or [symbol])
    peers = [s for s in symbols if s != symbol]
    # Build refs across symbols for regime labeling (sample-relative).
    intensities: list[float] = []
    vols: list[float] = []
    window_s = max(1e-12, (window_end - window_start) / 1000.0)
    for sym in symbols:
        el, _ = select_window_pit(
            [t for t in capture.get("trades") or [] if t.get("symbol") == sym],
            window_start_ms=window_start,
            window_end_ms=window_end,
            as_of_ms=as_of_ms,
        )
        intensities.append(len(el) / window_s)
        ordered = _sorted_trades(el)
        prices = [float(e["price"]) for e in ordered]
        vols.append(_std(_log_returns(prices)) if len(prices) >= 3 else 0.0)
    features = extract_all_features(
        trades=list(capture.get("trades") or []),
        liquidations=list(capture.get("liquidations") or []),
        symbol=symbol,
        window_start_ms=window_start,
        window_end_ms=window_end,
        as_of_ms=as_of_ms,
        peer_symbols=peers,
        intensity_ref=intensities,
        vol_ref=vols,
    )
    return {
        "schema": "v13_e_feature_bundle",
        "symbol": symbol,
        "window_start_ms": window_start,
        "window_end_ms": window_end,
        "window_ms": window_end - window_start if window_end > window_start else DEFAULT_WINDOW_MS,
        "as_of_ms": as_of_ms,
        "fixture_checksum": capture.get("fixture_checksum"),
        "features": features,
        "feature_ids": list(FEATURE_IDS),
        "predictive_edge_claimed": False,
    }

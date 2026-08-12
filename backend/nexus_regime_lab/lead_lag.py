"""Cross-asset lead-lag research without future leakage.

Descriptive correlation of lagged series only. No trading edge claim.
"""
from __future__ import annotations

import math
from typing import Any

from backend.nexus_regime_lab.constants import (
    DEFAULT_BAR_MS,
    DEFAULT_LEAD_LAG_MAX_LAG_BARS,
    DEFAULT_LOOKBACK_BARS,
    REGIME_SCHEMA_VERSION,
)
from backend.nexus_regime_lab.pit import filter_pit_lookback


def _log_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        a, b = closes[i - 1], closes[i]
        if a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


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


def _aligned_returns(
    bars: list[dict[str, Any]],
    symbol: str,
    *,
    as_of_ms: int,
    lookback_start_ms: int,
) -> tuple[list[int], list[float], list[dict[str, Any]], list[dict[str, Any]]]:
    subset = [b for b in bars if b.get("symbol") == symbol]
    eligible, not_yet = filter_pit_lookback(
        subset, as_of_ms=as_of_ms, lookback_start_ms=lookback_start_ms
    )
    # Align by exchange_timestamp floor already implied by bar grid.
    ts = [int(b["exchange_timestamp"]) for b in eligible]
    closes = [float(b["close"]) for b in eligible]
    # Return at bar i uses close[i-1], close[i] — timestamp of return = ts[i]
    rets = _log_returns(closes)
    ret_ts = ts[1:] if len(ts) > 1 else []
    return ret_ts, rets, eligible, not_yet


def lead_lag_pair(
    bars: list[dict[str, Any]],
    *,
    leader: str,
    follower: str,
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
    max_lag_bars: int = DEFAULT_LEAD_LAG_MAX_LAG_BARS,
) -> dict[str, Any]:
    """Compute PIT lead-lag correlations for lag in [-max_lag, +max_lag].

    Positive lag k: corr(leader[t-k], follower[t]) — leader leads.
    Negative lag -k: corr(follower[t-k], leader[t]) — follower leads.
    Only bars with exchange_timestamp <= as_of_ms AND receive_timestamp <= as_of_ms.
    """
    lookback_start = as_of_ms - lookback_bars * bar_ms
    l_ts, l_rets, l_elig, l_ny = _aligned_returns(
        bars, leader, as_of_ms=as_of_ms, lookback_start_ms=lookback_start
    )
    f_ts, f_rets, f_elig, f_ny = _aligned_returns(
        bars, follower, as_of_ms=as_of_ms, lookback_start_ms=lookback_start
    )
    if (not l_elig and l_ny) or (not f_elig and f_ny):
        return {
            "schema": "v14_f_lead_lag_pair",
            "regime_schema_version": REGIME_SCHEMA_VERSION,
            "leader": leader,
            "follower": follower,
            "as_of_ms": as_of_ms,
            "availability": "NOT_YET_AVAILABLE",
            "lags": {},
            "best_lag": None,
            "best_corr": None,
            "predictive_edge_claimed": False,
            "strategy_signal": False,
            "trading_claim": False,
            "non_claim": "Descriptive lead-lag research only; not a trading edge.",
        }

    l_map = {t: r for t, r in zip(l_ts, l_rets)}
    f_map = {t: r for t, r in zip(f_ts, f_rets)}
    common = sorted(set(l_map) & set(f_map))
    # Drop any timestamp > as_of (belt-and-suspenders).
    common = [t for t in common if t <= as_of_ms]

    lags: dict[str, Any] = {}
    best_lag = None
    best_corr: float | None = None
    for k in range(-max_lag_bars, max_lag_bars + 1):
        xs: list[float] = []
        ys: list[float] = []
        if k >= 0:
            # leader leads by k bars
            for t in common:
                t_lead = t - k * bar_ms
                if t_lead not in l_map or t not in f_map:
                    continue
                if t > as_of_ms or t_lead > as_of_ms:
                    continue
                xs.append(l_map[t_lead])
                ys.append(f_map[t])
        else:
            # follower leads by |k| bars
            kk = -k
            for t in common:
                t_fol = t - kk * bar_ms
                if t_fol not in f_map or t not in l_map:
                    continue
                if t > as_of_ms or t_fol > as_of_ms:
                    continue
                xs.append(f_map[t_fol])
                ys.append(l_map[t])
        corr = _pearson(xs, ys)
        lags[str(k)] = {
            "lag_bars": k,
            "n_pairs": len(xs),
            "corr": corr,
        }
        if corr is not None and (best_corr is None or abs(corr) > abs(best_corr)):
            best_corr = corr
            best_lag = k

    availability = "AVAILABLE" if any(v["corr"] is not None for v in lags.values()) else "PARTIAL"
    return {
        "schema": "v14_f_lead_lag_pair",
        "regime_schema_version": REGIME_SCHEMA_VERSION,
        "leader": leader,
        "follower": follower,
        "as_of_ms": as_of_ms,
        "lookback_start_ms": lookback_start,
        "lookback_end_ms": as_of_ms,
        "bar_ms": bar_ms,
        "max_lag_bars": max_lag_bars,
        "availability": availability,
        "lags": lags,
        "best_lag": best_lag,
        "best_corr": best_corr,
        "leader_eligible_bars": len(l_elig),
        "follower_eligible_bars": len(f_elig),
        "common_return_timestamps": len(common),
        "predictive_edge_claimed": False,
        "strategy_signal": False,
        "trading_claim": False,
        "non_claim": "Descriptive lead-lag research only; not a trading edge.",
    }


def lead_lag_matrix(
    bars: list[dict[str, Any]],
    *,
    symbols: list[str],
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
    max_lag_bars: int = DEFAULT_LEAD_LAG_MAX_LAG_BARS,
) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(symbols):
        for b in symbols[i + 1 :]:
            pairs.append(
                lead_lag_pair(
                    bars,
                    leader=a,
                    follower=b,
                    as_of_ms=as_of_ms,
                    bar_ms=bar_ms,
                    lookback_bars=lookback_bars,
                    max_lag_bars=max_lag_bars,
                )
            )
    return {
        "schema": "v14_f_lead_lag_matrix",
        "as_of_ms": as_of_ms,
        "symbols": list(symbols),
        "pair_count": len(pairs),
        "pairs": pairs,
        "predictive_edge_claimed": False,
        "strategy_signal": False,
        "trading_claim": False,
        "non_claim": "Cross-asset lead-lag is descriptive research only.",
    }


def lead_lag_from_capture(
    capture: dict[str, Any],
    *,
    as_of_ms: int | None = None,
    leader: str = "BTCUSDT",
    follower: str = "ETHUSDT",
    max_lag_bars: int = DEFAULT_LEAD_LAG_MAX_LAG_BARS,
) -> dict[str, Any]:
    bars = list(capture.get("bars") or [])
    bar_ms = int(capture.get("bar_ms") or DEFAULT_BAR_MS)
    if as_of_ms is None:
        as_of_ms = int(capture["window_end_ms"])
    return lead_lag_pair(
        bars,
        leader=leader,
        follower=follower,
        as_of_ms=int(as_of_ms),
        bar_ms=bar_ms,
        max_lag_bars=max_lag_bars,
    )

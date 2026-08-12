"""Point-in-Time regime classifiers — descriptive only, no edge claims."""
from __future__ import annotations

import math
from typing import Any

from backend.nexus_regime_lab.catalog import REGIME_CATALOG, require_regime
from backend.nexus_regime_lab.constants import (
    DEFAULT_BAR_MS,
    DEFAULT_LOOKBACK_BARS,
    REGIME_IDS,
)
from backend.nexus_regime_lab.pit import filter_pit_lookback, observation


def _log_returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        a, b = closes[i - 1], closes[i]
        if a > 0 and b > 0:
            out.append(math.log(b / a))
    return out


def _std(vals: list[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / len(vals)
    var = sum((x - m) ** 2 for x in vals) / (len(vals) - 1)
    return math.sqrt(var)


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _tercile_label(value: float, sample: list[float], labels: tuple[str, str, str]) -> str:
    """Classify value using terciles of the contemporaneous sample (includes value)."""
    if not sample:
        return labels[1]
    ordered = sorted(sample)
    n = len(ordered)
    t1 = ordered[max(0, n // 3 - 1)] if n >= 3 else ordered[0]
    t2 = ordered[min(n - 1, (2 * n) // 3)] if n >= 3 else ordered[-1]
    if value <= t1:
        return labels[0]
    if value >= t2:
        return labels[2]
    return labels[1]


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


def _lookback_bounds(
    *,
    as_of_ms: int,
    bar_ms: int,
    lookback_bars: int,
) -> tuple[int, int]:
    lookback_end = as_of_ms
    lookback_start = as_of_ms - lookback_bars * bar_ms
    return lookback_start, lookback_end


def _symbol_bars(
    bars: list[dict[str, Any]],
    symbol: str,
    *,
    as_of_ms: int,
    lookback_start_ms: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    subset = [b for b in bars if b.get("symbol") == symbol]
    return filter_pit_lookback(
        subset, as_of_ms=as_of_ms, lookback_start_ms=lookback_start_ms
    )


def _base_obs(
    regime_id: str,
    symbol: str,
    *,
    lookback_start_ms: int,
    lookback_end_ms: int,
    as_of_ms: int,
    label: Any,
    metrics: dict[str, Any] | None,
    availability: str,
    source_bars: list[dict[str, Any]],
    extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return observation(
        regime_id=regime_id,
        symbol=symbol,
        lookback_start_ms=lookback_start_ms,
        lookback_end_ms=lookback_end_ms,
        as_of_ms=as_of_ms,
        label=label,
        metrics=metrics,
        availability=availability,
        source_bars=source_bars,
        extras=extras,
    )


def classify_volatility_regime(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> dict[str, Any]:
    rid = "volatility_regime"
    meta = require_regime(rid)
    start, end = _lookback_bounds(as_of_ms=as_of_ms, bar_ms=bar_ms, lookback_bars=lookback_bars)
    eligible, not_yet = _symbol_bars(bars, symbol, as_of_ms=as_of_ms, lookback_start_ms=start)
    if not eligible and not_yet:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None, metrics=None, availability="NOT_YET_AVAILABLE", source_bars=[],
        )
    closes = [float(b["close"]) for b in eligible if b.get("close") is not None]
    rets = _log_returns(closes)
    if len(rets) < meta["min_bars"] - 1:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None,
            metrics={"realized_vol": None, "n_returns": len(rets)},
            availability="MISSING" if not eligible else "PARTIAL",
            source_bars=eligible,
        )
    vol = _std(rets)
    # Sample terciles from rolling single-bar absolute returns as contemporaneous distribution.
    sample = [abs(r) for r in rets] or [vol]
    label = _tercile_label(vol, sample, ("LOW", "MEDIUM", "HIGH"))
    return _base_obs(
        rid, symbol,
        lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
        label=label,
        metrics={"realized_vol": vol, "n_returns": len(rets)},
        availability="AVAILABLE",
        source_bars=eligible,
    )


def classify_liquidity_regime(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> dict[str, Any]:
    rid = "liquidity_regime"
    meta = require_regime(rid)
    start, end = _lookback_bounds(as_of_ms=as_of_ms, bar_ms=bar_ms, lookback_bars=lookback_bars)
    eligible, not_yet = _symbol_bars(bars, symbol, as_of_ms=as_of_ms, lookback_start_ms=start)
    if not eligible and not_yet:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None, metrics=None, availability="NOT_YET_AVAILABLE", source_bars=[],
        )
    vols = [float(b["volume_notional"]) for b in eligible if b.get("volume_notional") is not None]
    if len(vols) < meta["min_bars"]:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None,
            metrics={"avg_volume_notional": None, "n_bars": len(vols)},
            availability="MISSING" if not eligible else "PARTIAL",
            source_bars=eligible,
        )
    avg = _mean(vols)
    label = _tercile_label(avg, vols, ("THIN", "NORMAL", "DEEP"))
    return _base_obs(
        rid, symbol,
        lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
        label=label,
        metrics={"avg_volume_notional": avg, "n_bars": len(vols)},
        availability="AVAILABLE",
        source_bars=eligible,
    )


def classify_trend_regime(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> dict[str, Any]:
    rid = "trend_regime"
    meta = require_regime(rid)
    start, end = _lookback_bounds(as_of_ms=as_of_ms, bar_ms=bar_ms, lookback_bars=lookback_bars)
    eligible, not_yet = _symbol_bars(bars, symbol, as_of_ms=as_of_ms, lookback_start_ms=start)
    if not eligible and not_yet:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None, metrics=None, availability="NOT_YET_AVAILABLE", source_bars=[],
        )
    closes = [float(b["close"]) for b in eligible if b.get("close") is not None]
    if len(closes) < meta["min_bars"] or closes[0] == 0:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None,
            metrics={"drift": None},
            availability="MISSING" if not eligible else "PARTIAL",
            source_bars=eligible,
        )
    drift = (closes[-1] - closes[0]) / closes[0]
    if drift > 0.001:
        label = "UP"
    elif drift < -0.001:
        label = "DOWN"
    else:
        label = "FLAT"
    return _base_obs(
        rid, symbol,
        lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
        label=label,
        metrics={"drift": drift, "n_bars": len(closes)},
        availability="AVAILABLE",
        source_bars=eligible,
    )


def classify_funding_regime(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> dict[str, Any]:
    rid = "funding_regime"
    meta = require_regime(rid)
    start, end = _lookback_bounds(as_of_ms=as_of_ms, bar_ms=bar_ms, lookback_bars=lookback_bars)
    eligible, not_yet = _symbol_bars(bars, symbol, as_of_ms=as_of_ms, lookback_start_ms=start)
    if not eligible and not_yet:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None, metrics=None, availability="NOT_YET_AVAILABLE", source_bars=[],
        )
    rates = [float(b["funding_rate"]) for b in eligible if b.get("funding_rate") is not None]
    if len(rates) < meta["min_bars"]:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None,
            metrics={"mean_funding": None},
            availability="MISSING" if not eligible else "PARTIAL",
            source_bars=eligible,
        )
    mean_f = _mean(rates)
    if mean_f > 1e-5:
        label = "POSITIVE"
    elif mean_f < -1e-5:
        label = "NEGATIVE"
    else:
        label = "NEUTRAL"
    return _base_obs(
        rid, symbol,
        lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
        label=label,
        metrics={"mean_funding": mean_f, "n_bars": len(rates)},
        availability="AVAILABLE",
        source_bars=eligible,
    )


def classify_open_interest_regime(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> dict[str, Any]:
    rid = "open_interest_regime"
    meta = require_regime(rid)
    start, end = _lookback_bounds(as_of_ms=as_of_ms, bar_ms=bar_ms, lookback_bars=lookback_bars)
    eligible, not_yet = _symbol_bars(bars, symbol, as_of_ms=as_of_ms, lookback_start_ms=start)
    if not eligible and not_yet:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None, metrics=None, availability="NOT_YET_AVAILABLE", source_bars=[],
        )
    ois = [float(b["open_interest"]) for b in eligible if b.get("open_interest") is not None]
    if len(ois) < meta["min_bars"] or ois[0] == 0:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None,
            metrics={"oi_change": None},
            availability="MISSING" if not eligible else "PARTIAL",
            source_bars=eligible,
        )
    change = (ois[-1] - ois[0]) / ois[0]
    if change > 0.01:
        label = "EXPANDING"
    elif change < -0.01:
        label = "CONTRACTING"
    else:
        label = "STABLE"
    return _base_obs(
        rid, symbol,
        lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
        label=label,
        metrics={"oi_change": change, "n_bars": len(ois)},
        availability="AVAILABLE",
        source_bars=eligible,
    )


def classify_liquidation_regime(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> dict[str, Any]:
    rid = "liquidation_regime"
    meta = require_regime(rid)
    start, end = _lookback_bounds(as_of_ms=as_of_ms, bar_ms=bar_ms, lookback_bars=lookback_bars)
    eligible, not_yet = _symbol_bars(bars, symbol, as_of_ms=as_of_ms, lookback_start_ms=start)
    if not eligible and not_yet:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None, metrics=None, availability="NOT_YET_AVAILABLE", source_bars=[],
        )
    liqs = [
        float(b["liquidation_notional"])
        for b in eligible
        if b.get("liquidation_notional") is not None
    ]
    if len(liqs) < meta["min_bars"]:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None,
            metrics={"mean_liquidation_notional": None},
            availability="MISSING" if not eligible else "PARTIAL",
            source_bars=eligible,
        )
    mean_l = _mean(liqs)
    label = _tercile_label(mean_l, liqs, ("QUIET", "ELEVATED", "STRESSED"))
    return _base_obs(
        rid, symbol,
        lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
        label=label,
        metrics={"mean_liquidation_notional": mean_l, "n_bars": len(liqs)},
        availability="AVAILABLE",
        source_bars=eligible,
    )


def classify_correlation_regime(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    as_of_ms: int,
    universe: list[str] | None = None,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> dict[str, Any]:
    rid = "correlation_regime"
    meta = require_regime(rid)
    start, end = _lookback_bounds(as_of_ms=as_of_ms, bar_ms=bar_ms, lookback_bars=lookback_bars)
    if universe is None:
        universe = sorted({str(b["symbol"]) for b in bars if b.get("symbol")})
    series: dict[str, list[float]] = {}
    any_not_yet = False
    for sym in universe:
        eligible, not_yet = _symbol_bars(bars, sym, as_of_ms=as_of_ms, lookback_start_ms=start)
        if not eligible and not_yet:
            any_not_yet = True
            continue
        closes = [float(b["close"]) for b in eligible if b.get("close") is not None]
        rets = _log_returns(closes)
        if len(rets) >= meta["min_bars"] - 1:
            series[sym] = rets
    if not series and any_not_yet:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None, metrics=None, availability="NOT_YET_AVAILABLE", source_bars=[],
        )
    syms = sorted(series)
    pairs: list[float] = []
    for i in range(len(syms)):
        for j in range(i + 1, len(syms)):
            a, b = series[syms[i]], series[syms[j]]
            n = min(len(a), len(b))
            if n < 3:
                continue
            corr = _pearson(a[-n:], b[-n:])
            if corr is not None:
                pairs.append(corr)
    if len(pairs) < 1:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None,
            metrics={"mean_pairwise_corr": None, "pair_count": 0},
            availability="PARTIAL" if series else "MISSING",
            source_bars=[],
            extras={"universe_used": syms},
        )
    mean_c = _mean(pairs)
    if mean_c < 0.2:
        label = "DECOUPLED"
    elif mean_c > 0.6:
        label = "COUPLED"
    else:
        label = "MIXED"
    return _base_obs(
        rid, symbol,
        lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
        label=label,
        metrics={"mean_pairwise_corr": mean_c, "pair_count": len(pairs)},
        availability="AVAILABLE",
        source_bars=[],
        extras={"universe_used": syms},
    )


def classify_market_stress_regime(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> dict[str, Any]:
    rid = "market_stress_regime"
    meta = require_regime(rid)
    start, end = _lookback_bounds(as_of_ms=as_of_ms, bar_ms=bar_ms, lookback_bars=lookback_bars)
    eligible, not_yet = _symbol_bars(bars, symbol, as_of_ms=as_of_ms, lookback_start_ms=start)
    if not eligible and not_yet:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None, metrics=None, availability="NOT_YET_AVAILABLE", source_bars=[],
        )
    if len(eligible) < meta["min_bars"]:
        return _base_obs(
            rid, symbol,
            lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
            label=None,
            metrics={"stress_score": None},
            availability="MISSING" if not eligible else "PARTIAL",
            source_bars=eligible,
        )
    closes = [float(b["close"]) for b in eligible if b.get("close") is not None]
    rets = _log_returns(closes)
    vol = _std(rets)
    liqs = [float(b.get("liquidation_notional") or 0.0) for b in eligible]
    funds = [abs(float(b.get("funding_rate") or 0.0)) for b in eligible]
    mean_liq = _mean(liqs)
    mean_abs_f = _mean(funds)
    # z vs contemporaneous sample std (self-relative; descriptive composite).
    def _z(x: float, sample: list[float]) -> float:
        s = _std(sample)
        if s <= 0:
            return 0.0
        return (x - _mean(sample)) / s

    z_vol = _z(vol, [abs(r) for r in rets] or [vol])
    z_liq = _z(mean_liq, liqs)
    z_fund = _z(mean_abs_f, funds)
    score = (z_vol + z_liq + z_fund) / 3.0
    # Score terciles across single-bar stress proxies in lookback.
    bar_scores: list[float] = []
    for i, b in enumerate(eligible):
        abs_ret = abs(rets[i - 1]) if i > 0 and i - 1 < len(rets) else 0.0
        bar_scores.append(
            (abs_ret + float(b.get("liquidation_notional") or 0.0) / 1e5
             + abs(float(b.get("funding_rate") or 0.0)) * 1e5) / 3.0
        )
    label = _tercile_label(score, bar_scores or [score], ("CALM", "WATCH", "STRESS"))
    return _base_obs(
        rid, symbol,
        lookback_start_ms=start, lookback_end_ms=end, as_of_ms=as_of_ms,
        label=label,
        metrics={
            "stress_score": score,
            "z_vol": z_vol,
            "z_liq": z_liq,
            "z_funding_abs": z_fund,
        },
        availability="AVAILABLE",
        source_bars=eligible,
    )


CLASSIFIERS = {
    "volatility_regime": classify_volatility_regime,
    "liquidity_regime": classify_liquidity_regime,
    "trend_regime": classify_trend_regime,
    "funding_regime": classify_funding_regime,
    "open_interest_regime": classify_open_interest_regime,
    "liquidation_regime": classify_liquidation_regime,
    "correlation_regime": classify_correlation_regime,
    "market_stress_regime": classify_market_stress_regime,
}


def classify_all_regimes(
    bars: list[dict[str, Any]],
    *,
    symbol: str,
    as_of_ms: int,
    bar_ms: int = DEFAULT_BAR_MS,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
    universe: list[str] | None = None,
) -> dict[str, Any]:
    assert set(CLASSIFIERS) == set(REGIME_IDS)
    assert set(REGIME_CATALOG) == set(REGIME_IDS)
    out: dict[str, Any] = {}
    for rid in REGIME_IDS:
        fn = CLASSIFIERS[rid]
        if rid == "correlation_regime":
            out[rid] = fn(
                bars,
                symbol=symbol,
                as_of_ms=as_of_ms,
                bar_ms=bar_ms,
                lookback_bars=lookback_bars,
                universe=universe,
            )
        else:
            out[rid] = fn(
                bars,
                symbol=symbol,
                as_of_ms=as_of_ms,
                bar_ms=bar_ms,
                lookback_bars=lookback_bars,
            )
    return out


def classify_bundle_from_capture(
    capture: dict[str, Any],
    *,
    symbol: str,
    as_of_ms: int | None = None,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> dict[str, Any]:
    bars = list(capture.get("bars") or [])
    bar_ms = int(capture.get("bar_ms") or DEFAULT_BAR_MS)
    if as_of_ms is None:
        # Default as_of: end of window but before late-receive lag on last primary bar.
        as_of_ms = int(capture["window_end_ms"])
    universe = list(capture.get("symbols") or sorted({str(b["symbol"]) for b in bars}))
    regimes = classify_all_regimes(
        bars,
        symbol=symbol,
        as_of_ms=int(as_of_ms),
        bar_ms=bar_ms,
        lookback_bars=lookback_bars,
        universe=universe,
    )
    return {
        "schema": "v14_f_regime_bundle",
        "symbol": symbol,
        "as_of_ms": int(as_of_ms),
        "bar_ms": bar_ms,
        "lookback_bars": lookback_bars,
        "fixture_checksum": capture.get("fixture_checksum"),
        "regimes": regimes,
        "regime_ids": list(REGIME_IDS),
        "predictive_edge_claimed": False,
        "strategy_signal": False,
        "contemporaneous_only": True,
    }

"""Stage 4 read-only market context builder (Bybit demo public data)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.research.bybit_demo_client import BybitDemoClient
from tools.research.stage4_fleet_summary import resolve_stage4_read_only_symbols

KLINE_INTERVAL = "15"
KLINE_COUNT = 20


def _f(raw: Any, default: float = 0.0) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _pct_change(last: float, prev: float) -> float:
    if not prev:
        return 0.0
    return round((last - prev) / prev * 100.0, 4)


def _trend_from_closes(closes: List[float]) -> str:
    if len(closes) < 2:
        return "unknown"
    first = closes[0]
    last = closes[-1]
    if not first:
        return "unknown"
    ch = (last - first) / first * 100.0
    if ch > 0.05:
        return "up"
    if ch < -0.05:
        return "down"
    return "flat"


def _volatility_pct(closes: List[float]) -> float:
    if len(closes) < 2:
        return 0.0
    returns = []
    for i in range(1, len(closes)):
        if closes[i - 1]:
            returns.append(abs((closes[i] - closes[i - 1]) / closes[i - 1]) * 100.0)
    if not returns:
        return 0.0
    return round(sum(returns) / len(returns), 4)


def _range_pct(high: float, low: float, mid: float) -> float:
    if not mid or high <= low:
        return 0.0
    return round((high - low) / mid * 100.0, 4)


def _close_slope_pct(closes: List[float]) -> float:
    if len(closes) < 2 or not closes[0]:
        return 0.0
    return round((closes[-1] - closes[0]) / closes[0] * 100.0, 4)


def _direction_consistency(closes: List[float]) -> float:
    if len(closes) < 3:
        return 0.0
    overall_up = closes[-1] >= closes[0]
    same = 0
    total = 0
    for i in range(1, len(closes)):
        if closes[i - 1]:
            bar_up = closes[i] >= closes[i - 1]
            if bar_up == overall_up:
                same += 1
            total += 1
    return round(same / total, 4) if total else 0.0


def classify_regime_from_klines(
    closes: List[float],
    highs: List[float],
    lows: List[float],
    *,
    change_24h_pct: float = 0.0,
) -> Dict[str, Any]:
    """Rule-based regime from 15m klines; never raises."""
    kline_count = len(closes)
    if kline_count < 3:
        return {
            "regime": "unknown",
            "regime_reason": "insufficient_klines",
            "trend_strength": 0.0,
            "range_strength": 0.0,
            "volatility_level": "unknown",
            "kline_data_quality": "error" if kline_count == 0 else "partial",
        }

    slope = _close_slope_pct(closes)
    vol = _volatility_pct(closes)
    hi = max(highs) if highs else max(closes)
    lo = min(lows) if lows else min(closes)
    mid = closes[-1] or 1.0
    range_pct = _range_pct(hi, lo, mid)
    consistency = _direction_consistency(closes)
    abs_slope = abs(slope)

    trend_strength = round(min(1.0, (abs_slope / 0.8) * max(consistency, 0.3)), 4) if abs_slope > 0.03 else 0.0
    range_strength = round(
        min(1.0, max(0.0, (1.0 - abs_slope / 0.6)) * (0.7 if range_pct >= 0.25 else 0.3)),
        4,
    )

    if vol >= 0.25 or range_pct >= 2.0:
        vol_level = "high"
    elif vol >= 0.08:
        vol_level = "medium"
    else:
        vol_level = "low"

    regime = "unknown"
    reason = ""

    if vol >= 0.30 or range_pct >= 2.5:
        regime = "volatile"
        reason = f"high_volatility_15m={vol:.4f},range_pct={range_pct:.4f}"
    elif abs_slope >= 0.10 and consistency >= 0.50 and range_pct < 2.5:
        regime = "trend"
        reason = f"slope={slope:.4f},consistency={consistency:.2f}"
    elif abs_slope < 0.10 and 0.25 <= range_pct <= 2.5 and vol < 0.25:
        regime = "range"
        reason = f"low_slope={slope:.4f},range_pct={range_pct:.4f}"
    elif abs(change_24h_pct) >= 0.12 and abs_slope >= 0.06:
        regime = "trend"
        reason = f"24h_change={change_24h_pct:.4f},slope={slope:.4f}"
    elif range_pct >= 0.20 and abs_slope < 0.12:
        regime = "range"
        reason = f"contained_range,slope={slope:.4f}"
    else:
        reason = f"mixed_signal,slope={slope:.4f},vol={vol:.4f}"

    kline_dq = "ok" if kline_count >= 10 else "partial"
    return {
        "regime": regime,
        "regime_reason": reason,
        "trend_strength": trend_strength,
        "range_strength": range_strength,
        "volatility_level": vol_level,
        "kline_data_quality": kline_dq,
    }


def _empty_context(symbol: str, *, limitations: List[str]) -> Dict[str, Any]:
    sym = symbol.upper()
    return {
        "symbol": sym,
        "last_price": 0.0,
        "prev_price_24h": 0.0,
        "change_24h_pct": 0.0,
        "high_24h": 0.0,
        "low_24h": 0.0,
        "volume_24h": 0.0,
        "turnover_24h": 0.0,
        "spread_bps": None,
        "kline_interval": "15m",
        "kline_count": 0,
        "trend_15m": "unknown",
        "volatility_15m": 0.0,
        "range_15m_pct": 0.0,
        "regime": "unknown",
        "regime_reason": "no_data",
        "trend_strength": 0.0,
        "range_strength": 0.0,
        "volatility_level": "unknown",
        "kline_data_quality": "error",
        "data_quality": "error" if limitations else "partial",
        "data_limitations": limitations,
        "source": "unavailable",
        "balance_read_ok": True,
    }


def build_market_context(
    symbol: str,
    *,
    client: Optional[BybitDemoClient] = None,
) -> Dict[str, Any]:
    """Build enriched read-only market context; never raises."""
    sym = symbol.upper()
    limitations: List[str] = []
    if sym not in resolve_stage4_read_only_symbols():
        return _empty_context(sym, limitations=[f"symbol_not_in_read_allowlist:{sym}"])

    cli = client or BybitDemoClient("dry-run", allow_demo_order=False)
    ctx = _empty_context(sym, limitations=[])

    try:
        ticker = cli.fetch_ticker(sym)
        last = _f(ticker.get("lastPrice") or ticker.get("last_price"))
        prev = _f(ticker.get("prevPrice24h") or ticker.get("prev_price_24h"))
        high24 = _f(ticker.get("highPrice24h") or ticker.get("high_24h") or last)
        low24 = _f(ticker.get("lowPrice24h") or ticker.get("low_24h") or last)
        vol24 = _f(ticker.get("volume24h") or ticker.get("volume_24h"))
        turn24 = _f(ticker.get("turnover24h") or ticker.get("turnover_24h"))
        bid = _f(ticker.get("bid1Price"))
        ask = _f(ticker.get("ask1Price"))
        spread_bps: Optional[float] = None
        if bid > 0 and ask > 0 and last > 0:
            spread_bps = round((ask - bid) / last * 10000.0, 2)

        ctx.update(
            {
                "last_price": last,
                "prev_price_24h": prev,
                "change_24h_pct": _pct_change(last, prev),
                "high_24h": high24,
                "low_24h": low24,
                "volume_24h": vol24,
                "turnover_24h": turn24,
                "spread_bps": spread_bps,
                "source": str(ticker.get("source") or "bybit_demo_public_ticker"),
            }
        )
    except Exception as exc:
        limitations.append(f"ticker_error:{str(exc)[:80]}")

    closes: List[float] = []
    highs: List[float] = []
    lows: List[float] = []
    try:
        klines = cli.fetch_klines(sym, interval=KLINE_INTERVAL, limit=KLINE_COUNT)
        for row in klines:
            closes.append(_f(row.get("close")))
            highs.append(_f(row.get("high")))
            lows.append(_f(row.get("low")))
        ctx["kline_count"] = len(closes)
        if closes:
            ctx["trend_15m"] = _trend_from_closes(closes)
            ctx["volatility_15m"] = _volatility_pct(closes)
            hi = max(highs) if highs else max(closes)
            lo = min(lows) if lows else min(closes)
            mid = closes[-1]
            ctx["range_15m_pct"] = _range_pct(hi, lo, mid or 1.0)
            regime_info = classify_regime_from_klines(
                closes,
                highs,
                lows,
                change_24h_pct=float(ctx.get("change_24h_pct") or 0),
            )
            ctx.update(regime_info)
        else:
            limitations.append("kline_empty")
            ctx["kline_data_quality"] = "error"
            ctx["regime_reason"] = "kline_empty"
    except Exception as exc:
        limitations.append(f"kline_error:{str(exc)[:80]}")
        ctx["kline_count"] = 0
        ctx["kline_data_quality"] = "error"
        ctx["regime_reason"] = f"kline_error:{str(exc)[:40]}"

    ctx["data_limitations"] = limitations
    if limitations and ctx.get("last_price"):
        ctx["data_quality"] = "partial"
    elif limitations:
        ctx["data_quality"] = "error"
    else:
        ctx["data_quality"] = "ok"
    ctx["balance_read_ok"] = True
    return ctx

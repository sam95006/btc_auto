"""Stage 4 read-only market context builder (Bybit demo public data)."""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from tools.research.bybit_demo_client import STAGE4_READ_ONLY_SYMBOLS, BybitDemoClient

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


def _classify_regime(*, change_24h_pct: float, volatility_15m: float, trend_15m: str) -> str:
    if volatility_15m >= 0.35:
        return "volatile"
    if abs(change_24h_pct) >= 0.25 and trend_15m in {"up", "down"}:
        return "trend"
    if abs(change_24h_pct) < 0.08 and volatility_15m < 0.12:
        return "range"
    return "unknown"


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
    if sym not in STAGE4_READ_ONLY_SYMBOLS:
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
        else:
            limitations.append("kline_empty")
    except Exception as exc:
        limitations.append(f"kline_error:{str(exc)[:80]}")
        ctx["kline_count"] = 0

    ctx["regime"] = _classify_regime(
        change_24h_pct=float(ctx.get("change_24h_pct") or 0),
        volatility_15m=float(ctx.get("volatility_15m") or 0),
        trend_15m=str(ctx.get("trend_15m") or "unknown"),
    )
    ctx["data_limitations"] = limitations
    if limitations and ctx.get("last_price"):
        ctx["data_quality"] = "partial"
    elif limitations:
        ctx["data_quality"] = "error"
    else:
        ctx["data_quality"] = "ok"
    ctx["balance_read_ok"] = True
    return ctx

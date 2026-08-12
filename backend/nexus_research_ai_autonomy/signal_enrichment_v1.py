"""Live market enrichment for Signal Quality V1 — public read-only data only."""
from __future__ import annotations

import math
import statistics
import time
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, _float


def _klines(client: DemoWriteClient, symbol: str, interval: str, limit: int = 30) -> list[float]:
    try:
        raw = client.public_get(
            "/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": interval, "limit": str(limit)},
        )
        rows = (raw.get("result") or {}).get("list") or []
        closes: list[float] = []
        for r in rows:
            if isinstance(r, (list, tuple)) and len(r) >= 5:
                closes.append(float(r[4]))
            elif isinstance(r, dict):
                closes.append(_float(r.get("close") or r.get("c")))
        return [c for c in closes if c > 0]
    except Exception:  # noqa: BLE001
        return []


def _momentum_features(closes: list[float]) -> dict[str, Any]:
    if len(closes) < 3:
        return {"return": None, "velocity": None, "acceleration": None, "volume_confirmed": None}
    # klines returned newest-first from Bybit
    c0, c1 = closes[0], closes[-1]
    ret = (c0 - c1) / c1 * 100.0 if c1 else None
    mid = closes[len(closes) // 2] if len(closes) >= 4 else c1
    vel = (c0 - mid) / mid * 100.0 if mid else None
    acc = (vel - ((mid - c1) / c1 * 100.0 if c1 else 0.0)) if vel is not None and c1 else None
    return {
        "return": round(ret, 6) if ret is not None else None,
        "velocity": round(vel, 6) if vel is not None else None,
        "acceleration": round(acc, 6) if acc is not None else None,
        "volume_confirmed": None,
    }


def _spread_bps(bid: float, ask: float, mid: float) -> float | None:
    if bid <= 0 or ask <= 0 or mid <= 0:
        return None
    return (ask - bid) / mid * 10_000.0


def _activity_from_turnover(turnover24h: float) -> tuple[float, str]:
    if turnover24h <= 0:
        return 0.2, "ACTIVITY_FALLBACK"
    import math

    score = min(1.0, max(0.2, math.log10(turnover24h) / 8.0))
    return round(score, 4), "TURNOVER_LOG"


def enrich_symbol(
    client: DemoWriteClient,
    *,
    symbol: str,
    ticker_row: dict[str, Any] | None = None,
    now_ms: int | None = None,
) -> dict[str, Any]:
    """Point-in-time enrichment — no future data."""
    now_ms = now_ms or int(time.time() * 1000)
    t = dict(ticker_row or {})
    price = _float(t.get("last_price") or t.get("lastPrice") or 0)
    turnover = _float(t.get("turnover_24h") or t.get("turnover24h") or 0)
    volume = _float(t.get("volume_24h") or t.get("volume24h") or 0)
    change_24h = _float(t.get("change_pct_24h") or t.get("price24hPcnt") or 0)
    if abs(change_24h) < 5 and t.get("price24hPcnt") is not None:
        change_24h = _float(t.get("price24hPcnt")) * 100.0

    bid = _float(t.get("bid1Price") or t.get("bidPrice") or 0)
    ask = _float(t.get("ask1Price") or t.get("askPrice") or 0)
    if (not bid or not ask) and symbol:
        try:
            raw = client.public_get("/v5/market/tickers", {"category": "linear", "symbol": symbol})
            rows = (raw.get("result") or {}).get("list") or []
            if rows:
                r0 = rows[0]
                price = price or _float(r0.get("lastPrice"))
                bid = _float(r0.get("bid1Price"))
                ask = _float(r0.get("ask1Price"))
                turnover = turnover or _float(r0.get("turnover24h"))
                volume = volume or _float(r0.get("volume24h"))
                change_24h = change_24h or _float(r0.get("price24hPcnt")) * 100.0
        except Exception:  # noqa: BLE001
            pass

    mid = price or ((bid + ask) / 2.0 if bid and ask else 0)
    spread_bps = _spread_bps(bid, ask, mid)

    act_score, act_source = _activity_from_turnover(turnover)
    act_freshness_ms = 0

    m1 = _momentum_features(_klines(client, symbol, "1", 20))
    m5 = _momentum_features(_klines(client, symbol, "5", 20))
    m15 = _momentum_features(_klines(client, symbol, "15", 20))

    vol_closes = _klines(client, symbol, "5", 48)
    volatility = None
    if len(vol_closes) >= 6:
        rets = [
            math.log(vol_closes[i] / vol_closes[i + 1])
            for i in range(len(vol_closes) - 1)
            if vol_closes[i + 1] > 0
        ]
        if len(rets) >= 4:
            volatility = round(abs(statistics.pstdev(rets)) * math.sqrt(12) * 100.0, 4)

    oi = oi_short = oi_medium = None
    try:
        oi_raw = client.public_get(
            "/v5/market/open-interest",
            {"category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": "12"},
        )
        oi_rows = (oi_raw.get("result") or {}).get("list") or []
        if oi_rows:
            oi_vals = [_float(r.get("openInterest")) for r in oi_rows]
            oi_vals = [v for v in oi_vals if v > 0]
            if oi_vals:
                oi = oi_vals[0]
                if len(oi_vals) >= 2:
                    oi_short = (oi_vals[0] - oi_vals[1]) / oi_vals[1] if oi_vals[1] else None
                if len(oi_vals) >= 4:
                    oi_medium = (oi_vals[0] - oi_vals[3]) / oi_vals[3] if oi_vals[3] else None
    except Exception:  # noqa: BLE001
        pass

    funding_rate = funding_delta = None
    try:
        fr = client.public_get(
            "/v5/market/tickers",
            {"category": "linear", "symbol": symbol},
        )
        rows = (fr.get("result") or {}).get("list") or []
        if rows:
            funding_rate = _float(rows[0].get("fundingRate"))
    except Exception:  # noqa: BLE001
        pass

    return {
        "symbol": symbol,
        "timestamp_ms": now_ms,
        "price": price,
        "turnover": turnover,
        "volume": volume,
        "change_pct_24h": change_24h,
        "spread_bps": round(spread_bps, 4) if spread_bps is not None else None,
        "depth_near_mid": None,
        "estimated_slippage": round((spread_bps or 0) / 10_000.0 * mid, 6) if mid else None,
        "activity_score": act_score,
        "activity_source": act_source,
        "activity_freshness_ms": act_freshness_ms,
        "activity_fallback": act_source == "ACTIVITY_FALLBACK",
        "momentum_1m": m1,
        "momentum_5m": m5,
        "momentum_15m": m15,
        "volatility": volatility,
        "open_interest": oi,
        "oi_delta_short": round(oi_short, 6) if oi_short is not None else None,
        "oi_delta_medium": round(oi_medium, 6) if oi_medium is not None else None,
        "funding_rate": funding_rate,
        "funding_delta": funding_delta,
        "cvd": None,
        "cvd_source": "source_unavailable",
        "liquidation_long_intensity": None,
        "liquidation_short_intensity": None,
        "liquidation_imbalance": None,
        "liquidations_source": "source_unavailable",
        "data_freshness_ms": int(time.time() * 1000) - now_ms,
    }

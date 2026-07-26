"""Enrich instruments with public ticker / orderbook quality (Demo host only)."""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.request import Request, urlopen

from backend.nexus_research.demo_autonomous.universe import MarketQualitySnapshot
from backend.nexus_research.demo_exchange.constants import DEMO_REST_BASE_URL, HTTP_TIMEOUT_SEC

logger = logging.getLogger(__name__)


def _get_json(url: str, timeout_sec: float) -> dict[str, Any]:
    if "api-demo.bybit.com" not in url:
        raise ValueError(f"quality_host_not_demo:{url}")
    req = Request(url, method="GET")
    with urlopen(req, timeout=timeout_sec) as resp:
        raw = resp.read().decode("utf-8", "replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("quality_non_object")
    return data


def fetch_ticker_quality(
    *,
    base_url: str = DEMO_REST_BASE_URL,
    timeout_sec: float = HTTP_TIMEOUT_SEC,
) -> dict[str, MarketQualitySnapshot]:
    """Build MarketQualitySnapshot map from /v5/market/tickers?category=linear."""
    url = f"{base_url.rstrip('/')}/v5/market/tickers?category=linear"
    data = _get_json(url, timeout_sec)
    if int(data.get("retCode", -1)) != 0:
        raise RuntimeError(f"tickers_failed:{data.get('retMsg')}")
    rows = (data.get("result") or {}).get("list") or []
    out: dict[str, MarketQualitySnapshot] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "")
        if not symbol.endswith("USDT"):
            continue
        turnover = float(row.get("turnover24h") or 0)
        volume = float(row.get("volume24h") or 0)
        last = float(row.get("lastPrice") or 0)
        bid = float(row.get("bid1Price") or 0)
        ask = float(row.get("ask1Price") or 0)
        if last > 0 and bid > 0 and ask > 0 and ask >= bid:
            spread_bps = (ask - bid) / last * 10_000.0
        else:
            spread_bps = 999.0
        # High/low range as crude ATR proxy
        high = float(row.get("highPrice24h") or 0)
        low = float(row.get("lowPrice24h") or 0)
        atr_pct = ((high - low) / last * 100.0) if last > 0 and high > low else 0.0
        oi = float(row.get("openInterest") or row.get("openInterestValue") or 0)
        funding = float(row.get("fundingRate") or 0)
        funding_abnormal = abs(funding) > 0.005
        out[symbol] = MarketQualitySnapshot(
            symbol=symbol,
            turnover_24h=turnover,
            spread_bps=spread_bps,
            volume_24h=volume * last if last > 0 else volume,
            open_interest=oi,
            atr_pct=atr_pct,
            freshness_ms=5_000,
            depth_score=min(100.0, turnover / 1e8 * 10),
            price_continuity=1.0 if spread_bps < 50 else 0.5,
            funding_abnormal=funding_abnormal,
        )
    logger.info("ticker_quality_count=%s", len(out))
    return out

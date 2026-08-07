"""Fetch Bybit Mainnet public linear instruments + tickers and build eligible universe."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from backend.market.scanner import universe_config as cfg

BYBIT = "https://api.bybit.com"
_UA = "NEXUS-EATI-MarketScanner/1.0 (read-only-public)"


def _get(path: str, params: dict[str, Any], timeout: float = 12.0) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    url = f"{BYBIT}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as raw:
        payload = json.loads(raw.read().decode("utf-8"))
    if int(payload.get("retCode", -1)) != 0:
        raise RuntimeError(payload.get("retMsg") or "bybit_error")
    return payload


def fetch_all_linear_tickers() -> list[dict[str, Any]]:
    payload = _get("/v5/market/tickers", {"category": "linear"})
    return list(((payload.get("result") or {}).get("list")) or [])


def fetch_linear_instruments() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cursor = ""
    for _ in range(20):
        params: dict[str, Any] = {"category": "linear", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        payload = _get("/v5/market/instruments-info", params)
        result = payload.get("result") or {}
        batch = list(result.get("list") or [])
        rows.extend(batch)
        cursor = str(result.get("nextPageCursor") or "")
        if not cursor or not batch:
            break
    return rows


def _f(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _spread_bps(bid: float | None, ask: float | None, last: float | None) -> float | None:
    if bid is None or ask is None or not last or last <= 0:
        return None
    if ask < bid:
        return None
    return ((ask - bid) / last) * 10_000.0


def symbol_type_of(instrument: dict[str, Any] | None) -> str:
    if not instrument:
        return ""
    return str(instrument.get("symbolType") or "").strip().lower()


def asset_disposition(symbol_type: str) -> str:
    """Crypto opportunity membership vs cross-asset context-only labeling."""
    st = (symbol_type or "").strip().lower()
    if st in cfg.NON_CRYPTO_SYMBOL_TYPES:
        return cfg.CROSS_ASSET_DISPOSITION
    return cfg.CRYPTO_OPPORTUNITY_DISPOSITION


def classify_exclusion(
    ticker: dict[str, Any],
    instrument: dict[str, Any] | None,
    now_ms: int,
) -> str | None:
    symbol = str(ticker.get("symbol") or "")
    if not symbol.endswith("USDT"):
        return "UNSUPPORTED"
    if symbol in cfg.BLACKLIST_SYMBOLS:
        return "UNSUPPORTED"
    if instrument is not None:
        status = str(instrument.get("status") or "")
        if status and status != "Trading":
            return "NOT_TRADING"
        quote = str(instrument.get("quoteCoin") or "")
        if quote and quote != "USDT":
            return "UNSUPPORTED"
        # Equity/ETF/commodity linear perps are listed on Bybit but are not crypto opportunities.
        st = symbol_type_of(instrument)
        if st in cfg.NON_CRYPTO_SYMBOL_TYPES:
            return "NON_CRYPTO_ASSET"
        launch = instrument.get("launchTime")
        if launch not in (None, ""):
            try:
                if now_ms - int(launch) < cfg.MIN_LISTING_AGE_MS:
                    return "NEW_LISTING"
            except (TypeError, ValueError):
                pass

    last = _f(ticker, "lastPrice")
    bid = _f(ticker, "bid1Price")
    ask = _f(ticker, "ask1Price")
    oi_val = _f(ticker, "openInterestValue")
    turnover = _f(ticker, "turnover24h")
    if last is None or bid is None or ask is None or oi_val is None or turnover is None:
        return "MISSING_FIELDS"
    if turnover < cfg.MIN_TURNOVER_24H_USDT:
        return "LOW_LIQUIDITY"
    if oi_val < cfg.MIN_OI_VALUE_USDT:
        return "LOW_OPEN_INTEREST"
    spread = _spread_bps(bid, ask, last)
    if spread is None:
        return "MISSING_FIELDS"
    if spread > cfg.MAX_SPREAD_BPS:
        return "WIDE_SPREAD"
    return None


def build_universe(
    tickers: list[dict[str, Any]] | None = None,
    instruments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    tickers = tickers if tickers is not None else fetch_all_linear_tickers()
    try:
        instruments = instruments if instruments is not None else fetch_linear_instruments()
    except Exception:
        instruments = instruments or []
    inst_by_sym = {str(r.get("symbol")): r for r in instruments if r.get("symbol")}

    excluded: list[dict[str, str]] = []
    eligible: list[dict[str, Any]] = []
    non_crypto_excluded = 0
    cross_asset_sample: list[dict[str, str]] = []
    for row in tickers:
        sym = str(row.get("symbol") or "")
        if not sym:
            continue
        inst = inst_by_sym.get(sym)
        reason = classify_exclusion(row, inst, now_ms)
        if reason:
            excluded.append({"symbol": sym, "reason": reason})
            if reason == "NON_CRYPTO_ASSET":
                non_crypto_excluded += 1
                if len(cross_asset_sample) < 20:
                    st = symbol_type_of(inst)
                    cross_asset_sample.append(
                        {
                            "symbol": sym,
                            "symbolType": st,
                            "disposition": asset_disposition(st),
                        }
                    )
            continue
        last = _f(row, "lastPrice") or 0.0
        bid = _f(row, "bid1Price")
        ask = _f(row, "ask1Price")
        st = symbol_type_of(inst)
        eligible.append(
            {
                "symbol": sym,
                "lastPrice": last,
                "markPrice": _f(row, "markPrice"),
                "indexPrice": _f(row, "indexPrice"),
                "bid1": bid,
                "ask1": ask,
                "spreadBps": _spread_bps(bid, ask, last),
                "change24hPct": (_f(row, "price24hPcnt") or 0.0) * 100.0,
                "openInterest": _f(row, "openInterest"),
                "openInterestValue": _f(row, "openInterestValue"),
                "fundingRate": _f(row, "fundingRate"),
                "nextFundingTime": int(row["nextFundingTime"])
                if row.get("nextFundingTime") not in (None, "")
                else None,
                "volume24h": _f(row, "volume24h"),
                "turnover24h": _f(row, "turnover24h"),
                "exchangeTimestamp": int(row["ts"]) if row.get("ts") not in (None, "") else now_ms,
                "receivedAt": now_ms,
                "source": "BYBIT_MAINNET_LINEAR",
                "symbolType": st or "crypto",
                "assetDisposition": asset_disposition(st),
            }
        )

    eligible.sort(key=lambda r: float(r.get("turnover24h") or 0.0), reverse=True)
    before = len(eligible)
    limited = eligible[: cfg.SYMBOL_LIMIT]
    for row in eligible[cfg.SYMBOL_LIMIT :]:
        excluded.append({"symbol": row["symbol"], "reason": "UNIVERSE_LIMIT"})

    # Data-truth metric: non-crypto must never remain in crypto opportunity universe.
    non_crypto_in_opportunity = sum(
        1
        for r in limited
        if str(r.get("assetDisposition") or "") == cfg.CROSS_ASSET_DISPOSITION
    )

    return {
        "source": "BYBIT_MAINNET_LINEAR",
        "generatedAt": now_ms,
        "total_linear_instruments": len(instruments) or len(tickers),
        "total_tickers_seen": len(tickers),
        "eligible_before_limit": before,
        "eligible_after_limit": len(limited),
        "excluded_count": len(excluded),
        "non_crypto_excluded_count": non_crypto_excluded,
        "non_crypto_symbol_in_crypto_opportunity_count": non_crypto_in_opportunity,
        "cross_asset_excluded_sample": cross_asset_sample,
        "symbol_limit": cfg.SYMBOL_LIMIT,
        "ranking_basis": "turnover24h",
        "refresh_interval_sec": cfg.SNAPSHOT_INTERVAL_SEC,
        "symbols": [r["symbol"] for r in limited],
        "rows": limited,
        "excluded_sample": excluded[:40],
        "read_only": True,
        "private_api": False,
        "api_key_used": False,
    }

"""Read-only historical microstructure fetch (OI / funding / trades) via demo public API.

Never invent zeros for missing series. No private Mainnet. No trading writes.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.demo_domain import DEMO_REST_BASE_URL

EXCHANGE = "bybit"
BASE = DEMO_REST_BASE_URL


@dataclass
class MicroSeries:
    exchange: str
    endpoint: str
    symbol: str
    series_type: str
    start_time: int
    end_time: int
    record_count: int
    checksum: str
    missing_rate: float
    supported_status: str
    points: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get(path: str, params: dict[str, str], *, timeout: float = 30.0) -> dict[str, Any]:
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "nexus-edge-research-v3/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_funding_history(*, symbol: str, start_ms: int, end_ms: int, max_pages: int = 40) -> MicroSeries:
    path = "/v5/market/funding/history"
    collected: dict[int, dict[str, Any]] = {}
    cursor_end = int(end_ms)
    status = "AVAILABLE"
    try:
        for _ in range(max_pages):
            data = _get(
                path,
                {
                    "category": "linear",
                    "symbol": symbol.upper(),
                    "endTime": str(cursor_end),
                    "limit": "200",
                },
            )
            if int(data.get("retCode") or 0) != 0:
                status = "API_UNSUPPORTED"
                break
            rows = (data.get("result") or {}).get("list") or []
            if not rows:
                break
            oldest = None
            for row in rows:
                ts = int(row.get("fundingRateTimestamp") or 0)
                if start_ms <= ts <= end_ms:
                    collected[ts] = {"ts_ms": ts, "funding_rate": float(row.get("fundingRate") or 0.0)}
                oldest = ts if oldest is None else min(oldest, ts)
            if oldest is None or oldest <= start_ms:
                break
            cursor_end = oldest - 1
            time.sleep(0.05)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ValueError):
        status = "API_UNSUPPORTED"
        collected = {}
    pts = [collected[k] for k in sorted(collected)]
    if status == "AVAILABLE" and len(pts) < 10:
        status = "INSUFFICIENT_HISTORY"
    checksum = hashlib.sha256(json.dumps(pts, separators=(",", ":")).encode()).hexdigest()
    expected = max(1, int((end_ms - start_ms) / (8 * 3600 * 1000)))
    missing_rate = max(0.0, 1.0 - (len(pts) / expected)) if expected else 1.0
    return MicroSeries(
        exchange=EXCHANGE,
        endpoint=path,
        symbol=symbol.upper(),
        series_type="funding",
        start_time=pts[0]["ts_ms"] if pts else start_ms,
        end_time=pts[-1]["ts_ms"] if pts else end_ms,
        record_count=len(pts),
        checksum=checksum,
        missing_rate=round(missing_rate, 6),
        supported_status=status,
        points=pts,
    )


def fetch_open_interest(
    *, symbol: str, start_ms: int, end_ms: int, interval_time: str = "1h", max_pages: int = 50
) -> MicroSeries:
    path = "/v5/market/open-interest"
    collected: dict[int, dict[str, Any]] = {}
    cursor_end = int(end_ms)
    status = "AVAILABLE"
    try:
        for _ in range(max_pages):
            data = _get(
                path,
                {
                    "category": "linear",
                    "symbol": symbol.upper(),
                    "intervalTime": interval_time,
                    "endTime": str(cursor_end),
                    "limit": "200",
                },
            )
            if int(data.get("retCode") or 0) != 0:
                status = "API_UNSUPPORTED"
                break
            rows = (data.get("result") or {}).get("list") or []
            if not rows:
                break
            oldest = None
            for row in rows:
                ts = int(row.get("timestamp") or 0)
                if start_ms <= ts <= end_ms and row.get("openInterest") is not None:
                    collected[ts] = {"ts_ms": ts, "open_interest": float(row["openInterest"])}
                oldest = ts if oldest is None else min(oldest, ts)
            if oldest is None or oldest <= start_ms:
                break
            cursor_end = oldest - 1
            time.sleep(0.05)
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ValueError):
        status = "API_UNSUPPORTED"
        collected = {}
    pts = [collected[k] for k in sorted(collected)]
    if status == "AVAILABLE" and len(pts) < 24:
        status = "INSUFFICIENT_HISTORY"
    checksum = hashlib.sha256(json.dumps(pts, separators=(",", ":")).encode()).hexdigest()
    expected = max(1, int((end_ms - start_ms) / 3_600_000))
    missing_rate = max(0.0, 1.0 - (len(pts) / expected)) if expected else 1.0
    return MicroSeries(
        exchange=EXCHANGE,
        endpoint=path,
        symbol=symbol.upper(),
        series_type="open_interest",
        start_time=pts[0]["ts_ms"] if pts else start_ms,
        end_time=pts[-1]["ts_ms"] if pts else end_ms,
        record_count=len(pts),
        checksum=checksum,
        missing_rate=round(min(1.0, missing_rate), 6),
        supported_status=status,
        points=pts,
    )


def probe_trade_flow(*, symbol: str) -> MicroSeries:
    path = "/v5/market/recent-trade"
    status = "INSUFFICIENT_HISTORY"
    pts: list[dict[str, Any]] = []
    try:
        data = _get(path, {"category": "linear", "symbol": symbol.upper(), "limit": "1000"})
        if int(data.get("retCode") or 0) != 0:
            status = "API_UNSUPPORTED"
        else:
            for row in (data.get("result") or {}).get("list") or []:
                pts.append(
                    {
                        "ts_ms": int(row.get("time") or 0),
                        "side": row.get("side"),
                        "size": float(row.get("size") or 0),
                        "price": float(row.get("price") or 0),
                    }
                )
            status = "INSUFFICIENT_HISTORY"
    except (urllib.error.URLError, TimeoutError, OSError, RuntimeError, ValueError):
        status = "API_UNSUPPORTED"
    return MicroSeries(
        exchange=EXCHANGE,
        endpoint=path,
        symbol=symbol.upper(),
        series_type="recent_trade",
        start_time=pts[-1]["ts_ms"] if pts else 0,
        end_time=pts[0]["ts_ms"] if pts else 0,
        record_count=len(pts),
        checksum=hashlib.sha256(json.dumps(pts[:20], separators=(",", ":")).encode()).hexdigest(),
        missing_rate=1.0,
        supported_status=status,
        points=[],
    )


def lookup_asof(points: list[dict[str, Any]], ts_ms: int, key: str) -> float | None:
    if not points:
        return None
    lo, hi = 0, len(points) - 1
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        t = int(points[mid]["ts_ms"])
        if t <= ts_ms:
            best = points[mid]
            lo = mid + 1
        else:
            hi = mid - 1
    if best is None or best.get(key) is None:
        return None
    return float(best[key])


def oi_change_pct(points: list[dict[str, Any]], ts_ms: int, lookback: int = 6) -> float | None:
    if not points:
        return None
    idx = None
    for i, p in enumerate(points):
        if int(p["ts_ms"]) <= ts_ms:
            idx = i
        else:
            break
    if idx is None or idx < lookback:
        return None
    a = float(points[idx - lookback]["open_interest"])
    b = float(points[idx]["open_interest"])
    if a <= 0:
        return None
    return (b - a) / a


def _empty(series_type: str, endpoint: str, symbol: str, start_ms: int, end_ms: int, status: str) -> MicroSeries:
    return MicroSeries(
        exchange=EXCHANGE,
        endpoint=endpoint,
        symbol=symbol,
        series_type=series_type,
        start_time=start_ms,
        end_time=end_ms,
        record_count=0,
        checksum="",
        missing_rate=1.0,
        supported_status=status,
        points=[],
    )


def _load_series(path: Path) -> MicroSeries:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    return MicroSeries(
        exchange=str(raw.get("exchange") or EXCHANGE),
        endpoint=str(raw.get("endpoint") or ""),
        symbol=str(raw.get("symbol") or ""),
        series_type=str(raw.get("series_type") or ""),
        start_time=int(raw.get("start_time") or 0),
        end_time=int(raw.get("end_time") or 0),
        record_count=int(raw.get("record_count") or 0),
        checksum=str(raw.get("checksum") or ""),
        missing_rate=float(raw.get("missing_rate") or 1.0),
        supported_status=str(raw.get("supported_status") or "DATA_UNAVAILABLE"),
        points=list(raw.get("points") or []),
    )


def fetch_or_load_micro_bundle(
    *,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
    cache_dir: Path,
    use_network: bool = True,
) -> dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {
        "funding": {},
        "open_interest": {},
        "trade_flow": {},
        "cvd": {
            "supported_status": "INSUFFICIENT_HISTORY",
            "note": "No historical trade backfill for CVD",
        },
        "liquidation": {
            "supported_status": "DATA_UNAVAILABLE",
            "note": "No legitimate public liquidation history wired",
        },
    }
    manifest = []
    for sym in symbols:
        f_cache = cache_dir / f"{sym}_funding_{start_ms}_{end_ms}.json"
        o_cache = cache_dir / f"{sym}_oi_1h_{start_ms}_{end_ms}.json"
        if f_cache.exists():
            fund = _load_series(f_cache)
        elif use_network:
            fund = fetch_funding_history(symbol=sym, start_ms=start_ms, end_ms=end_ms)
            f_cache.write_text(json.dumps(fund.to_dict(), indent=2) + "\n", encoding="utf-8")
        else:
            fund = _empty("funding", "/v5/market/funding/history", sym, start_ms, end_ms, "DATA_UNAVAILABLE")
        if o_cache.exists():
            oi = _load_series(o_cache)
        elif use_network:
            oi = fetch_open_interest(symbol=sym, start_ms=start_ms, end_ms=end_ms)
            o_cache.write_text(json.dumps(oi.to_dict(), indent=2) + "\n", encoding="utf-8")
        else:
            oi = _empty("open_interest", "/v5/market/open-interest", sym, start_ms, end_ms, "DATA_UNAVAILABLE")
        tf = (
            probe_trade_flow(symbol=sym)
            if use_network
            else _empty("recent_trade", "/v5/market/recent-trade", sym, 0, 0, "INSUFFICIENT_HISTORY")
        )
        out["funding"][sym] = fund
        out["open_interest"][sym] = oi
        out["trade_flow"][sym] = tf
        for s in (fund, oi, tf):
            meta = {k: v for k, v in s.to_dict().items() if k != "points"}
            manifest.append(meta)
    (cache_dir / "microstructure_manifest.json").write_text(
        json.dumps({"series": manifest}, indent=2) + "\n", encoding="utf-8"
    )
    return out

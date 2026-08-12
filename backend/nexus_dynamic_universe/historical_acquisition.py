"""Resumable checksummed historical acquisition for eligible symbols."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

PUBLIC_BASE = "https://api.bybit.com"
CoverageStatus = Literal["AVAILABLE", "MISSING", "UNKNOWN", "STALE", "UNSUPPORTED"]

REQUIRED_INTERVALS = ("15", "60", "240")
OPTIONAL_INTERVALS = ("5",)  # intrabar sequencing only — not strategy feature


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_obj(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass
class SeriesCoverage:
    symbol: str
    timeframe: str
    series_type: str
    first_available_timestamp: int | None
    last_available_timestamp: int | None
    expected_records: int | None
    actual_records: int
    missing_records: int | None
    duplicate_records: int
    out_of_order_records: int
    coverage_ratio: float | None
    provider: str
    download_timestamp: str
    content_checksum: str
    status: CoverageStatus

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _get(params: dict[str, str], *, path: str, timeout: float = 30.0) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    url = f"{PUBLIC_BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "nexus-hist-acq/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_kline_page(
    *,
    symbol: str,
    interval: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 1000,
    category: str = "linear",
) -> list[list[Any]]:
    params: dict[str, str] = {
        "category": category,
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": str(max(1, min(1000, int(limit)))),
    }
    if start_ms is not None:
        params["start"] = str(int(start_ms))
    if end_ms is not None:
        params["end"] = str(int(end_ms))
    data = _get(params, path="/v5/market/kline")
    if int(data.get("retCode") or 0) != 0:
        raise RuntimeError(f"kline_error:{data.get('retCode')}:{data.get('retMsg')}")
    return list((data.get("result") or {}).get("list") or [])


def fetch_mark_kline_page(**kwargs: Any) -> list[list[Any]]:
    params = {
        "category": kwargs.get("category", "linear"),
        "symbol": str(kwargs["symbol"]).upper(),
        "interval": str(kwargs["interval"]),
        "limit": str(max(1, min(1000, int(kwargs.get("limit", 1000))))),
    }
    if kwargs.get("start_ms") is not None:
        params["start"] = str(int(kwargs["start_ms"]))
    if kwargs.get("end_ms") is not None:
        params["end"] = str(int(kwargs["end_ms"]))
    data = _get(params, path="/v5/market/mark-price-kline")
    if int(data.get("retCode") or 0) != 0:
        raise RuntimeError(f"mark_kline_error:{data.get('retCode')}:{data.get('retMsg')}")
    return list((data.get("result") or {}).get("list") or [])


def fetch_index_kline_page(**kwargs: Any) -> list[list[Any]]:
    params = {
        "category": kwargs.get("category", "linear"),
        "symbol": str(kwargs["symbol"]).upper(),
        "interval": str(kwargs["interval"]),
        "limit": str(max(1, min(1000, int(kwargs.get("limit", 1000))))),
    }
    if kwargs.get("start_ms") is not None:
        params["start"] = str(int(kwargs["start_ms"]))
    if kwargs.get("end_ms") is not None:
        params["end"] = str(int(kwargs["end_ms"]))
    data = _get(params, path="/v5/market/index-price-kline")
    if int(data.get("retCode") or 0) != 0:
        raise RuntimeError(f"index_kline_error:{data.get('retCode')}:{data.get('retMsg')}")
    return list((data.get("result") or {}).get("list") or [])


def analyze_rows(rows: list[list[Any]]) -> tuple[int, int, int, int | None, int | None]:
    """Returns actual, duplicates, out_of_order, first_ts, last_ts."""
    if not rows:
        return 0, 0, 0, None, None
    stamps = [int(r[0]) for r in rows]
    stamps_sorted = sorted(stamps)
    dup = len(stamps) - len(set(stamps))
    ooo = sum(1 for a, b in zip(stamps, stamps[1:]) if a > b)
    return len(stamps), dup, ooo, stamps_sorted[0], stamps_sorted[-1]


def interval_ms(interval: str) -> int:
    return {"5": 300_000, "15": 900_000, "60": 3_600_000, "240": 14_400_000}[interval]


def fetch_series_resumable(
    *,
    symbol: str,
    interval: str,
    series_type: str,
    start_ms: int,
    end_ms: int,
    cache_dir: Path,
    rate_limit_s: float = 0.08,
    max_pages: int = 80,
) -> SeriesCoverage:
    """Fetch or load cached series; never invent zeros for missing OI/funding."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = f"{symbol}_{series_type}_{interval}_{start_ms}_{end_ms}.json"
    cache_path = cache_dir / key
    download_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if cache_path.exists():
        raw = cache_path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        rows = payload.get("rows") or []
        actual, dup, ooo, first_ts, last_ts = analyze_rows(rows)
        expected = max(0, (end_ms - start_ms) // interval_ms(interval))
        missing = max(0, expected - actual) if expected else None
        ratio = (actual / expected) if expected else None
        return SeriesCoverage(
            symbol=symbol,
            timeframe=interval,
            series_type=series_type,
            first_available_timestamp=first_ts,
            last_available_timestamp=last_ts,
            expected_records=expected,
            actual_records=actual,
            missing_records=missing,
            duplicate_records=dup,
            out_of_order_records=ooo,
            coverage_ratio=ratio,
            provider="bybit_public",
            download_timestamp=str(payload.get("download_timestamp") or download_ts),
            content_checksum=_sha_bytes(raw),
            status="AVAILABLE" if actual > 0 else "MISSING",
        )

    fetch_fn = {
        "trade": fetch_kline_page,
        "mark": fetch_mark_kline_page,
        "index": fetch_index_kline_page,
    }.get(series_type)
    if fetch_fn is None:
        return SeriesCoverage(
            symbol=symbol,
            timeframe=interval,
            series_type=series_type,
            first_available_timestamp=None,
            last_available_timestamp=None,
            expected_records=None,
            actual_records=0,
            missing_records=None,
            duplicate_records=0,
            out_of_order_records=0,
            coverage_ratio=None,
            provider="bybit_public",
            download_timestamp=download_ts,
            content_checksum=_sha_obj({"unsupported": series_type}),
            status="UNSUPPORTED",
        )

    all_rows: list[list[Any]] = []
    cursor_end = end_ms
    for _ in range(max_pages):
        page = fetch_fn(symbol=symbol, interval=interval, start_ms=start_ms, end_ms=cursor_end, limit=1000)
        if not page:
            break
        all_rows.extend(page)
        oldest = min(int(r[0]) for r in page)
        if oldest <= start_ms:
            break
        cursor_end = oldest - 1
        time.sleep(rate_limit_s)

    # Deduplicate by timestamp
    by_ts: dict[int, list[Any]] = {}
    for r in all_rows:
        by_ts[int(r[0])] = r
    rows = [by_ts[k] for k in sorted(by_ts)]
    blob = {
        "symbol": symbol,
        "series_type": series_type,
        "interval": interval,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "download_timestamp": download_ts,
        "rows": rows,
        "note": "Never replace missing OI/funding with zero",
    }
    raw = json.dumps(blob, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    cache_path.write_bytes(raw)
    actual, dup, ooo, first_ts, last_ts = analyze_rows(rows)
    expected = max(0, (end_ms - start_ms) // interval_ms(interval))
    missing = max(0, expected - actual) if expected else None
    ratio = (actual / expected) if expected else None
    return SeriesCoverage(
        symbol=symbol,
        timeframe=interval,
        series_type=series_type,
        first_available_timestamp=first_ts,
        last_available_timestamp=last_ts,
        expected_records=expected,
        actual_records=actual,
        missing_records=missing,
        duplicate_records=dup,
        out_of_order_records=ooo,
        coverage_ratio=ratio,
        provider="bybit_public",
        download_timestamp=download_ts,
        content_checksum=_sha_bytes(raw),
        status="AVAILABLE" if actual > 0 else "MISSING",
    )


def eligibility_gates(
    *,
    listing_age_days: float | None,
    coverage_ratio: float | None,
    turnover_24h: float | None,
    oi_value: float | None,
    spread_bps: float | None,
    slippage_bps: float | None,
    mark_status: CoverageStatus,
    candle_status: CoverageStatus,
    require_oi: bool = False,
) -> tuple[bool, list[str]]:
    """Preregistered data/execution-quality gates — before strategy performance."""
    fails: list[str] = []
    if listing_age_days is None or listing_age_days < 30:
        fails.append("insufficient_listing_age")
    if coverage_ratio is None or coverage_ratio < 0.85:
        fails.append("insufficient_contiguous_history")
    if turnover_24h is None or turnover_24h < 1_000_000:
        fails.append("minimum_turnover")
    if require_oi and (oi_value is None or oi_value <= 0):
        fails.append("minimum_open_interest")
    if spread_bps is not None and spread_bps > 20:
        fails.append("spread_proxy")
    if slippage_bps is not None and slippage_bps > 15:
        fails.append("slippage_estimate")
    if candle_status != "AVAILABLE":
        fails.append("candle_coverage")
    if mark_status not in ("AVAILABLE", "UNKNOWN"):
        fails.append("mark_price_coverage")
    return (len(fails) == 0, fails)

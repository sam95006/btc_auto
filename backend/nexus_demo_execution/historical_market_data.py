"""Real historical Bybit USDT Linear Perpetual kline provenance + fetch.

Public market data only. No interpolation. Synthetic paths forbidden for qualification.
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

BYBIT_PUBLIC = "https://api.bybit.com"
SOURCE_ENDPOINT = "/v5/market/kline"
MARKET_TYPE = "linear"
EXCHANGE = "bybit"


@dataclass
class Candle:
    ts_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketDataset:
    exchange: str
    market_type: str
    symbol: str
    interval: str
    start_time: int
    end_time: int
    record_count: int
    downloaded_at: float
    source_endpoint: str
    data_checksum: str
    missing_interval_count: int
    duplicate_interval_count: int
    timestamps_monotonic: bool
    duplicate_records: int
    future_data_used: bool
    candles: list[Candle] = field(default_factory=list)
    data_gaps: list[dict[str, Any]] = field(default_factory=list)
    classification: str = "REAL_HISTORICAL_MARKET_DATA"

    def provenance(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "market_type": self.market_type,
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "record_count": self.record_count,
            "downloaded_at": self.downloaded_at,
            "source_endpoint": self.source_endpoint,
            "data_checksum": self.data_checksum,
            "missing_interval_count": self.missing_interval_count,
            "duplicate_interval_count": self.duplicate_interval_count,
            "timestamps_monotonic": self.timestamps_monotonic,
            "duplicate_records": self.duplicate_records,
            "future_data_used": self.future_data_used,
            "classification": self.classification,
            "gap_count": len(self.data_gaps),
        }


def _f(v: Any) -> float:
    return float(v)


def interval_ms(interval: str) -> int:
    mapping = {
        "1": 60_000,
        "3": 180_000,
        "5": 300_000,
        "15": 900_000,
        "30": 1_800_000,
        "60": 3_600_000,
        "120": 7_200_000,
        "240": 14_400_000,
        "D": 86_400_000,
    }
    if interval not in mapping:
        raise ValueError(f"unsupported_interval:{interval}")
    return mapping[interval]


def parse_kline_rows(raw: list[Any]) -> list[Candle]:
    """Bybit returns newest-first; convert to chronological Candle list."""
    rows: list[Candle] = []
    for item in raw:
        if not isinstance(item, list) or len(item) < 5:
            continue
        rows.append(
            Candle(
                ts_ms=int(item[0]),
                open=_f(item[1]),
                high=_f(item[2]),
                low=_f(item[3]),
                close=_f(item[4]),
                volume=_f(item[5]) if len(item) > 5 else 0.0,
            )
        )
    rows.sort(key=lambda c: c.ts_ms)
    return rows


def _http_get(params: dict[str, str], *, timeout: float = 30.0) -> dict[str, Any]:
    qs = urllib.parse.urlencode(params)
    url = f"{BYBIT_PUBLIC}{SOURCE_ENDPOINT}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "nexus-geometry-qualify/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_klines_page(
    *,
    symbol: str,
    interval: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    limit: int = 1000,
) -> list[Candle]:
    params: dict[str, str] = {
        "category": MARKET_TYPE,
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": str(max(1, min(1000, int(limit)))),
    }
    if start_ms is not None:
        params["start"] = str(int(start_ms))
    if end_ms is not None:
        params["end"] = str(int(end_ms))
    data = _http_get(params)
    if int(data.get("retCode") or 0) != 0:
        raise RuntimeError(f"bybit_kline_error:{data.get('retCode')}:{data.get('retMsg')}")
    raw = (data.get("result") or {}).get("list") or []
    return parse_kline_rows(raw)


def fetch_historical_klines(
    *,
    symbol: str,
    interval: str = "15",
    start_ms: int,
    end_ms: int,
    max_pages: int = 40,
) -> MarketDataset:
    """Paginate public klines backward from end_ms until start_ms."""
    if end_ms <= start_ms:
        raise ValueError("end_ms_must_exceed_start_ms")
    step = interval_ms(interval)
    cursor_end = int(end_ms)
    collected: dict[int, Candle] = {}
    downloaded_at = time.time()
    for _ in range(max(1, max_pages)):
        page = fetch_klines_page(symbol=symbol, interval=interval, end_ms=cursor_end, limit=1000)
        if not page:
            break
        for c in page:
            if start_ms <= c.ts_ms <= end_ms:
                collected[c.ts_ms] = c
        oldest = min(c.ts_ms for c in page)
        if oldest <= start_ms:
            break
        cursor_end = oldest - 1
        time.sleep(0.05)
    candles = [collected[k] for k in sorted(collected)]
    return build_dataset(
        symbol=symbol,
        interval=interval,
        candles=candles,
        downloaded_at=downloaded_at,
        expected_step_ms=step,
    )


def build_dataset(
    *,
    symbol: str,
    interval: str,
    candles: list[Candle],
    downloaded_at: float | None = None,
    expected_step_ms: int | None = None,
) -> MarketDataset:
    step = expected_step_ms or interval_ms(interval)
    downloaded_at = downloaded_at if downloaded_at is not None else time.time()
    now_ms = int(time.time() * 1000)
    future = sum(1 for c in candles if c.ts_ms > now_ms + step)
    mono = all(candles[i].ts_ms < candles[i + 1].ts_ms for i in range(len(candles) - 1)) if len(candles) > 1 else True
    # duplicates already collapsed by ts key when fetched; count any equal consecutive
    dup = sum(1 for i in range(len(candles) - 1) if candles[i].ts_ms == candles[i + 1].ts_ms)
    gaps: list[dict[str, Any]] = []
    missing = 0
    for i in range(len(candles) - 1):
        delta = candles[i + 1].ts_ms - candles[i].ts_ms
        if delta > step * 1.5:
            n_miss = int(round(delta / step)) - 1
            missing += max(0, n_miss)
            gaps.append(
                {
                    "class": "DATA_GAP",
                    "from_ts": candles[i].ts_ms,
                    "to_ts": candles[i + 1].ts_ms,
                    "missing_intervals": max(0, n_miss),
                }
            )
    payload = [
        [c.ts_ms, c.open, c.high, c.low, c.close, c.volume]
        for c in candles
    ]
    checksum = hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    start_t = candles[0].ts_ms if candles else 0
    end_t = candles[-1].ts_ms if candles else 0
    classification = "REAL_HISTORICAL_MARKET_DATA"
    if future > 0 or not mono or dup > 0:
        classification = "DATA_INVALID"
    return MarketDataset(
        exchange=EXCHANGE,
        market_type=MARKET_TYPE,
        symbol=symbol.upper(),
        interval=interval,
        start_time=start_t,
        end_time=end_t,
        record_count=len(candles),
        downloaded_at=downloaded_at,
        source_endpoint=SOURCE_ENDPOINT,
        data_checksum=checksum,
        missing_interval_count=missing,
        duplicate_interval_count=dup,
        timestamps_monotonic=mono,
        duplicate_records=dup,
        future_data_used=future > 0,
        candles=candles,
        data_gaps=gaps,
        classification=classification,
    )


def save_dataset(ds: MarketDataset, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = {
        **ds.provenance(),
        "candles": [c.to_dict() for c in ds.candles],
        "data_gaps": ds.data_gaps,
    }
    path.write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")


def load_dataset(path: Path) -> MarketDataset:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    candles = [
        Candle(
            ts_ms=int(c["ts_ms"]),
            open=float(c["open"]),
            high=float(c["high"]),
            low=float(c["low"]),
            close=float(c["close"]),
            volume=float(c.get("volume") or 0.0),
        )
        for c in (raw.get("candles") or [])
    ]
    return build_dataset(
        symbol=str(raw.get("symbol") or "UNKNOWN"),
        interval=str(raw.get("interval") or "15"),
        candles=candles,
        downloaded_at=float(raw.get("downloaded_at") or time.time()),
    )


def fetch_or_load_bundle(
    *,
    symbols: list[str],
    interval: str,
    start_ms: int,
    end_ms: int,
    cache_dir: Path,
    use_network: bool = True,
) -> list[MarketDataset]:
    out: list[MarketDataset] = []
    for sym in symbols:
        cache = cache_dir / f"{sym.upper()}_{interval}_{start_ms}_{end_ms}.json"
        if cache.exists():
            ds = load_dataset(cache)
            out.append(ds)
            continue
        if not use_network:
            raise FileNotFoundError(f"missing_cached_market_data:{cache}")
        try:
            ds = fetch_historical_klines(
                symbol=sym, interval=interval, start_ms=start_ms, end_ms=end_ms
            )
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as exc:
            raise RuntimeError(f"market_data_fetch_failed:{sym}:{type(exc).__name__}") from exc
        save_dataset(ds, cache)
        out.append(ds)
    return out

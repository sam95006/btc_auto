"""NEXUS_RESEARCH_DATA_BUNDLE_V1 — multi-timeframe point-in-time synchronized bundles."""
from __future__ import annotations

import gzip
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset

DATA_BUNDLE_VERSION = "NEXUS_RESEARCH_DATA_BUNDLE_V1"

BUNDLE_STATUSES = frozenset(
    {
        "PRICE_MULTI_TIMEFRAME_READY",
        "DERIVATIVES_MULTI_TIMEFRAME_READY",
        "PRICE_ONLY_READY",
        "LIVE_MONITOR_ONLY",
        "DATA_INVALID",
    }
)

INTERVAL_MS = {"5": 300_000, "15": 900_000, "60": 3_600_000, "240": 14_400_000}


def _rows_to_candles(rows: list[Any]) -> list[Candle]:
    out: list[Candle] = []
    for r in rows:
        if isinstance(r, dict):
            out.append(
                Candle(
                    ts_ms=int(r.get("ts_ms") or r.get("start") or r["ts"]),
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r.get("volume") or r.get("vol") or 0),
                )
            )
        else:
            out.append(
                Candle(
                    ts_ms=int(r[0]),
                    open=float(r[1]),
                    high=float(r[2]),
                    low=float(r[3]),
                    close=float(r[4]),
                    volume=float(r[5]) if len(r) > 5 else 0.0,
                )
            )
    out.sort(key=lambda c: c.ts_ms)
    return out


def compute_partition_integrity(candles: list[Candle], *, interval: str) -> dict[str, Any]:
    """Compute integrity over the COMPLETE partition — never hardcode zeros."""
    step = INTERVAL_MS.get(str(interval), 900_000)
    if not candles:
        return {
            "record_count": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "missing_interval_count": 0,
            "duplicate_interval_count": 0,
            "non_monotonic_count": 0,
            "OHLC_integrity_error_count": 0,
            "future_timestamp_count": 0,
            "timestamps_monotonic": True,
            "full_partition_checksum": sha_candles([]),
            "valid": False,
            "fail_closed": True,
        }
    missing = 0
    duplicates = 0
    non_mono = 0
    ohlc_err = 0
    future = 0
    now_ms = int(time.time() * 1000) + 60_000
    seen: set[int] = set()
    prev_ts: int | None = None
    for c in candles:
        if c.ts_ms in seen:
            duplicates += 1
        seen.add(c.ts_ms)
        if prev_ts is not None:
            if c.ts_ms < prev_ts:
                non_mono += 1
            elif c.ts_ms - prev_ts > step * 1.5:
                # count gaps in expected steps
                missing += max(0, int(round((c.ts_ms - prev_ts) / step)) - 1)
        prev_ts = c.ts_ms
        if c.high < c.low or c.open < 0 or c.close < 0 or c.high < max(c.open, c.close) * 0.999:
            # soft OHLC: high must be >= open/close/low roughly
            if c.high < c.low or min(c.open, c.close, c.high, c.low) < 0:
                ohlc_err += 1
            elif c.high < max(c.open, c.close) or c.low > min(c.open, c.close):
                ohlc_err += 1
        if c.ts_ms > now_ms:
            future += 1
    checksum = sha_candles(candles)
    valid = (
        len(candles) >= 80
        and non_mono == 0
        and future == 0
        and ohlc_err == 0
        and duplicates == 0
    )
    return {
        "record_count": len(candles),
        "first_timestamp": candles[0].ts_ms,
        "last_timestamp": candles[-1].ts_ms,
        "missing_interval_count": missing,
        "duplicate_interval_count": duplicates,
        "non_monotonic_count": non_mono,
        "OHLC_integrity_error_count": ohlc_err,
        "future_timestamp_count": future,
        "timestamps_monotonic": non_mono == 0,
        "full_partition_checksum": checksum,
        "valid": valid,
        "fail_closed": not valid,
    }


def sha_candles(candles: list[Candle]) -> str:
    """Checksum covers the COMPLETE normalized partition, not a sample."""
    blob = json.dumps(
        [[c.ts_ms, c.open, c.high, c.low, c.close, c.volume] for c in candles],
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def resample_ohlcv(candles: list[Candle], *, target_interval: str) -> list[Candle]:
    """Deterministic as-of resampling from finer bars — no forward fill of future."""
    step = INTERVAL_MS[str(target_interval)]
    if not candles:
        return []
    buckets: dict[int, list[Candle]] = {}
    for c in candles:
        bucket = (c.ts_ms // step) * step
        buckets.setdefault(bucket, []).append(c)
    out: list[Candle] = []
    for ts in sorted(buckets):
        group = buckets[ts]
        out.append(
            Candle(
                ts_ms=ts,
                open=group[0].open,
                high=max(x.high for x in group),
                low=min(x.low for x in group),
                close=group[-1].close,
                volume=sum(x.volume for x in group),
            )
        )
    return out


def _load_json_candles(path: Path) -> list[Candle] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, dict) and raw.get("candles"):
        candles = []
        for c in raw["candles"]:
            if isinstance(c, dict):
                candles.append(
                    Candle(
                        ts_ms=int(c["ts_ms"]),
                        open=float(c["open"]),
                        high=float(c["high"]),
                        low=float(c["low"]),
                        close=float(c["close"]),
                        volume=float(c.get("volume") or 0),
                    )
                )
            else:
                candles.append(
                    Candle(
                        ts_ms=int(c[0]),
                        open=float(c[1]),
                        high=float(c[2]),
                        low=float(c[3]),
                        close=float(c[4]),
                        volume=float(c[5] if len(c) > 5 else 0),
                    )
                )
        candles.sort(key=lambda x: x.ts_ms)
        return candles
    if isinstance(raw, dict) and "rows" in raw:
        return _rows_to_candles(raw["rows"])
    return None


def _load_gz_candles(path: Path) -> list[Candle] | None:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return None
    if isinstance(raw, dict) and "rows" in raw:
        return _rows_to_candles(raw["rows"])
    if isinstance(raw, dict) and raw.get("candles"):
        return _rows_to_candles(
            [
                {
                    "ts_ms": c["ts_ms"] if isinstance(c, dict) else c[0],
                    "open": c["open"] if isinstance(c, dict) else c[1],
                    "high": c["high"] if isinstance(c, dict) else c[2],
                    "low": c["low"] if isinstance(c, dict) else c[3],
                    "close": c["close"] if isinstance(c, dict) else c[4],
                    "volume": (c.get("volume") if isinstance(c, dict) else (c[5] if len(c) > 5 else 0)),
                }
                for c in raw["candles"]
            ]
        )
    return None


def _mk_dataset(symbol: str, interval: str, candles: list[Candle], source: str) -> MarketDataset | None:
    integ = compute_partition_integrity(candles, interval=interval)
    if integ["fail_closed"]:
        return None
    return MarketDataset(
        exchange="bybit",
        market_type="linear",
        symbol=symbol,
        interval=str(interval),
        start_time=int(integ["first_timestamp"]),
        end_time=int(integ["last_timestamp"]),
        record_count=int(integ["record_count"]),
        downloaded_at=time.time(),
        source_endpoint=source,
        data_checksum=str(integ["full_partition_checksum"]),
        missing_interval_count=int(integ["missing_interval_count"]),
        duplicate_interval_count=int(integ["duplicate_interval_count"]),
        timestamps_monotonic=bool(integ["timestamps_monotonic"]),
        duplicate_records=int(integ["duplicate_interval_count"]),
        future_data_used=bool(integ["future_timestamp_count"] > 0),
        candles=candles,
    )


@dataclass
class ResearchDataBundle:
    symbol: str
    status: str
    candles_15: list[Candle] = field(default_factory=list)
    candles_60: list[Candle] = field(default_factory=list)
    candles_240: list[Candle] = field(default_factory=list)
    candles_5: list[Candle] = field(default_factory=list)
    mark_15: list[Candle] = field(default_factory=list)
    index_15: list[Candle] = field(default_factory=list)
    funding_points: list[dict[str, Any]] = field(default_factory=list)
    oi_points: list[dict[str, Any]] = field(default_factory=list)
    integrity_15: dict[str, Any] = field(default_factory=dict)
    integrity_60: dict[str, Any] = field(default_factory=dict)
    integrity_240: dict[str, Any] = field(default_factory=dict)
    size_class: str = "UNKNOWN"
    sources: dict[str, str] = field(default_factory=dict)
    required_feature_status: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("candles_15", "candles_60", "candles_240", "candles_5", "mark_15", "index_15"):
            d[k] = [{"ts_ms": c.ts_ms, "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume} for c in getattr(self, k)[:3]]
            d[f"{k}_count"] = len(getattr(self, k))
        return d

    def dataset_15(self) -> MarketDataset | None:
        return _mk_dataset(self.symbol, "15", self.candles_15, self.sources.get("15", "bundle"))


def _classify_size(symbol: str) -> str:
    meme_tok = ("DOGE", "PEPE", "SATS", "SHIB", "WIF", "BONK", "RATS", "XEC", "MEME", "FLOKI")
    if any(t in symbol for t in meme_tok):
        return "MEME"
    mainstream = {
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "BNBUSDT",
        "AVAXUSDT",
        "LINKUSDT",
        "DOTUSDT",
        "LTCUSDT",
        "BCHUSDT",
        "NEARUSDT",
        "ATOMUSDT",
        "UNIUSDT",
        "APTUSDT",
        "ARBUSDT",
        "OPUSDT",
        "SUIUSDT",
        "TONUSDT",
        "TRXUSDT",
        "XAUUSDT",
    }
    mid = {"HYPEUSDT", "ZECUSDT", "SOXLUSDT", "AAVEUSDT", "MKRUSDT", "INJUSDT", "FILUSDT", "SEIUSDT", "TIAUSDT"}
    if symbol in mainstream:
        return "MAINSTREAM"
    if symbol in mid:
        return "MID_SIZE"
    # default small for lesser-known alts in research set
    if symbol.endswith("USDT"):
        return "SMALL" if symbol not in mainstream else "MAINSTREAM"
    return "UNKNOWN"


def load_research_data_bundles(root: Path) -> list[ResearchDataBundle]:
    """Load point-in-time synchronized multi-TF bundles from local caches only."""
    by_sym: dict[str, ResearchDataBundle] = {}
    h5 = root / ".nexus_runtime" / "research" / "dynamic_universe_h5_v1" / "market_cache"
    if h5.is_dir():
        for p in sorted(h5.glob("*_*_*.json")):
            parts = p.name.split("_")
            if len(parts) < 2:
                continue
            sym, interval = parts[0], parts[1]
            if interval not in {"5", "15", "60", "240"}:
                continue
            candles = _load_json_candles(p)
            if not candles:
                continue
            b = by_sym.setdefault(sym, ResearchDataBundle(symbol=sym, status="LIVE_MONITOR_ONLY"))
            b.size_class = _classify_size(sym)
            b.sources[interval] = str(p)
            if interval == "15":
                b.candles_15 = candles
                b.integrity_15 = compute_partition_integrity(candles, interval="15")
            elif interval == "60":
                b.candles_60 = candles
                b.integrity_60 = compute_partition_integrity(candles, interval="60")
            elif interval == "240":
                b.candles_240 = candles
                b.integrity_240 = compute_partition_integrity(candles, interval="240")
            elif interval == "5":
                b.candles_5 = candles

    ga = root / ".nexus_runtime" / "research" / "goal_alignment_v1" / "hist_queue" / "partitions"
    if ga.is_dir():
        for p in sorted(ga.glob("*.json.gz")):
            name = p.name
            # SYMBOL_kind_interval_...
            bits = name.split("_")
            if len(bits) < 3:
                continue
            sym, kind, interval = bits[0], bits[1], bits[2]
            candles = _load_gz_candles(p)
            if not candles:
                continue
            b = by_sym.setdefault(sym, ResearchDataBundle(symbol=sym, status="LIVE_MONITOR_ONLY"))
            b.size_class = _classify_size(sym)
            key = f"{kind}_{interval}"
            b.sources[key] = str(p)
            if kind == "trade" and interval == "15" and not b.candles_15:
                b.candles_15 = candles
                b.integrity_15 = compute_partition_integrity(candles, interval="15")
            elif kind == "trade" and interval == "60" and not b.candles_60:
                b.candles_60 = candles
                b.integrity_60 = compute_partition_integrity(candles, interval="60")
            elif kind == "trade" and interval == "240" and not b.candles_240:
                b.candles_240 = candles
                b.integrity_240 = compute_partition_integrity(candles, interval="240")
            elif kind == "mark" and interval == "15":
                b.mark_15 = candles
            elif kind == "index" and interval == "15":
                b.index_15 = candles

    # Resample missing HTF from 15m when needed (as-of, no lookahead)
    for b in by_sym.values():
        if b.candles_15 and not b.candles_60:
            b.candles_60 = resample_ohlcv(b.candles_15, target_interval="60")
            b.integrity_60 = compute_partition_integrity(b.candles_60, interval="60")
            b.sources["60"] = b.sources.get("60") or "resampled_from_15"
        if b.candles_15 and not b.candles_240:
            b.candles_240 = resample_ohlcv(b.candles_15, target_interval="240")
            b.integrity_240 = compute_partition_integrity(b.candles_240, interval="240")
            b.sources["240"] = b.sources.get("240") or "resampled_from_15"

        # Feature status — never invent zeros
        b.required_feature_status = {
            "price_15": "OK" if b.candles_15 else "MISSING",
            "price_60": "OK" if b.candles_60 else "MISSING",
            "price_240": "OK" if b.candles_240 else "MISSING",
            "funding": "OK" if b.funding_points else "MISSING",
            "open_interest": "OK" if b.oi_points else "MISSING",
            "mark": "OK" if b.mark_15 else "MISSING",
            "index": "OK" if b.index_15 else "MISSING",
        }

        price_mtf = bool(b.candles_15 and b.candles_60 and b.candles_240 and b.integrity_15.get("valid"))
        deriv_mtf = bool(price_mtf and b.mark_15 and b.index_15 and b.funding_points and b.oi_points)
        if not b.candles_15 or not b.integrity_15.get("valid"):
            b.status = "DATA_INVALID"
        elif deriv_mtf:
            b.status = "DERIVATIVES_MULTI_TIMEFRAME_READY"
        elif price_mtf:
            # mark/index without funding still not derivatives-ready
            if b.mark_15 and b.index_15:
                b.status = "PRICE_MULTI_TIMEFRAME_READY"
            else:
                b.status = "PRICE_MULTI_TIMEFRAME_READY"
        elif b.candles_15:
            b.status = "PRICE_ONLY_READY"
        else:
            b.status = "LIVE_MONITOR_ONLY"
        assert b.status in BUNDLE_STATUSES

    return [by_sym[k] for k in sorted(by_sym.keys())]


def try_attach_derivatives(bundles: list[ResearchDataBundle], *, max_symbols: int = 25) -> int:
    """Attempt read-only public fetch of funding/OI for up to max_symbols. No price proxy."""
    attached = 0
    try:
        from backend.nexus_demo_execution.microstructure_history import (
            fetch_funding_history,
            fetch_open_interest,
        )
    except Exception:
        return 0
    for b in bundles:
        if attached >= max_symbols:
            break
        if not b.candles_15:
            continue
        start = b.candles_15[0].ts_ms
        end = b.candles_15[-1].ts_ms
        try:
            fund = fetch_funding_history(symbol=b.symbol, start_ms=start, end_ms=end)
            oi = fetch_open_interest(symbol=b.symbol, start_ms=start, end_ms=end)
        except Exception:
            continue
        if fund.supported_status == "AVAILABLE" and fund.points:
            b.funding_points = fund.points
            b.required_feature_status["funding"] = "OK"
        else:
            b.required_feature_status["funding"] = "MISSING"
        if oi.supported_status == "AVAILABLE" and oi.points:
            b.oi_points = [{"ts_ms": p["ts_ms"], "open_interest": p.get("open_interest")} for p in oi.points]
            b.required_feature_status["open_interest"] = "OK"
        else:
            b.required_feature_status["open_interest"] = "MISSING"
        price_mtf = bool(b.candles_15 and b.candles_60 and b.candles_240)
        if (
            price_mtf
            and b.funding_points
            and b.oi_points
            and b.mark_15
            and b.index_15
        ):
            b.status = "DERIVATIVES_MULTI_TIMEFRAME_READY"
            attached += 1
        elif b.funding_points and b.oi_points:
            attached += 1
    return attached


def bundle_manifest(bundles: list[ResearchDataBundle]) -> dict[str, Any]:
    price = [b for b in bundles if b.status in {"PRICE_MULTI_TIMEFRAME_READY", "DERIVATIVES_MULTI_TIMEFRAME_READY", "PRICE_ONLY_READY"}]
    deriv = [b for b in bundles if b.funding_points and b.oi_points]
    mtf = [b for b in bundles if b.status in {"PRICE_MULTI_TIMEFRAME_READY", "DERIVATIVES_MULTI_TIMEFRAME_READY"}]
    invalid = [b for b in bundles if b.status == "DATA_INVALID"]
    by_class: dict[str, int] = {}
    for b in price:
        by_class[b.size_class] = by_class.get(b.size_class, 0) + 1
    full_checksum = hashlib.sha256(
        json.dumps(
            {b.symbol: b.integrity_15.get("full_partition_checksum") for b in bundles},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "schema": "research_data_bundle_manifest_v1",
        "data_bundle_version": DATA_BUNDLE_VERSION,
        "actual_loaded_dataset_count": len(bundles),
        "actual_price_dataset_count": len(price),
        "actual_derivatives_dataset_count": len(deriv),
        "multi_timeframe_ready_count": len(mtf),
        "data_integrity_failure_count": len(invalid),
        "actual_mainstream_dataset_count": by_class.get("MAINSTREAM", 0),
        "actual_mid_size_dataset_count": by_class.get("MID_SIZE", 0),
        "actual_small_dataset_count": by_class.get("SMALL", 0),
        "actual_meme_dataset_count": by_class.get("MEME", 0),
        "full_dataset_checksum": full_checksum,
        "acquisition_targets": {
            "actual_price_dataset_count": 60,
            "actual_derivatives_dataset_count": 20,
            "mainstream": 25,
            "mid_size": 15,
            "small": 10,
            "meme": 8,
        },
        "blockers": [
            "local_cache_limited_to_h5_plus_ga_partitions",
            "bulk_historical_download_not_authorized_in_this_repair_task",
            "derivatives_ready_requires_actual_funding_oi_mark_index_not_registry_label",
        ],
        "symbols": [
            {
                "symbol": b.symbol,
                "status": b.status,
                "size_class": b.size_class,
                "required_feature_status": b.required_feature_status,
                "integrity_15": {k: b.integrity_15.get(k) for k in (
                    "record_count",
                    "missing_interval_count",
                    "duplicate_interval_count",
                    "non_monotonic_count",
                    "full_partition_checksum",
                    "valid",
                )},
            }
            for b in bundles
        ],
    }

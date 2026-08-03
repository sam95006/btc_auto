"""Load MarketDataset from H5 JSON cache or goal-alignment gzip partitions."""
from __future__ import annotations

import gzip
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.historical_market_data import Candle, MarketDataset


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


def _mk_dataset(symbol: str, interval: str, candles: list[Candle], source: str) -> MarketDataset | None:
    if len(candles) < 80:
        return None
    blob = json.dumps([c.to_dict() for c in candles[:: max(1, len(candles) // 50)]], sort_keys=True)
    return MarketDataset(
        exchange="bybit",
        market_type="linear",
        symbol=symbol,
        interval=interval,
        start_time=candles[0].ts_ms,
        end_time=candles[-1].ts_ms,
        record_count=len(candles),
        downloaded_at=time.time(),
        source_endpoint=source,
        data_checksum=hashlib.sha256(blob.encode()).hexdigest(),
        missing_interval_count=0,
        duplicate_interval_count=0,
        timestamps_monotonic=True,
        duplicate_records=0,
        future_data_used=False,
        candles=candles,
    )


def load_dataset_from_json(path: Path) -> MarketDataset | None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and raw.get("candles"):
        candles = [
            Candle(
                ts_ms=int(c["ts_ms"] if isinstance(c, dict) else c[0]),
                open=float(c["open"] if isinstance(c, dict) else c[1]),
                high=float(c["high"] if isinstance(c, dict) else c[2]),
                low=float(c["low"] if isinstance(c, dict) else c[3]),
                close=float(c["close"] if isinstance(c, dict) else c[4]),
                volume=float((c.get("volume") if isinstance(c, dict) else (c[5] if len(c) > 5 else 0)) or 0),
            )
            for c in raw["candles"]
        ]
        candles.sort(key=lambda c: c.ts_ms)
        sym = str(raw.get("symbol") or path.name.split("_")[0])
        return _mk_dataset(sym, "15", candles, str(path))
    if isinstance(raw, dict) and "rows" in raw:
        return _mk_dataset(str(raw.get("symbol") or path.name.split("_")[0]), "15", _rows_to_candles(raw["rows"]), str(path))
    # full MarketDataset dump
    if isinstance(raw, dict) and "symbol" in raw and "candles" in raw:
        return load_dataset_from_json  # type: ignore
    return None


def load_dataset_from_gz(path: Path) -> MarketDataset | None:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict) or "rows" not in raw:
        return None
    return _mk_dataset(str(raw.get("symbol") or path.name.split("_")[0]), "15", _rows_to_candles(raw["rows"]), str(path))


def load_development_datasets(root: Path) -> list[MarketDataset]:
    by_sym: dict[str, MarketDataset] = {}
    h5 = root / ".nexus_runtime" / "research" / "dynamic_universe_h5_v1" / "market_cache"
    if h5.is_dir():
        for p in sorted(h5.glob("*_15_*.json")):
            # Prefer full MarketDataset JSON from fetch_or_load_bundle
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and "candles" in raw and "exchange" in raw:
                    candles = [
                        Candle(**{k: c[k] for k in ("ts_ms", "open", "high", "low", "close", "volume")})
                        if isinstance(c, dict)
                        else Candle(ts_ms=int(c[0]), open=float(c[1]), high=float(c[2]), low=float(c[3]), close=float(c[4]), volume=float(c[5] if len(c) > 5 else 0))
                        for c in raw["candles"]
                    ]
                    ds = MarketDataset(
                        exchange=str(raw.get("exchange") or "bybit"),
                        market_type=str(raw.get("market_type") or "linear"),
                        symbol=str(raw["symbol"]),
                        interval=str(raw.get("interval") or "15"),
                        start_time=int(raw.get("start_time") or candles[0].ts_ms),
                        end_time=int(raw.get("end_time") or candles[-1].ts_ms),
                        record_count=len(candles),
                        downloaded_at=float(raw.get("downloaded_at") or time.time()),
                        source_endpoint=str(raw.get("source_endpoint") or p),
                        data_checksum=str(raw.get("data_checksum") or "unknown"),
                        missing_interval_count=int(raw.get("missing_interval_count") or 0),
                        duplicate_interval_count=int(raw.get("duplicate_interval_count") or 0),
                        timestamps_monotonic=bool(raw.get("timestamps_monotonic", True)),
                        duplicate_records=int(raw.get("duplicate_records") or 0),
                        future_data_used=bool(raw.get("future_data_used", False)),
                        candles=candles,
                    )
                    if len(candles) >= 80:
                        by_sym[ds.symbol] = ds
                        continue
            except Exception:
                pass
            ds2 = load_dataset_from_json(p)
            if ds2:
                by_sym[ds2.symbol] = ds2
    ga = root / ".nexus_runtime" / "research" / "goal_alignment_v1" / "hist_queue" / "partitions"
    if ga.is_dir():
        for p in sorted(ga.glob("*_trade_15_*.json.gz")):
            ds = load_dataset_from_gz(p)
            if ds and ds.symbol not in by_sym:
                by_sym[ds.symbol] = ds
    return [by_sym[k] for k in sorted(by_sym.keys())]

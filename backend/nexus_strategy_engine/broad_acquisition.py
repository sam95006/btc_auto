"""Resumable broad research-data acquisition for Strategy Engine V1.2."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.closed_historical_registry import RESEARCH_V2_V3_END_MS
from backend.nexus_demo_execution.microstructure_history import (
    fetch_funding_history,
    fetch_open_interest,
)
from backend.nexus_dynamic_universe.historical_acquisition import fetch_series_resumable
from backend.nexus_strategy_engine.data_bundle import (
    DATA_BUNDLE_VERSION,
    ResearchDataBundle,
    compute_partition_integrity,
    load_research_data_bundles,
    resample_ohlcv,
)
from backend.nexus_demo_execution.historical_market_data import Candle

# Practical development window: 120d ending at sealed research end (enough for 5 folds)
DEV_END_MS = RESEARCH_V2_V3_END_MS
DEV_START_MS = DEV_END_MS - 120 * 24 * 3_600_000

MEME_TOKENS = ("DOGE", "PEPE", "SATS", "SHIB", "WIF", "BONK", "RATS", "XEC", "MEME", "FLOKI", "CAT", "MOG", "BABYDOGE")
MAINSTREAM = {
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "BNBUSDT", "AVAXUSDT", "LINKUSDT",
    "DOTUSDT", "LTCUSDT", "BCHUSDT", "NEARUSDT", "ATOMUSDT", "UNIUSDT", "APTUSDT", "ARBUSDT",
    "OPUSDT", "SUIUSDT", "TONUSDT", "TRXUSDT", "XAUUSDT", "MATICUSDT", "POLUSDT", "INJUSDT",
    "FILUSDT", "AAVEUSDT", "MKRUSDT", "LDOUSDT", "RENDERUSDT", "FETUSDT",
}
MID = {
    "HYPEUSDT", "ZECUSDT", "SOXLUSDT", "SEIUSDT", "TIAUSDT", "WLDUSDT", "JUPUSDT", "PYTHUSDT",
    "ORDIUSDT", "STXUSDT", "IMXUSDT", "RUNEUSDT", "GALAUSDT", "SANDUSDT", "MANAUSDT", "AXSUSDT",
    "CRVUSDT", "ENSUSDT", "BLURUSDT",
}


@dataclass
class AcquisitionProgress:
    symbols_attempted: list[str] = field(default_factory=list)
    completed_partitions: int = 0
    failed_partitions: int = 0
    pending_partitions: int = 0
    blockers: dict[str, list[str]] = field(default_factory=dict)
    resume_status: str = "NOT_STARTED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _classify(symbol: str) -> str:
    if any(t in symbol for t in MEME_TOKENS):
        return "MEME"
    if symbol in MAINSTREAM:
        return "MAINSTREAM"
    if symbol in MID:
        return "MID_SIZE"
    return "SMALL"


def _listing_age_days(launch_ms: int | None, now_ms: int) -> float | None:
    if not launch_ms:
        return None
    return max(0.0, (now_ms - int(launch_ms)) / 86_400_000)


def build_priority_queue(root: Path, *, target_price: int = 60) -> list[dict[str, Any]]:
    snaps = sorted((root / ".nexus_runtime/research/dynamic_universe_h5_v1/universe_snapshots").glob("universe_*.json"))
    if not snaps:
        raise FileNotFoundError("universe_snapshot_missing")
    raw = json.loads(snaps[-1].read_text(encoding="utf-8"))
    instruments = [x for x in (raw.get("instruments") or []) if x.get("eligible") and x.get("status") == "Trading"]
    now_ms = int(time.time() * 1000)
    scored: list[dict[str, Any]] = []
    for inst in instruments:
        sym = str(inst["symbol"]).upper()
        age = _listing_age_days(inst.get("launch_time"), now_ms)
        if age is not None and age < 30:
            continue
        size = _classify(sym)
        # Priority: diversity buckets first, then older listings
        bucket_rank = {"MAINSTREAM": 0, "MID_SIZE": 1, "SMALL": 2, "MEME": 3}.get(size, 4)
        scored.append(
            {
                "symbol": sym,
                "size_class": size,
                "listing_age_days": age,
                "bucket_rank": bucket_rank,
                "launch_time": inst.get("launch_time"),
                "tick_size": inst.get("tick_size"),
                "selection_basis": [
                    "instrument_validity",
                    "listing_age",
                    "symbol_profile_diversity",
                    "not_v1_v11_profitability",
                ],
            }
        )
    # Round-robin diversity
    by_bucket: dict[str, list] = {k: [] for k in ("MAINSTREAM", "MID_SIZE", "SMALL", "MEME")}
    for s in sorted(scored, key=lambda x: (-(x["listing_age_days"] or 0), x["symbol"])):
        by_bucket.setdefault(s["size_class"], []).append(s)
    queue: list[dict[str, Any]] = []
    targets = {"MAINSTREAM": 25, "MID_SIZE": 15, "SMALL": 10, "MEME": 8}
    # Fill targets first
    for b, n in targets.items():
        queue.extend(by_bucket.get(b, [])[:n])
    # Pad to target_price from remaining
    seen = {x["symbol"] for x in queue}
    for b in ("MAINSTREAM", "MID_SIZE", "SMALL", "MEME"):
        for s in by_bucket.get(b, []):
            if s["symbol"] in seen:
                continue
            queue.append(s)
            seen.add(s["symbol"])
            if len(queue) >= max(target_price + 20, 80):
                break
        if len(queue) >= max(target_price + 20, 80):
            break
    return queue


def _rows_to_candles(rows: list[list[Any]]) -> list[Candle]:
    out = []
    for r in rows:
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


def acquire_broad_datasets(
    root: Path,
    *,
    target_price: int = 60,
    target_derivatives: int = 20,
    rate_limit_s: float = 0.08,
    max_pages: int = 25,
) -> dict[str, Any]:
    cache = root / ".nexus_runtime/research/strategy_engine_v1_2/market_cache"
    progress_path = root / ".nexus_runtime/research/strategy_engine_v1_2/acquisition_progress.json"
    cache.mkdir(parents=True, exist_ok=True)

    progress = AcquisitionProgress(resume_status="RESUMING" if progress_path.exists() else "STARTED")
    if progress_path.exists():
        prev = json.loads(progress_path.read_text(encoding="utf-8"))
        progress.completed_partitions = int(prev.get("completed_partitions") or 0)
        progress.failed_partitions = int(prev.get("failed_partitions") or 0)

    queue = build_priority_queue(root, target_price=target_price)
    # Also keep already-local symbols
    existing = load_research_data_bundles(root)
    existing_syms = {b.symbol for b in existing}

    bundles_by_sym: dict[str, ResearchDataBundle] = {b.symbol: b for b in existing}
    price_ready: list[str] = []
    deriv_ready: list[str] = []

    def _save_progress():
        progress_path.write_text(json.dumps(progress.to_dict(), indent=2) + "\n", encoding="utf-8")

    attempted = 0
    for item in queue:
        sym = item["symbol"]
        if len(price_ready) >= target_price and len(deriv_ready) >= target_derivatives:
            break
        if sym in price_ready:
            continue
        attempted += 1
        progress.symbols_attempted.append(sym)
        print(
            f"acquire {sym} ({attempted}) price={len(price_ready)} deriv={len(deriv_ready)}",
            flush=True,
        )
        blockers: list[str] = []
        try:
            trade15 = fetch_series_resumable(
                symbol=sym,
                interval="15",
                series_type="trade",
                start_ms=DEV_START_MS,
                end_ms=DEV_END_MS,
                cache_dir=cache,
                rate_limit_s=rate_limit_s,
                max_pages=max_pages,
            )
            progress.completed_partitions += 1
            if trade15.status != "AVAILABLE" or trade15.actual_records < 80:
                blockers.append("TRADE_CANDLE_MISSING")
                progress.blockers[sym] = blockers
                progress.failed_partitions += 1
                _save_progress()
                continue
            # Load candles from cache file
            key = f"{sym}_trade_15_{DEV_START_MS}_{DEV_END_MS}.json"
            payload = json.loads((cache / key).read_text(encoding="utf-8"))
            c15 = _rows_to_candles(payload.get("rows") or [])
            integ = compute_partition_integrity(c15, interval="15")
            if integ["fail_closed"]:
                blockers.append("DATA_GAPS" if integ["missing_interval_count"] else "DATA_INTEGRITY_INVALID")
                progress.blockers[sym] = blockers
                _save_progress()
                continue

            # 60 / 240 — fetch if needed else resample
            c60: list[Candle] = []
            c240: list[Candle] = []
            for interval, holder_name in (("60", "c60"), ("240", "c240")):
                try:
                    cov = fetch_series_resumable(
                        symbol=sym,
                        interval=interval,
                        series_type="trade",
                        start_ms=DEV_START_MS,
                        end_ms=DEV_END_MS,
                        cache_dir=cache,
                        rate_limit_s=rate_limit_s,
                        max_pages=max(8, max_pages // 2),
                    )
                    progress.completed_partitions += 1
                    if cov.status == "AVAILABLE" and cov.actual_records >= 40:
                        p = cache / f"{sym}_trade_{interval}_{DEV_START_MS}_{DEV_END_MS}.json"
                        rows = json.loads(p.read_text(encoding="utf-8")).get("rows") or []
                        candles = _rows_to_candles(rows)
                        if holder_name == "c60":
                            c60 = candles
                        else:
                            c240 = candles
                except Exception as exc:
                    progress.failed_partitions += 1
                    progress.blockers.setdefault(sym, []).append(f"OTHER_EXPLICIT_REASON:{type(exc).__name__}")
            if not c60:
                c60 = resample_ohlcv(c15, target_interval="60")
            if not c240:
                c240 = resample_ohlcv(c15, target_interval="240")

            b = bundles_by_sym.get(sym) or ResearchDataBundle(symbol=sym, status="LIVE_MONITOR_ONLY")
            b.size_class = item["size_class"]
            b.candles_15 = c15
            b.candles_60 = c60
            b.candles_240 = c240
            b.integrity_15 = integ
            b.integrity_60 = compute_partition_integrity(c60, interval="60")
            b.integrity_240 = compute_partition_integrity(c240, interval="240")
            b.sources["15"] = str(cache / key)
            b.status = "PRICE_MULTI_TIMEFRAME_READY"
            b.required_feature_status = {
                "price_15": "OK",
                "price_60": "OK" if c60 else "MISSING",
                "price_240": "OK" if c240 else "MISSING",
                "funding": "MISSING",
                "open_interest": "MISSING",
                "mark": "MISSING",
                "index": "MISSING",
            }
            bundles_by_sym[sym] = b
            price_ready.append(sym)

            # Derivatives for first target_derivatives + extras
            if len(deriv_ready) < target_derivatives + 5:
                try:
                    mark = fetch_series_resumable(
                        symbol=sym, interval="15", series_type="mark",
                        start_ms=DEV_START_MS, end_ms=DEV_END_MS, cache_dir=cache,
                        rate_limit_s=rate_limit_s, max_pages=max_pages,
                    )
                    index = fetch_series_resumable(
                        symbol=sym, interval="15", series_type="index",
                        start_ms=DEV_START_MS, end_ms=DEV_END_MS, cache_dir=cache,
                        rate_limit_s=rate_limit_s, max_pages=max_pages,
                    )
                    progress.completed_partitions += 2
                    if mark.status == "AVAILABLE":
                        mp = cache / f"{sym}_mark_15_{DEV_START_MS}_{DEV_END_MS}.json"
                        b.mark_15 = _rows_to_candles(json.loads(mp.read_text(encoding="utf-8")).get("rows") or [])
                        b.required_feature_status["mark"] = "OK"
                    else:
                        blockers.append("MARK_PRICE_MISSING")
                    if index.status == "AVAILABLE":
                        ip = cache / f"{sym}_index_15_{DEV_START_MS}_{DEV_END_MS}.json"
                        b.index_15 = _rows_to_candles(json.loads(ip.read_text(encoding="utf-8")).get("rows") or [])
                        b.required_feature_status["index"] = "OK"
                    else:
                        blockers.append("INDEX_PRICE_MISSING")

                    fund = fetch_funding_history(symbol=sym, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
                    oi = fetch_open_interest(symbol=sym, start_ms=DEV_START_MS, end_ms=DEV_END_MS)
                    if fund.supported_status == "AVAILABLE" and fund.points:
                        b.funding_points = fund.points
                        b.required_feature_status["funding"] = "OK"
                    else:
                        blockers.append("FUNDING_MISSING")
                    if oi.supported_status == "AVAILABLE" and oi.points:
                        b.oi_points = [
                            {"ts_ms": p["ts_ms"], "open_interest": p.get("open_interest")} for p in oi.points
                        ]
                        b.required_feature_status["open_interest"] = "OK"
                    else:
                        blockers.append("OPEN_INTEREST_MISSING")

                    if (
                        b.funding_points
                        and b.oi_points
                        and b.mark_15
                        and b.index_15
                    ):
                        b.status = "DERIVATIVES_MULTI_TIMEFRAME_READY"
                        deriv_ready.append(sym)
                except Exception as exc:
                    blockers.append(f"OTHER_EXPLICIT_REASON:{type(exc).__name__}")
            if blockers:
                progress.blockers[sym] = blockers
        except Exception as exc:
            progress.failed_partitions += 1
            progress.blockers[sym] = [f"OTHER_EXPLICIT_REASON:{type(exc).__name__}"]
        _save_progress()
        # Soft stop if enough price
        if len(price_ready) >= target_price and len(deriv_ready) >= target_derivatives:
            break

    progress.resume_status = "COMPLETE"
    progress.pending_partitions = max(0, (target_price * 3 + target_derivatives * 4) - progress.completed_partitions)
    _save_progress()

    bundles = [bundles_by_sym[k] for k in sorted(bundles_by_sym.keys()) if bundles_by_sym[k].candles_15]
    # Counts
    from collections import Counter

    size_c = Counter(b.size_class for b in bundles if b.status != "DATA_INVALID")
    price_n = sum(1 for b in bundles if b.status in {"PRICE_MULTI_TIMEFRAME_READY", "DERIVATIVES_MULTI_TIMEFRAME_READY", "PRICE_ONLY_READY"})
    deriv_n = sum(1 for b in bundles if b.funding_points and b.oi_points and b.mark_15 and b.index_15)
    checksum = __import__("hashlib").sha256(
        json.dumps({b.symbol: b.integrity_15.get("full_partition_checksum") for b in bundles}, sort_keys=True).encode()
    ).hexdigest()

    return {
        "schema": "broad_data_acquisition_manifest_v1_2",
        "data_bundle_version": DATA_BUNDLE_VERSION,
        "dev_window": {"start_ms": DEV_START_MS, "end_ms": DEV_END_MS},
        "symbols_attempted": progress.symbols_attempted,
        "symbols_attempted_count": len(progress.symbols_attempted),
        "existing_local_before": sorted(existing_syms),
        "actual_loaded_dataset_count": len(bundles),
        "actual_price_dataset_count": price_n,
        "actual_derivatives_dataset_count": deriv_n,
        "actual_mainstream_dataset_count": size_c.get("MAINSTREAM", 0),
        "actual_mid_size_dataset_count": size_c.get("MID_SIZE", 0),
        "actual_small_dataset_count": size_c.get("SMALL", 0),
        "actual_meme_dataset_count": size_c.get("MEME", 0),
        "trade_15m_ready_count": sum(1 for b in bundles if b.candles_15),
        "trade_60m_ready_count": sum(1 for b in bundles if b.candles_60),
        "trade_240m_ready_count": sum(1 for b in bundles if b.candles_240),
        "trade_5m_ready_count": sum(1 for b in bundles if b.candles_5),
        "funding_ready_count": sum(1 for b in bundles if b.funding_points),
        "open_interest_ready_count": sum(1 for b in bundles if b.oi_points),
        "mark_price_ready_count": sum(1 for b in bundles if b.mark_15),
        "index_price_ready_count": sum(1 for b in bundles if b.index_15),
        "download_completed_partitions": progress.completed_partitions,
        "download_failed_partitions": progress.failed_partitions,
        "download_pending_partitions": progress.pending_partitions,
        "download_resume_status": progress.resume_status,
        "full_dataset_checksum": checksum,
        "historical_record_count": sum(len(b.candles_15) for b in bundles),
        "blockers": progress.blockers,
        "coverage_gate_price_ok": price_n >= target_price,
        "coverage_gate_derivatives_ok": deriv_n >= target_derivatives,
        "bundles": bundles,
    }

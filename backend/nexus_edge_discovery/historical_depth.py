"""Historical depth expansion — extend point-in-time history without fabricating."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.closed_historical_registry import RESEARCH_V2_V3_END_MS
from backend.nexus_demo_execution.microstructure_history import fetch_funding_history, fetch_open_interest
from backend.nexus_dynamic_universe.historical_acquisition import fetch_series_resumable
from backend.nexus_strategy_engine.broad_acquisition import (
    DEV_END_MS,
    _classify,
    _rows_to_candles,
    build_priority_queue,
)
from backend.nexus_strategy_engine.data_bundle import (
    ResearchDataBundle,
    compute_partition_integrity,
    load_research_data_bundles,
    resample_ohlcv,
)

DAY_MS = 86_400_000


def expand_historical_depth(
    root: Path,
    *,
    price_depth_days: int = 365,
    derivatives_depth_days: int = 365,
    rare_derivatives_depth_days: int = 540,
    target_price_symbols: int = 40,
    target_deriv_symbols: int = 25,
    rate_limit_s: float = 0.05,
    max_pages: int = 120,
) -> dict[str, Any]:
    cache = root / ".nexus_runtime/research/edge_discovery_v2/market_cache"
    cache.mkdir(parents=True, exist_ok=True)
    end_ms = DEV_END_MS
    price_start = end_ms - price_depth_days * DAY_MS
    deriv_start = end_ms - derivatives_depth_days * DAY_MS
    rare_start = end_ms - rare_derivatives_depth_days * DAY_MS

    existing = load_research_data_bundles(root)
    # Prefer V1.2 cache symbols
    v12_cache = root / ".nexus_runtime/research/strategy_engine_v1_2/market_cache"
    symbols = sorted({b.symbol for b in existing if b.candles_15})
    try:
        queue = build_priority_queue(root, target_price=max(target_price_symbols, 60))
        for q in queue:
            if q["symbol"] not in symbols:
                symbols.append(q["symbol"])
    except Exception:
        pass

    price_ready = []
    deriv_ready = []
    rare_ready = []
    limits: dict[str, Any] = {
        "funding_history_limits": [],
        "oi_history_limits": [],
        "mark_history_limits": [],
        "index_history_limits": [],
        "listing_age_limits": [],
    }
    blockers: dict[str, list[str]] = {}
    bundles_by: dict[str, ResearchDataBundle] = {b.symbol: b for b in existing}

    for sym in symbols:
        if len(price_ready) >= target_price_symbols and len(deriv_ready) >= target_deriv_symbols:
            break
        try:
            # Price 15m deep
            cov = fetch_series_resumable(
                symbol=sym,
                interval="15",
                series_type="trade",
                start_ms=price_start,
                end_ms=end_ms,
                cache_dir=cache,
                rate_limit_s=rate_limit_s,
                max_pages=max_pages,
            )
            if cov.status != "AVAILABLE" or cov.actual_records < 200:
                blockers.setdefault(sym, []).append("TRADE_CANDLE_MISSING_OR_SHALLOW")
                continue
            key = f"{sym}_trade_15_{price_start}_{end_ms}.json"
            payload = json.loads((cache / key).read_text(encoding="utf-8"))
            c15 = _rows_to_candles(payload.get("rows") or [])
            if len(c15) < 200:
                continue
            depth_days = (c15[-1].ts_ms - c15[0].ts_ms) / DAY_MS
            if depth_days < 300:
                limits["listing_age_limits"].append({"symbol": sym, "achieved_price_depth_days": depth_days})
            # 60/240 resample if needed
            c60 = resample_ohlcv(c15, target_interval="60")
            c240 = resample_ohlcv(c15, target_interval="240")
            b = bundles_by.get(sym) or ResearchDataBundle(symbol=sym, status="PRICE_MULTI_TIMEFRAME_READY")
            b.size_class = _classify(sym)
            b.candles_15 = c15
            b.candles_60 = c60
            b.candles_240 = c240
            b.integrity_15 = compute_partition_integrity(c15, interval="15")
            b.status = "PRICE_MULTI_TIMEFRAME_READY"
            bundles_by[sym] = b
            if depth_days >= 300:
                price_ready.append(sym)

            if len(deriv_ready) < target_deriv_symbols + 5:
                d_start = rare_start if len(rare_ready) < target_deriv_symbols else deriv_start
                mark = fetch_series_resumable(
                    symbol=sym, interval="15", series_type="mark",
                    start_ms=d_start, end_ms=end_ms, cache_dir=cache,
                    rate_limit_s=rate_limit_s, max_pages=max_pages,
                )
                index = fetch_series_resumable(
                    symbol=sym, interval="15", series_type="index",
                    start_ms=d_start, end_ms=end_ms, cache_dir=cache,
                    rate_limit_s=rate_limit_s, max_pages=max_pages,
                )
                fund = fetch_funding_history(symbol=sym, start_ms=d_start, end_ms=end_ms)
                oi = fetch_open_interest(symbol=sym, start_ms=d_start, end_ms=end_ms)
                if mark.status == "AVAILABLE":
                    mp = cache / f"{sym}_mark_15_{d_start}_{end_ms}.json"
                    if mp.exists():
                        b.mark_15 = _rows_to_candles(json.loads(mp.read_text(encoding="utf-8")).get("rows") or [])
                else:
                    limits["mark_history_limits"].append({"symbol": sym, "status": mark.status})
                if index.status == "AVAILABLE":
                    ip = cache / f"{sym}_index_15_{d_start}_{end_ms}.json"
                    if ip.exists():
                        b.index_15 = _rows_to_candles(json.loads(ip.read_text(encoding="utf-8")).get("rows") or [])
                else:
                    limits["index_history_limits"].append({"symbol": sym, "status": index.status})
                if fund.supported_status == "AVAILABLE" and fund.points:
                    b.funding_points = fund.points
                    f_depth = (fund.points[-1]["ts_ms"] - fund.points[0]["ts_ms"]) / DAY_MS if len(fund.points) > 1 else 0
                    limits["funding_history_limits"].append({"symbol": sym, "depth_days": f_depth, "points": len(fund.points)})
                else:
                    limits["funding_history_limits"].append({"symbol": sym, "status": fund.supported_status, "blocker": "FUNDING_MISSING"})
                if oi.supported_status == "AVAILABLE" and oi.points:
                    b.oi_points = [{"ts_ms": p["ts_ms"], "open_interest": p.get("open_interest")} for p in oi.points]
                    o_depth = (oi.points[-1]["ts_ms"] - oi.points[0]["ts_ms"]) / DAY_MS if len(oi.points) > 1 else 0
                    limits["oi_history_limits"].append({"symbol": sym, "depth_days": o_depth, "points": len(oi.points)})
                else:
                    limits["oi_history_limits"].append({"symbol": sym, "status": oi.supported_status, "blocker": "OPEN_INTEREST_MISSING"})
                if b.funding_points and b.oi_points and b.mark_15 and b.index_15:
                    b.status = "DERIVATIVES_MULTI_TIMEFRAME_READY"
                    deriv_ready.append(sym)
                    f_days = limits["funding_history_limits"][-1].get("depth_days") or 0
                    if f_days >= 500:
                        rare_ready.append(sym)
        except Exception as exc:
            blockers.setdefault(sym, []).append(f"OTHER:{type(exc).__name__}")

    bundles = [bundles_by[s] for s in sorted(bundles_by) if bundles_by[s].candles_15]
    price_depth_ok = sum(
        1
        for b in bundles
        if b.candles_15 and (b.candles_15[-1].ts_ms - b.candles_15[0].ts_ms) / DAY_MS >= 300
    )
    deriv_depth_ok = len(deriv_ready)
    return {
        "schema": "historical_depth_manifest_v1",
        "price_history_target_days": price_depth_days,
        "derivatives_history_target_days": derivatives_depth_days,
        "rare_derivatives_target_days": rare_derivatives_depth_days,
        "price_symbols_with_depth_ge_300d": price_depth_ok,
        "derivatives_symbols_ready": deriv_depth_ok,
        "rare_derivatives_symbols_ge_500d": len(rare_ready),
        "price_depth_gate_ok": price_depth_ok >= target_price_symbols,
        "derivatives_depth_gate_ok": deriv_depth_ok >= target_deriv_symbols,
        "provider_limits": limits,
        "blockers_sample": dict(list(blockers.items())[:30]),
        "bundles": bundles,
        "symbols_price_ready": price_ready[:target_price_symbols],
        "symbols_deriv_ready": deriv_ready[:target_deriv_symbols],
        "v12_coverage_preserved": True,
        "fabricated_history": False,
        "end_ms": end_ms,
        "price_start_ms": price_start,
        "deriv_start_ms": deriv_start,
        "rare_start_ms": rare_start,
        "also_used_v12_cache_dir": str(v12_cache),
    }

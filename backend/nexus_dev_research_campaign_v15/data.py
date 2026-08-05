"""Development-classified real historical data loader for V15-C.

Never consumes untouched OOS. Fixtures are labeled FIXTURE_NOT_REAL when used.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.historical_market_data import (
    Candle,
    MarketDataset,
    fetch_or_load_bundle,
)
from backend.nexus_demo_execution.microstructure_history import (
    fetch_funding_history,
    fetch_open_interest,
)
from backend.nexus_dev_research_campaign_v15.constants import (
    DEFAULT_INTERVAL,
    DEFAULT_SYMBOLS,
    DEV_END_MS,
    DEV_START_MS,
    DEVELOPMENT_INTERVAL_ID,
    RANDOM_SEED,
)
from backend.nexus_dev_research_campaign_v15.hard_bans import assert_interval_not_oos


@dataclass
class DevelopmentBar:
    ts_ms: int
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    mid: float
    mid_return: float
    funding_rate: float | None
    open_interest: float | None
    data_quality_ok: bool = True


@dataclass
class DevelopmentPanel:
    classification: str  # REAL_HISTORICAL_DEVELOPMENT | FIXTURE_NOT_REAL
    development_interval_id: str
    start_ms: int
    end_ms: int
    interval: str
    symbols: list[str]
    bars_by_symbol: dict[str, list[DevelopmentBar]]
    provenance: dict[str, Any] = field(default_factory=dict)
    oos_consumed: bool = False
    fixture_used: bool = False

    @property
    def is_real(self) -> bool:
        return self.classification == "REAL_HISTORICAL_DEVELOPMENT" and not self.fixture_used


def _align_series(
    candles: list[Candle],
    funding_pts: list[dict[str, Any]],
    oi_pts: list[dict[str, Any]],
    *,
    symbol: str,
) -> list[DevelopmentBar]:
    fund_by_ts = {int(p["ts_ms"]): float(p["funding_rate"]) for p in funding_pts}
    oi_by_ts = {int(p["ts_ms"]): float(p["open_interest"]) for p in oi_pts}
    fund_times = sorted(fund_by_ts)
    oi_times = sorted(oi_by_ts)

    def _asof(times: list[int], mapping: dict[int, float], ts: int) -> float | None:
        if not times:
            return None
        # last observation with t <= ts
        lo, hi = 0, len(times) - 1
        best = None
        while lo <= hi:
            mid = (lo + hi) // 2
            if times[mid] <= ts:
                best = times[mid]
                lo = mid + 1
            else:
                hi = mid - 1
        return mapping[best] if best is not None else None

    out: list[DevelopmentBar] = []
    prev_close: float | None = None
    for c in candles:
        mid = float(c.close)
        ret = 0.0 if prev_close is None or prev_close <= 0 else (mid - prev_close) / prev_close
        prev_close = mid
        dq = c.high >= c.low and c.close > 0 and c.open > 0
        out.append(
            DevelopmentBar(
                ts_ms=int(c.ts_ms),
                symbol=symbol,
                open=float(c.open),
                high=float(c.high),
                low=float(c.low),
                close=float(c.close),
                volume=float(c.volume),
                mid=mid,
                mid_return=float(ret),
                funding_rate=_asof(fund_times, fund_by_ts, int(c.ts_ms)),
                open_interest=_asof(oi_times, oi_by_ts, int(c.ts_ms)),
                data_quality_ok=dq,
            )
        )
    return out


def _fixture_panel(
    *,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
    interval: str,
    seed: int = RANDOM_SEED,
) -> DevelopmentPanel:
    """Clearly labeled synthetic fixture — NEVER called real."""
    rng = random.Random(seed)
    step = 3_600_000 if interval == "60" else 900_000
    n = max(120, min(800, int((end_ms - start_ms) / step)))
    bars_by_symbol: dict[str, list[DevelopmentBar]] = {}
    for sym_i, sym in enumerate(symbols):
        px = 100.0 + 10.0 * sym_i
        bars: list[DevelopmentBar] = []
        oi = 1_000_000.0 + 50_000.0 * sym_i
        for i in range(n):
            ts = start_ms + i * step
            shock = rng.gauss(0.0, 0.004)
            # mild regime structure
            if (i // 80) % 3 == 0:
                shock += 0.0015
            elif (i // 80) % 3 == 2:
                shock -= 0.0012
            open_ = px
            close = max(1.0, px * (1.0 + shock))
            high = max(open_, close) * (1.0 + abs(rng.gauss(0, 0.001)))
            low = min(open_, close) * (1.0 - abs(rng.gauss(0, 0.001)))
            vol = abs(rng.gauss(1000, 200))
            fund = rng.gauss(0.0, 0.00005)
            oi = max(1.0, oi * (1.0 + rng.gauss(0.0, 0.002)))
            bars.append(
                DevelopmentBar(
                    ts_ms=ts,
                    symbol=sym,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    volume=vol,
                    mid=close,
                    mid_return=(close - open_) / open_ if open_ else 0.0,
                    funding_rate=fund,
                    open_interest=oi,
                    data_quality_ok=True,
                )
            )
            px = close
        bars_by_symbol[sym] = bars
    digest = hashlib.sha256(
        json.dumps(
            {s: [(b.ts_ms, b.close) for b in bars_by_symbol[s][:5]] for s in symbols},
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return DevelopmentPanel(
        classification="FIXTURE_NOT_REAL",
        development_interval_id=f"FIXTURE_NOT_REAL_{DEVELOPMENT_INTERVAL_ID}",
        start_ms=start_ms,
        end_ms=end_ms,
        interval=interval,
        symbols=list(symbols),
        bars_by_symbol=bars_by_symbol,
        provenance={
            "data_lineage": "FIXTURE_NOT_REAL",
            "fixture_synthetic": True,
            "never_call_fixture_real": True,
            "series_digest": digest,
            "seed": seed,
            "note": "Real historical fetch unavailable or incomplete; fixture labeled NOT REAL.",
        },
        oos_consumed=False,
        fixture_used=True,
    )


def load_development_panel(
    *,
    root: Path,
    symbols: tuple[str, ...] | list[str] = DEFAULT_SYMBOLS,
    interval: str = DEFAULT_INTERVAL,
    start_ms: int = DEV_START_MS,
    end_ms: int = DEV_END_MS,
    use_network: bool = True,
    allow_fixture_fallback: bool = True,
) -> DevelopmentPanel:
    assert_interval_not_oos(start_ms, end_ms)
    if end_ms > DEV_END_MS:
        raise ValueError("end_ms exceeds development window; refusing (would approach OOS)")
    if start_ms < DEV_START_MS:
        # Still ok if within non-OOS, but keep to registered development window.
        start_ms = DEV_START_MS

    cache_dir = root / "artifacts" / "readiness" / "immutable" / "v15_c_real_development_research_campaign" / "market_cache"
    syms = [s.upper() for s in symbols]
    try:
        datasets: list[MarketDataset] = fetch_or_load_bundle(
            symbols=syms,
            interval=interval,
            start_ms=start_ms,
            end_ms=end_ms,
            cache_dir=cache_dir,
            use_network=use_network,
            max_pages=120,
        )
        bars_by_symbol: dict[str, list[DevelopmentBar]] = {}
        prov_syms: dict[str, Any] = {}
        for ds in datasets:
            if ds.classification != "REAL_HISTORICAL_MARKET_DATA":
                raise RuntimeError(f"dataset_not_real:{ds.symbol}:{ds.classification}")
            if ds.record_count < 64:
                raise RuntimeError(f"insufficient_bars:{ds.symbol}:{ds.record_count}")
            # Funding / OI — best effort; missing does not invent zeros as features,
            # but panel still loads (mechanisms requiring them become DATA_BLOCKED).
            fund_pts: list[dict[str, Any]] = []
            oi_pts: list[dict[str, Any]] = []
            fund_status = "UNAVAILABLE"
            oi_status = "UNAVAILABLE"
            if use_network:
                try:
                    fund = fetch_funding_history(symbol=ds.symbol, start_ms=start_ms, end_ms=end_ms)
                    fund_pts = list(fund.points)
                    fund_status = fund.supported_status
                except Exception:  # noqa: BLE001 — degrade to unavailable
                    fund_pts = []
                    fund_status = "FETCH_FAILED"
                try:
                    oi = fetch_open_interest(symbol=ds.symbol, start_ms=start_ms, end_ms=end_ms)
                    oi_pts = list(oi.points)
                    oi_status = oi.supported_status
                except Exception:  # noqa: BLE001
                    oi_pts = []
                    oi_status = "FETCH_FAILED"
            bars_by_symbol[ds.symbol] = _align_series(
                list(ds.candles), fund_pts, oi_pts, symbol=ds.symbol
            )
            prov_syms[ds.symbol] = {
                **ds.provenance(),
                "funding_status": fund_status,
                "funding_points": len(fund_pts),
                "oi_status": oi_status,
                "oi_points": len(oi_pts),
            }
        panel = DevelopmentPanel(
            classification="REAL_HISTORICAL_DEVELOPMENT",
            development_interval_id=DEVELOPMENT_INTERVAL_ID,
            start_ms=start_ms,
            end_ms=end_ms,
            interval=interval,
            symbols=syms,
            bars_by_symbol=bars_by_symbol,
            provenance={
                "data_lineage": "REAL_HISTORICAL_DEVELOPMENT",
                "fixture_synthetic": False,
                "never_call_fixture_real": True,
                "symbols": prov_syms,
                "oos_consumed": False,
                "development_interval_id": DEVELOPMENT_INTERVAL_ID,
                "cache_dir": str(cache_dir).replace("\\", "/"),
            },
            oos_consumed=False,
            fixture_used=False,
        )
        return panel
    except Exception as exc:  # noqa: BLE001
        if not allow_fixture_fallback:
            raise
        panel = _fixture_panel(
            symbols=syms, start_ms=start_ms, end_ms=end_ms, interval=interval
        )
        panel.provenance["fallback_reason"] = f"{type(exc).__name__}:{exc}"
        return panel


def panel_digest(panel: DevelopmentPanel) -> str:
    blob = {
        "classification": panel.classification,
        "symbols": panel.symbols,
        "counts": {s: len(panel.bars_by_symbol.get(s) or []) for s in panel.symbols},
        "first_last": {
            s: (
                (panel.bars_by_symbol[s][0].ts_ms, panel.bars_by_symbol[s][0].close),
                (panel.bars_by_symbol[s][-1].ts_ms, panel.bars_by_symbol[s][-1].close),
            )
            if panel.bars_by_symbol.get(s)
            else None
            for s in panel.symbols
        },
    }
    return hashlib.sha256(
        json.dumps(blob, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def regime_label(mid_return: float, realized_vol: float) -> str:
    if realized_vol > 0.012:
        return "STRESS"
    if abs(mid_return) > 0.003:
        return "TREND"
    return "RANGE"

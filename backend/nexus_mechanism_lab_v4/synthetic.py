"""Synthetic development-only fixtures for Mechanism Lab V4 — never reserved OOS."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from backend.nexus_mechanism_lab_v4.constants import DEVELOPMENT_INTERVAL_ID, RANDOM_SEED


@dataclass(frozen=True, slots=True)
class SynthBar:
    ts_ms: int
    exchange_ts_ms: int
    receive_ts_ms: int
    mid: float
    mid_return: float
    spread_bps: float
    ofi_top: float
    ofi_cum: float
    aggression_ratio: float
    aggression_persistence: float
    aggression_ratio_lag: float
    aggression_side: float
    aggression_side_lag: float
    net_flow: float
    net_flow_lag: float
    absorption_score: float
    liquidation_intensity: float
    liquidation_intensity_lag: float
    depth_gap: float
    depth_withdrawal: float
    funding_z: float
    basis_bps: float
    basis_bps_lag: float
    oi_change: float
    vol_z: float
    range_compression: float
    range_compression_lag: float
    range_expansion: float
    spread_shock: float
    impact_bps: float
    impact_bid_bps: float
    impact_ask_bps: float
    impact_asymmetry: float
    lead_lag_score: float
    lead_return: float
    lag_return: float
    cross_corr: float
    pair_residual: float
    zscore_return: float
    volume: float
    volume_price_div: float
    volume_drought: float
    level_refresh_count: float
    distance_to_level_bps: float
    range_high_break: float
    breakout_fail_flag: float
    large_print_flag: float
    liq_side: float
    tod_bucket: str  # ASIA_OPEN | US_OPEN | FUNDING_SETTLEMENT | OTHER
    regime_label: str  # RANGE | TREND | STRESS
    regime_label_lag: str
    data_quality_ok: bool


def _xorshift(seed: int) -> int:
    x = seed & 0xFFFFFFFF
    x ^= (x << 13) & 0xFFFFFFFF
    x ^= (x >> 17) & 0xFFFFFFFF
    x ^= (x << 5) & 0xFFFFFFFF
    return x & 0xFFFFFFFF


def _unit(seed: int) -> tuple[float, int]:
    s = _xorshift(seed)
    return (s / 0xFFFFFFFF), s


def generate_synthetic_series(
    *,
    n_bars: int = 520,
    seed: int = RANDOM_SEED,
    as_of_ms: int = 1_700_000_000_000,
    inject_dq_gap: bool = True,
) -> list[SynthBar]:
    bars: list[SynthBar] = []
    mid = 50_000.0
    ofi_cum = 0.0
    state = seed ^ 0xC0FFEE01
    prev_aggr = 0.5
    prev_side = 1.0
    prev_net = 0.0
    prev_liq = 0.0
    prev_basis = 0.0
    prev_compress = 0.5
    prev_regime = "RANGE"
    for i in range(n_bars):
        u, state = _unit(state + i * 17 + 3)
        v, state = _unit(state + 91)
        w, state = _unit(state + 113)
        shock, state = _unit(state + 131)
        ret = (u - 0.5) * 0.004 + (v - 0.5) * 0.001
        mid = max(1.0, mid * (1.0 + ret))
        vol_z = (ret / 0.002) if abs(ret) > 1e-12 else 0.0
        regime = "RANGE"
        if abs(vol_z) > 1.8:
            regime = "STRESS"
        elif abs(vol_z) > 0.9:
            regime = "TREND"
        dq_ok = True
        if inject_dq_gap and 210 <= i < 218:
            dq_ok = False
        ofi = (u - 0.5) * 2.0
        ofi_cum += ofi
        aggr = 0.3 + 0.7 * v
        side = 1.0 if aggr >= 0.5 else -1.0
        net = (u - 0.5) * 1.5
        liq = max(0.0, abs(vol_z) - 1.2) * (1.0 + shock)
        basis = (v - 0.5) * 40.0
        compress = max(0.0, 1.0 - abs(vol_z))
        hour = (i // 60) % 24
        if 0 <= hour < 3:
            tod = "ASIA_OPEN"
        elif 13 <= hour < 16:
            tod = "US_OPEN"
        elif hour in {0, 8, 16}:
            tod = "FUNDING_SETTLEMENT"
        else:
            tod = "OTHER"
        impact = 0.5 + 3.0 * shock + (5.0 if regime == "STRESS" else 0.0)
        impact_bid = impact * (0.8 + 0.4 * u)
        impact_ask = impact * (0.8 + 0.4 * v)
        volume = 0.5 + 2.0 * w + (3.0 if abs(vol_z) > 1.0 else 0.0)
        ex_ts = as_of_ms + i * 60_000
        recv = ex_ts + int(20 + 40 * shock)
        bars.append(
            SynthBar(
                ts_ms=ex_ts,
                exchange_ts_ms=ex_ts,
                receive_ts_ms=recv,
                mid=mid,
                mid_return=ret,
                spread_bps=1.0 + 8.0 * w + (12.0 if regime == "STRESS" else 0.0),
                ofi_top=ofi,
                ofi_cum=ofi_cum,
                aggression_ratio=aggr,
                aggression_persistence=0.2 + 0.8 * ((aggr + prev_aggr) / 2.0),
                aggression_ratio_lag=prev_aggr,
                aggression_side=side,
                aggression_side_lag=prev_side,
                net_flow=net,
                net_flow_lag=prev_net,
                absorption_score=max(0.0, 0.55 - abs(ret) * 40.0),
                liquidation_intensity=liq,
                liquidation_intensity_lag=prev_liq,
                depth_gap=0.1 + 1.5 * shock,
                depth_withdrawal=max(0.0, shock - 0.75) * 2.0,
                funding_z=(u - 0.5) * 3.0,
                basis_bps=basis,
                basis_bps_lag=prev_basis,
                oi_change=(w - 0.5) * 0.05,
                vol_z=vol_z,
                range_compression=compress,
                range_compression_lag=prev_compress,
                range_expansion=max(0.0, abs(vol_z)),
                spread_shock=max(0.0, shock - 0.85) * 20.0,
                impact_bps=impact,
                impact_bid_bps=impact_bid,
                impact_ask_bps=impact_ask,
                impact_asymmetry=impact_bid - impact_ask,
                lead_lag_score=(u - 0.5) * 1.5,
                lead_return=(u - 0.5) * 0.003,
                lag_return=ret,
                cross_corr=0.4 + 0.5 * v,
                pair_residual=(u - v) * 0.002,
                zscore_return=vol_z,
                volume=volume,
                volume_price_div=(volume * (-1.0 if ret < 0 else 1.0)) - 1.0,
                volume_drought=1.0 if volume < 0.9 else 0.0,
                level_refresh_count=max(0.0, (0.6 - abs(ret) * 30.0)) * 5.0,
                distance_to_level_bps=abs(ret) * 10_000.0,
                range_high_break=1.0 if ret > 0.002 and compress < 0.4 else 0.0,
                breakout_fail_flag=1.0 if ret < -0.001 and prev_compress < 0.35 else 0.0,
                large_print_flag=1.0 if shock > 0.9 else 0.0,
                liq_side=1.0 if ret < 0 else -1.0,
                tod_bucket=tod,
                regime_label=regime,
                regime_label_lag=prev_regime,
                data_quality_ok=dq_ok,
            )
        )
        prev_aggr = aggr
        prev_side = side
        prev_net = net
        prev_liq = liq
        prev_basis = basis
        prev_compress = compress
        prev_regime = regime
    return bars


def series_lineage(bars: list[SynthBar], *, seed: int = RANDOM_SEED) -> dict[str, Any]:
    payload = "|".join(
        f"{b.exchange_ts_ms}:{b.mid:.8f}:{b.regime_label}:{int(b.data_quality_ok)}" for b in bars
    )
    digest = hashlib.sha256(f"{DEVELOPMENT_INTERVAL_ID}|{seed}|{payload}".encode()).hexdigest()
    return {
        "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
        "development_interval_id": DEVELOPMENT_INTERVAL_ID,
        "reserved_oos_consumed": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "bar_count": len(bars),
        "series_digest": digest,
        "seed": seed,
    }


def feature_value(bar: SynthBar, name: str) -> float | str:
    if not hasattr(bar, name):
        raise KeyError(f"unknown_feature:{name}")
    return getattr(bar, name)

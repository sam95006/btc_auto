"""Synthetic development-only market fixtures — never reserved OOS."""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

from backend.nexus_strategy_discovery_factory_v3.constants import (
    DEVELOPMENT_INTERVAL_ID,
    RANDOM_SEED,
)


@dataclass(frozen=True, slots=True)
class SynthBar:
    ts_ms: int
    mid: float
    spread_bps: float
    ofi: float
    aggression: float
    aggression_persistence: float
    absorption: float
    liquidation_intensity: float
    depth_gap: float
    depth_withdrawal: float
    funding_z: float
    basis_bps: float
    oi_change: float
    vol_z: float
    range_compression: float
    spread_shock: float
    impact_bps: float
    lead_lag_score: float
    cross_corr: float
    zscore_return: float
    regime_label: str  # RANGE | TREND | STRESS
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
    n_bars: int = 480,
    seed: int = RANDOM_SEED,
    as_of_ms: int = 1_700_000_000_000,
    inject_dq_gap: bool = True,
) -> list[SynthBar]:
    """Deterministic synthetic development series (non-OOS, non-Demo)."""
    bars: list[SynthBar] = []
    mid = 50_000.0
    state = seed ^ 0xA5A5A5A5
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
        if inject_dq_gap and 200 <= i < 208:
            dq_ok = False
        bars.append(
            SynthBar(
                ts_ms=as_of_ms + i * 60_000,
                mid=mid,
                spread_bps=1.0 + 8.0 * w + (12.0 if regime == "STRESS" else 0.0),
                ofi=(u - 0.5) * 2.0,
                aggression=0.3 + 0.7 * v,
                aggression_persistence=0.2 + 0.8 * ((u + v) / 2.0),
                absorption=max(0.0, (0.55 - abs(ret) * 40.0)),
                liquidation_intensity=max(0.0, abs(vol_z) - 1.2) * (1.0 + shock),
                depth_gap=0.1 + 1.5 * shock,
                depth_withdrawal=max(0.0, shock - 0.75) * 2.0,
                funding_z=(u - 0.5) * 3.0,
                basis_bps=(v - 0.5) * 40.0,
                oi_change=(w - 0.5) * 0.05,
                vol_z=vol_z,
                range_compression=max(0.0, 1.0 - abs(vol_z)),
                spread_shock=max(0.0, shock - 0.85) * 20.0,
                impact_bps=0.5 + 3.0 * shock + (5.0 if regime == "STRESS" else 0.0),
                lead_lag_score=(u - 0.5) * 1.5,
                cross_corr=0.4 + 0.5 * v,
                zscore_return=vol_z,
                regime_label=regime,
                data_quality_ok=dq_ok,
            )
        )
    return bars


def series_lineage(bars: list[SynthBar], *, seed: int = RANDOM_SEED) -> dict[str, Any]:
    payload = "|".join(f"{b.ts_ms}:{b.mid:.8f}:{b.regime_label}:{int(b.data_quality_ok)}" for b in bars)
    digest = hashlib.sha256(f"{DEVELOPMENT_INTERVAL_ID}|{seed}|{payload}".encode()).hexdigest()
    return {
        "data_lineage": "SYNTHETIC_DEVELOPMENT_FIXTURE",
        "development_interval_id": DEVELOPMENT_INTERVAL_ID,
        "reserved_oos_consumed": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "seed": seed,
        "bar_count": len(bars),
        "series_checksum": digest,
        "point_in_time_proof": {
            "as_of_ms": bars[0].ts_ms if bars else None,
            "last_bar_ms": bars[-1].ts_ms if bars else None,
            "lookahead_forbidden": True,
            "future_bar_reference_count": 0,
            "pit_join_rule": "signal_uses_bars_strictly_before_entry_only",
        },
    }


def feature_snapshot(bar: SynthBar) -> dict[str, Any]:
    return {
        "order_flow_imbalance": bar.ofi,
        "mid_return": 0.0,
        "spread_bps": bar.spread_bps,
        "liquidation_intensity": bar.liquidation_intensity,
        "aggression_ratio": bar.aggression,
        "depth_gap": bar.depth_gap,
        "absorption_score": bar.absorption,
        "aggression_persistence": bar.aggression_persistence,
        "funding_z": bar.funding_z,
        "basis_bps": bar.basis_bps,
        "oi_change": bar.oi_change,
        "vol_z": bar.vol_z,
        "range_compression": bar.range_compression,
        "depth_withdrawal": bar.depth_withdrawal,
        "impact_bps": bar.impact_bps,
        "spread_shock": bar.spread_shock,
        "lead_lag_score": bar.lead_lag_score,
        "cross_corr": bar.cross_corr,
        "regime_label": bar.regime_label,
        "zscore_return": bar.zscore_return,
    }


def signal_for_family(family_id: str, bar: SynthBar, prev: SynthBar | None) -> float | None:
    """Return signed signal in [-1, 1] or None if no event."""
    if not bar.data_quality_ok:
        return None
    if family_id == "ORDER_FLOW_IMBALANCE":
        if abs(bar.ofi) < 0.55:
            return None
        return max(-1.0, min(1.0, bar.ofi))
    if family_id == "LIQUIDATION_CASCADE":
        # Event-like but frequent enough on synthetic stress bars for cost study.
        if abs(bar.vol_z) < 0.7 and bar.liquidation_intensity < 0.05:
            return None
        return 1.0 if bar.ofi >= 0 else -1.0
    if family_id == "ABSORPTION":
        if bar.absorption < 0.25 or bar.aggression < 0.45:
            return None
        # Absorb aggressors → fade
        return -1.0 if bar.aggression > 0.55 else 1.0
    if family_id == "AGGRESSION_PERSISTENCE":
        if bar.aggression_persistence < 0.65:
            return None
        return 1.0 if bar.aggression >= 0.5 else -1.0
    if family_id == "FUNDING_BASIS_DISLOCATION":
        score = 0.6 * bar.funding_z + 0.4 * (bar.basis_bps / 20.0)
        if abs(score) < 0.55:
            return None
        return max(-1.0, min(1.0, -score / 3.0))  # fade dislocation
    if family_id == "VOL_EXPANSION_COMPRESSION":
        if abs(bar.vol_z) < 0.8 and bar.range_compression < 0.55:
            return None
        if bar.vol_z > 1.0:
            return 1.0 if (prev and bar.mid > prev.mid) else -1.0
        return -math.copysign(1.0, bar.zscore_return) if abs(bar.zscore_return) > 0.5 else None
    if family_id == "LIQUIDITY_WITHDRAWAL":
        if bar.depth_withdrawal < 0.4:
            return None
        return -1.0 if bar.ofi > 0 else 1.0
    if family_id == "SPREAD_SHOCK":
        if bar.spread_shock < 2.0:
            return None
        return -1.0 if bar.ofi > 0 else 1.0
    if family_id == "CROSS_ASSET_LEAD_LAG":
        if abs(bar.lead_lag_score) < 0.45 or bar.cross_corr < 0.55:
            return None
        return max(-1.0, min(1.0, bar.lead_lag_score))
    if family_id == "REGIME_MEAN_REVERSION":
        if bar.regime_label != "RANGE" or abs(bar.zscore_return) < 0.9:
            return None
        return -math.copysign(1.0, bar.zscore_return)
    return None

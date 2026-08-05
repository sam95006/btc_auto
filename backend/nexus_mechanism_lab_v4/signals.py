"""Deterministic per-mechanism signal implementations — not cosmetic clones."""
from __future__ import annotations

from backend.nexus_mechanism_lab_v4.catalog import MechanismSpec
from backend.nexus_mechanism_lab_v4.synthetic import SynthBar


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def signal_for(spec: MechanismSpec, bar: SynthBar, prev: SynthBar) -> int | None:
    """Return +1 / -1 / None. Uses only bar/prev (PIT: no future bars)."""
    kind = spec.signal_kind

    if kind == "signed_threshold":
        if abs(bar.ofi_top) < 0.55:
            return None
        return _sign(bar.ofi_top)

    if kind == "divergence":
        if _sign(bar.ofi_cum) == 0 or _sign(bar.mid_return) == 0:
            return None
        if _sign(bar.ofi_cum) == _sign(bar.mid_return):
            return None
        return _sign(bar.ofi_cum)

    if kind == "exhaustion_fade":
        if abs(bar.ofi_top) < 0.95 or bar.aggression_ratio < 0.7:
            return None
        return -_sign(bar.ofi_top)

    if kind == "persistence_continue":
        if bar.aggression_persistence < 0.65:
            return None
        return 1 if bar.aggression_ratio >= 0.5 else -1

    if kind == "persistence_decay_fade":
        if prev.aggression_persistence < 0.7 or bar.aggression_persistence > 0.55:
            return None
        prior = 1 if prev.aggression_ratio_lag >= 0.5 else -1
        return -prior

    if kind == "side_flip":
        if bar.aggression_side == prev.aggression_side:
            return None
        if abs(bar.ofi_top) < 0.4:
            return None
        return int(bar.aggression_side)

    if kind == "net_flow_sign_change":
        if _sign(bar.net_flow) == 0 or _sign(prev.net_flow) == 0:
            return None
        if _sign(bar.net_flow) == _sign(prev.net_flow):
            return None
        return -_sign(prev.net_flow)

    if kind == "liq_intensity_continue":
        if bar.liquidation_intensity < 0.35 or bar.depth_gap < 0.8:
            return None
        return int(bar.liq_side)

    if kind == "liq_acceleration":
        accel = bar.liquidation_intensity - prev.liquidation_intensity
        if accel < 0.2:
            return None
        return 1 if bar.aggression_ratio >= 0.5 else -1

    if kind == "post_liq_snapback":
        if prev.liquidation_intensity < 0.5 or bar.liquidation_intensity > 0.25:
            return None
        return -int(prev.liq_side) if prev.liq_side != 0 else -_sign(prev.mid_return)

    if kind == "post_liq_drought":
        if prev.liquidation_intensity < 0.4 or bar.volume > 1.2:
            return None
        return -_sign(prev.mid_return) if prev.mid_return != 0 else None

    if kind == "absorption_fade":
        if bar.absorption_score < 0.35 or abs(bar.mid_return) > 0.0015:
            return None
        return - (1 if bar.aggression_ratio >= 0.5 else -1)

    if kind == "iceberg_level_fade":
        if bar.level_refresh_count < 2.0 or bar.distance_to_level_bps > 8.0:
            return None
        return - (1 if bar.aggression_ratio >= 0.5 else -1)

    if kind == "depth_withdrawal_adverse":
        if bar.depth_withdrawal < 0.5:
            return None
        return -_sign(bar.mid_return) if bar.mid_return != 0 else None

    if kind == "thin_book_gap":
        if bar.depth_gap < 1.0 or bar.spread_bps < 6.0:
            return None
        return -_sign(bar.mid_return) if bar.mid_return != 0 else None

    if kind == "spread_shock_fade":
        if bar.spread_shock < 2.0:
            return None
        return -_sign(bar.mid_return) if bar.mid_return != 0 else None

    if kind == "spread_shock_stress_continue":
        if bar.spread_shock < 2.0 or abs(bar.vol_z) < 1.0:
            return None
        return 1 if bar.aggression_ratio >= 0.5 else -1

    if kind == "vol_expand_continue":
        if abs(bar.vol_z) < 1.2 or bar.mid_return == 0:
            return None
        return _sign(bar.mid_return)

    if kind == "vol_expand_reopen_fade":
        if abs(bar.vol_z) < 1.0 or prev.range_compression < 0.6:
            return None
        if bar.regime_label == "TREND":
            return None
        return -_sign(bar.zscore_return) if bar.zscore_return != 0 else None

    if kind == "compression_breakout":
        if prev.range_compression < 0.7 or abs(bar.mid_return) < 0.0015:
            return None
        return _sign(bar.mid_return)

    if kind == "compression_fail_fade":
        if bar.breakout_fail_flag < 0.5 or prev.range_compression < 0.55:
            return None
        return -_sign(bar.mid_return) if bar.mid_return != 0 else 1

    if kind == "funding_extreme_fade":
        if abs(bar.funding_z) < 1.4:
            return None
        return -_sign(bar.funding_z)

    if kind == "funding_squeeze_continue":
        if abs(bar.funding_z) < 1.4 or bar.oi_change <= 0:
            return None
        # Continue against crowded side: positive funding => crowded long => short
        return -_sign(bar.funding_z)

    if kind == "basis_fade":
        if abs(bar.basis_bps) < 12.0:
            return None
        return -_sign(bar.basis_bps)

    if kind == "basis_shock_momentum":
        shock = bar.basis_bps - prev.basis_bps
        if abs(shock) < 8.0 or bar.aggression_ratio < 0.55:
            return None
        return _sign(shock)

    if kind == "lead_lag_transfer":
        if abs(bar.lead_lag_score) < 0.45:
            return None
        return _sign(bar.lead_return) if bar.lead_return != 0 else _sign(bar.lead_lag_score)

    if kind == "corr_breakdown_rv":
        if bar.cross_corr > 0.55 or abs(bar.pair_residual) < 0.0004:
            return None
        return -_sign(bar.pair_residual)

    if kind == "regime_range_mr":
        if bar.regime_label != "RANGE" or abs(bar.zscore_return) < 0.8:
            return None
        return -_sign(bar.zscore_return)

    if kind == "regime_transition_shutdown":
        if not (prev.regime_label == "RANGE" and bar.regime_label == "TREND"):
            return None
        # Control overlay: emit flat signal marker via None for entries; lab treats
        # this as forced-flat event count, not a trade direction.
        return None

    if kind == "range_high_breakout":
        if bar.range_high_break < 0.5 or bar.volume < 1.2:
            return None
        return 1

    if kind == "vol_confirmed_breakout":
        if bar.range_high_break < 0.5 or abs(bar.vol_z) < 1.0:
            return None
        return _sign(bar.mid_return) if bar.mid_return != 0 else 1

    if kind == "failed_break_snapback":
        if bar.breakout_fail_flag < 0.5:
            return None
        return -_sign(bar.mid_return) if bar.mid_return != 0 else 1

    if kind == "failed_break_absorption":
        if bar.breakout_fail_flag < 0.5 or bar.absorption_score < 0.3:
            return None
        return - (1 if bar.aggression_ratio >= 0.5 else -1)

    if kind == "vp_bearish_div_fade":
        if bar.volume < 1.5 or bar.mid_return >= 0:
            return None
        return 1  # fade sell climax -> long

    if kind == "vp_drought_fade":
        if bar.volume_drought < 0.5 or bar.mid_return <= 0:
            return None
        return -1

    if kind == "oi_surge_stall":
        if bar.oi_change < 0.015 or abs(bar.mid_return) > 0.0008:
            return None
        return -_sign(bar.funding_z) if bar.funding_z != 0 else None

    if kind == "oi_flush_continue":
        if bar.oi_change > -0.015 or bar.liquidation_intensity < 0.3:
            return None
        return 1 if bar.aggression_ratio >= 0.5 else -1

    if kind == "impact_asym_fade":
        if abs(bar.impact_asymmetry) < 1.5:
            return None
        return -_sign(bar.impact_asymmetry)

    if kind == "impact_persist_continue":
        if bar.large_print_flag < 0.5 or bar.impact_bps < 3.0:
            return None
        return _sign(bar.mid_return) if bar.mid_return != 0 else 1

    if kind == "tod_asia_thin":
        if bar.tod_bucket != "ASIA_OPEN" or bar.depth_gap < 0.9:
            return None
        return -_sign(bar.mid_return) if bar.mid_return != 0 else None

    if kind == "tod_us_vol":
        if bar.tod_bucket != "US_OPEN" or abs(bar.vol_z) < 0.9:
            return None
        return _sign(bar.mid_return) if bar.mid_return != 0 else None

    if kind == "tod_funding_settlement":
        if bar.tod_bucket != "FUNDING_SETTLEMENT" or abs(bar.funding_z) < 0.8:
            return None
        return -_sign(bar.funding_z)

    raise AssertionError(f"unhandled_signal_kind:{kind}")

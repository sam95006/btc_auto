"""Semantically distinct mechanism family definitions — not cosmetic clones."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.nexus_strategy_discovery_factory_v3.constants import MECHANISM_FAMILIES


@dataclass(frozen=True, slots=True)
class MechanismFamilySpec:
    family_id: str
    semantic_mechanism_id: str
    economic_prior: str
    required_features: tuple[str, ...]
    signal_horizon_bars: int
    holding_bars: int
    # Scenario profile for synthetic generator (drives distinct outcomes).
    profile: str  # one of: signal_only | cost_destroyed | thin_sample | regime_fragile | dq_block | promising | reject


FAMILY_SPECS: tuple[MechanismFamilySpec, ...] = (
    MechanismFamilySpec(
        family_id="ORDER_FLOW_IMBALANCE",
        semantic_mechanism_id="MECH_OFI_TOPBOOK_PRESSURE_V1",
        economic_prior=(
            "Top-of-book / near-touch imbalance proxies short-horizon supply-demand "
            "pressure; edge is microstructure-local and cost-sensitive."
        ),
        required_features=("order_flow_imbalance", "mid_return", "spread_bps"),
        signal_horizon_bars=4,
        holding_bars=8,
        profile="promising",
    ),
    MechanismFamilySpec(
        family_id="LIQUIDATION_CASCADE",
        semantic_mechanism_id="MECH_LIQ_CASCADE_RESPONSE_V1",
        economic_prior=(
            "Forced liquidation bursts create liquidity voids and short-horizon "
            "continuation or snapback; requires event timing integrity."
        ),
        required_features=("liquidation_intensity", "aggression_ratio", "depth_gap"),
        signal_horizon_bars=2,
        holding_bars=6,
        profile="cost_destroyed",
    ),
    MechanismFamilySpec(
        family_id="ABSORPTION",
        semantic_mechanism_id="MECH_ABSORPTION_PASSIVE_DEFENSE_V1",
        economic_prior=(
            "Large passive liquidity absorbs aggressive flow without price progress; "
            "subsequent reversal is the hypothesized response."
        ),
        required_features=("absorption_score", "aggression_ratio", "mid_return"),
        signal_horizon_bars=6,
        holding_bars=12,
        profile="signal_only",
    ),
    MechanismFamilySpec(
        family_id="AGGRESSION_PERSISTENCE",
        semantic_mechanism_id="MECH_AGGRESSION_PERSISTENCE_V1",
        economic_prior=(
            "Sustained aggressor dominance across consecutive windows implies "
            "initiative continuation until liquidity replenishes."
        ),
        required_features=("aggression_persistence", "aggression_ratio", "vol_z"),
        signal_horizon_bars=8,
        holding_bars=10,
        profile="promising",
    ),
    MechanismFamilySpec(
        family_id="FUNDING_BASIS_DISLOCATION",
        semantic_mechanism_id="MECH_FUNDING_BASIS_DISLOCATION_V1",
        economic_prior=(
            "Funding and basis dislocations encode crowding / carry stress; "
            "mean-reversion of dislocation is hypothesized after extremes."
        ),
        required_features=("funding_z", "basis_bps", "oi_change"),
        signal_horizon_bars=16,
        holding_bars=32,
        profile="cost_destroyed",
    ),
    MechanismFamilySpec(
        family_id="VOL_EXPANSION_COMPRESSION",
        semantic_mechanism_id="MECH_VOL_EXPAND_COMPRESS_V1",
        economic_prior=(
            "Volatility regime transitions (expansion vs compression) alter "
            "expected range; breakout/mean-revert conditioned on vol state."
        ),
        required_features=("vol_z", "range_compression", "mid_return"),
        signal_horizon_bars=12,
        holding_bars=16,
        profile="regime_fragile",
    ),
    MechanismFamilySpec(
        family_id="LIQUIDITY_WITHDRAWAL",
        semantic_mechanism_id="MECH_LIQUIDITY_WITHDRAWAL_V1",
        economic_prior=(
            "Sudden visible-depth withdrawal raises impact and gap risk; "
            "short-horizon adverse selection dominates unless carefully gated."
        ),
        required_features=("depth_withdrawal", "spread_bps", "impact_bps"),
        signal_horizon_bars=3,
        holding_bars=5,
        profile="dq_block",
    ),
    MechanismFamilySpec(
        family_id="SPREAD_SHOCK",
        semantic_mechanism_id="MECH_SPREAD_SHOCK_V1",
        economic_prior=(
            "Transient spread shocks mark liquidity stress; fade after "
            "normalization is hypothesized but often cost-dominated."
        ),
        required_features=("spread_shock", "spread_bps", "mid_return"),
        signal_horizon_bars=4,
        holding_bars=8,
        profile="thin_sample",
    ),
    MechanismFamilySpec(
        family_id="CROSS_ASSET_LEAD_LAG",
        semantic_mechanism_id="MECH_CROSS_ASSET_LEAD_LAG_V1",
        economic_prior=(
            "Lead-lag between related instruments (e.g. BTC→alt) may transfer "
            "short-horizon information; PIT alignment is mandatory."
        ),
        required_features=("lead_lag_score", "cross_corr", "mid_return"),
        signal_horizon_bars=5,
        holding_bars=10,
        profile="signal_only",
    ),
    MechanismFamilySpec(
        family_id="REGIME_MEAN_REVERSION",
        semantic_mechanism_id="MECH_REGIME_COND_MEAN_REVERSION_V1",
        economic_prior=(
            "Range regimes favor mean reversion; trend regimes destroy it. "
            "Regime-conditioned evaluation is required to avoid false discovery."
        ),
        required_features=("regime_label", "zscore_return", "vol_z"),
        signal_horizon_bars=10,
        holding_bars=14,
        profile="reject",
    ),
)


def assert_families_distinct() -> None:
    ids = [s.family_id for s in FAMILY_SPECS]
    mechs = [s.semantic_mechanism_id for s in FAMILY_SPECS]
    if len(ids) != len(set(ids)):
        raise AssertionError("duplicate_family_id")
    if len(mechs) != len(set(mechs)):
        raise AssertionError("duplicate_semantic_mechanism_id")
    if set(ids) != set(MECHANISM_FAMILIES):
        raise AssertionError("family_set_mismatch_vs_constants")
    priors = [s.economic_prior for s in FAMILY_SPECS]
    if len(priors) != len(set(priors)):
        raise AssertionError("cosmetic_clone_priors_detected")


def family_catalog() -> list[dict[str, Any]]:
    assert_families_distinct()
    return [
        {
            "family_id": s.family_id,
            "semantic_mechanism_id": s.semantic_mechanism_id,
            "economic_prior": s.economic_prior,
            "required_features": list(s.required_features),
            "signal_horizon_bars": s.signal_horizon_bars,
            "holding_bars": s.holding_bars,
            "profile": s.profile,
        }
        for s in FAMILY_SPECS
    ]

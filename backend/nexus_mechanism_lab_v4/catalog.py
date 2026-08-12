"""Mechanism catalog — >=40 semantically distinct mechanisms (not param clones)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from backend.nexus_mechanism_lab_v4.constants import (
    MECHANISM_FAMILIES,
    MIN_MECHANISM_COUNT,
    REQUIRED_MECHANISM_FIELDS,
)


@dataclass(frozen=True, slots=True)
class MechanismSpec:
    mechanism_id: str
    family: str
    economic_rationale: str
    required_data: tuple[str, ...]
    pit_semantics: str
    entry_hypothesis: str
    exit_hypothesis: str
    failure_hypothesis: str
    cost_sensitivity: str
    capacity_assumptions: str
    invalidating_conditions: tuple[str, ...]
    # Deterministic signal contract (semantic, not cosmetic threshold clones).
    signal_kind: str
    primary_feature: str
    secondary_feature: str
    horizon_bars: int
    hold_bars: int
    direction_mode: str  # long_short | long_only | short_only | fade | continuation


def _pit(rule: str) -> str:
    return (
        "Only bars with exchange_ts_ms <= as_of_ms AND receive_ts_ms <= as_of_ms; "
        f"signal uses strictly contemporaneous or lagged features: {rule}. "
        "No future mid/feature peeking for signal formation."
    )


SPECS: tuple[MechanismSpec, ...] = (
    # --- ORDER_FLOW_IMBALANCE (3) ---
    MechanismSpec(
        mechanism_id="MECH_OFI_TOPBOOK_PRESSURE_CONTINUATION_V4",
        family="ORDER_FLOW_IMBALANCE",
        economic_rationale=(
            "Near-touch order-flow imbalance proxies short-horizon supply/demand pressure; "
            "continuation is hypothesized while replenishment lags."
        ),
        required_data=("ofi_top", "mid", "spread_bps", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("ofi_top[t] and mid[t] only"),
        entry_hypothesis="Enter with sign(ofi_top) when |ofi_top| exceeds development threshold.",
        exit_hypothesis="Exit after hold_bars or when ofi_top sign flips.",
        failure_hypothesis="Fails when passive replenishment absorbs imbalance without mid move.",
        cost_sensitivity="High — spread and impact dominate sub-minute holds.",
        capacity_assumptions="Synthetic micro notional only; top-book capacity saturates quickly.",
        invalidating_conditions=("book_snapshot_stale", "spread_shock_active", "data_quality_gap"),
        signal_kind="signed_threshold",
        primary_feature="ofi_top",
        secondary_feature="spread_bps",
        horizon_bars=3,
        hold_bars=6,
        direction_mode="continuation",
    ),
    MechanismSpec(
        mechanism_id="MECH_OFI_CUMULATIVE_DIVERGENCE_V4",
        family="ORDER_FLOW_IMBALANCE",
        economic_rationale=(
            "Cumulative OFI diverging from mid path implies hidden inventory pressure; "
            "subsequent mid catch-up is the research hypothesis."
        ),
        required_data=("ofi_cum", "mid_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("ofi_cum[t] vs mid_return over lagged window ending at t"),
        entry_hypothesis="Enter toward OFI when cum OFI and mid_return disagree in sign.",
        exit_hypothesis="Exit when divergence gap closes or hold_bars elapse.",
        failure_hypothesis="Fails when mid is driven by cross-venue prints not in local book.",
        cost_sensitivity="Medium — requires enough displacement to clear fees.",
        capacity_assumptions="Assumes local book represents actionable liquidity.",
        invalidating_conditions=("cross_venue_gap", "clock_skew", "ofi_reset_event"),
        signal_kind="divergence",
        primary_feature="ofi_cum",
        secondary_feature="mid_return",
        horizon_bars=8,
        hold_bars=12,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_OFI_EXHAUSTION_AFTER_EXTREME_V4",
        family="ORDER_FLOW_IMBALANCE",
        economic_rationale=(
            "Extreme one-sided OFI often exhausts aggressive inventory; fade after "
            "extreme is a distinct exhaustion mechanism, not a threshold tweak."
        ),
        required_data=("ofi_top", "aggression_ratio", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("extreme ofi_top measured on completed bars <= t"),
        entry_hypothesis="Fade sign(ofi_top) after extreme percentile on rolling window.",
        exit_hypothesis="Exit on mean-reversion of ofi_top or hold_bars.",
        failure_hypothesis="Fails during cascade regimes where extremes persist.",
        cost_sensitivity="High — mistimed fades pay spread twice.",
        capacity_assumptions="Only thin synthetic size; extremes coincide with thin books.",
        invalidating_conditions=("liquidation_cascade_active", "regime_stress"),
        signal_kind="exhaustion_fade",
        primary_feature="ofi_top",
        secondary_feature="aggression_ratio",
        horizon_bars=5,
        hold_bars=8,
        direction_mode="fade",
    ),
    # --- AGGRESSION_PERSISTENCE (2) ---
    MechanismSpec(
        mechanism_id="MECH_AGGRESSION_PERSISTENCE_CONTINUATION_V4",
        family="AGGRESSION_PERSISTENCE",
        economic_rationale=(
            "Sustained aggressor dominance across consecutive windows implies initiative "
            "continuation until liquidity replenishes."
        ),
        required_data=("aggression_persistence", "aggression_ratio", "vol_z", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("aggression_persistence[t] from bars <= t"),
        entry_hypothesis="Enter with aggression sign when persistence stays elevated.",
        exit_hypothesis="Exit when persistence decays below baseline or hold_bars.",
        failure_hypothesis="Fails when persistence is spoofed by bursty cancel/replace.",
        cost_sensitivity="Medium-high; persistence windows often coincide with wider spreads.",
        capacity_assumptions="Assumes aggressor flow is not dominated by one large account.",
        invalidating_conditions=("cancel_replace_storm", "data_quality_gap"),
        signal_kind="persistence_continue",
        primary_feature="aggression_persistence",
        secondary_feature="aggression_ratio",
        horizon_bars=6,
        hold_bars=10,
        direction_mode="continuation",
    ),
    MechanismSpec(
        mechanism_id="MECH_AGGRESSION_PERSISTENCE_DECAY_FADE_V4",
        family="AGGRESSION_PERSISTENCE",
        economic_rationale=(
            "Decay of previously elevated aggression persistence marks initiative loss; "
            "fade of the prior aggressor side is hypothesized."
        ),
        required_data=("aggression_persistence", "aggression_ratio_lag", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("persistence[t] vs persistence[t-k]; no future decay peek"),
        entry_hypothesis="Fade prior aggressor when persistence drops after elevated stretch.",
        exit_hypothesis="Exit on re-acceleration of persistence or hold_bars.",
        failure_hypothesis="Fails when decay is a pause before second impulse.",
        cost_sensitivity="High — false fades in impulse trains destroy net.",
        capacity_assumptions="Synthetic research size only.",
        invalidating_conditions=("second_impulse_within_horizon", "regime_trend"),
        signal_kind="persistence_decay_fade",
        primary_feature="aggression_persistence",
        secondary_feature="aggression_ratio_lag",
        horizon_bars=7,
        hold_bars=9,
        direction_mode="fade",
    ),
    # --- FLOW_REVERSAL (2) ---
    MechanismSpec(
        mechanism_id="MECH_FLOW_REVERSAL_AGGRESSION_FLIP_V4",
        family="FLOW_REVERSAL",
        economic_rationale=(
            "Aggression-side flip after one-sided exhaustion encodes a flow reversal "
            "event distinct from simple OFI thresholds."
        ),
        required_data=("aggression_side", "aggression_side_lag", "ofi_top", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("side flip detected on completed bars <= t"),
        entry_hypothesis="Enter with new aggression side after flip following exhaustion.",
        exit_hypothesis="Exit if side flips again or hold_bars elapse.",
        failure_hypothesis="Fails on noisy side chatter without inventory transfer.",
        cost_sensitivity="High around flip moments (spread shock common).",
        capacity_assumptions="Assumes side classification is stable at bar close.",
        invalidating_conditions=("side_label_unstable", "spread_shock_active"),
        signal_kind="side_flip",
        primary_feature="aggression_side",
        secondary_feature="aggression_side_lag",
        horizon_bars=4,
        hold_bars=7,
        direction_mode="continuation",
    ),
    MechanismSpec(
        mechanism_id="MECH_FLOW_REVERSAL_NET_FLOW_SIGN_CHANGE_V4",
        family="FLOW_REVERSAL",
        economic_rationale=(
            "Net signed flow sign change after sustained imbalance hypothesizes "
            "mean-reverting inventory rebalancing."
        ),
        required_data=("net_flow", "net_flow_lag", "mid_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("net_flow sign change using lags ending at t"),
        entry_hypothesis="Enter opposite prior net_flow after sign change confirmation.",
        exit_hypothesis="Exit when net_flow reverts to prior regime or hold_bars.",
        failure_hypothesis="Fails in trend regimes where sign changes are noise.",
        cost_sensitivity="Medium.",
        capacity_assumptions="Net flow measured on synthetic single-venue tape.",
        invalidating_conditions=("regime_trend", "missing_trade_tape"),
        signal_kind="net_flow_sign_change",
        primary_feature="net_flow",
        secondary_feature="net_flow_lag",
        horizon_bars=5,
        hold_bars=8,
        direction_mode="fade",
    ),
    # --- LIQUIDATION_CASCADE (2) ---
    MechanismSpec(
        mechanism_id="MECH_LIQ_CASCADE_CONTINUATION_V4",
        family="LIQUIDATION_CASCADE",
        economic_rationale=(
            "Forced liquidation bursts create liquidity voids; short-horizon continuation "
            "with cascade direction is hypothesized."
        ),
        required_data=("liquidation_intensity", "liq_side", "depth_gap", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("liquidation events with exchange_ts_ms <= as_of_ms"),
        entry_hypothesis="Enter with liq_side when intensity spikes and depth_gap widens.",
        exit_hypothesis="Exit when intensity decays or hold_bars.",
        failure_hypothesis="Fails when cascade is immediately backstopped by passive capital.",
        cost_sensitivity="Very high — impact and partial fills dominate.",
        capacity_assumptions="Near-zero capacity in true cascades; synthetic probe only.",
        invalidating_conditions=("missing_liq_feed", "clock_quality_bad"),
        signal_kind="liq_intensity_continue",
        primary_feature="liquidation_intensity",
        secondary_feature="depth_gap",
        horizon_bars=2,
        hold_bars=5,
        direction_mode="continuation",
    ),
    MechanismSpec(
        mechanism_id="MECH_LIQ_CASCADE_ACCELERATION_V4",
        family="LIQUIDATION_CASCADE",
        economic_rationale=(
            "Acceleration of liquidation intensity (second difference) marks cascade "
            "phase transition — distinct from level-threshold cascade detection."
        ),
        required_data=("liquidation_intensity", "liquidation_intensity_lag", "aggression_ratio", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("intensity acceleration from lags <= t"),
        entry_hypothesis="Enter with aggression sign when intensity acceleration positive.",
        exit_hypothesis="Exit when acceleration turns negative or hold_bars.",
        failure_hypothesis="Fails on single-print spikes without follow-through.",
        cost_sensitivity="Extreme.",
        capacity_assumptions="Research-only; not sized for live cascade participation.",
        invalidating_conditions=("single_print_spike", "feed_dup_events"),
        signal_kind="liq_acceleration",
        primary_feature="liquidation_intensity",
        secondary_feature="liquidation_intensity_lag",
        horizon_bars=2,
        hold_bars=4,
        direction_mode="continuation",
    ),
    # --- POST_LIQUIDATION_EXHAUSTION (2) ---
    MechanismSpec(
        mechanism_id="MECH_POST_LIQ_SNAPBACK_V4",
        family="POST_LIQUIDATION_EXHAUSTION",
        economic_rationale=(
            "After cascade intensity collapses, exhausted forced flow often allows "
            "partial snapback as opportunistic liquidity returns."
        ),
        required_data=("liquidation_intensity", "liquidation_intensity_lag", "mid_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("post-cascade window starts only after intensity peak at <= t"),
        entry_hypothesis="Fade cascade direction after intensity collapse from peak.",
        exit_hypothesis="Exit on snapback completion proxy or hold_bars.",
        failure_hypothesis="Fails when secondary cascade wave arrives.",
        cost_sensitivity="High — timing errors vs second wave are costly.",
        capacity_assumptions="Assumes some restored depth post-event.",
        invalidating_conditions=("secondary_cascade", "depth_still_void"),
        signal_kind="post_liq_snapback",
        primary_feature="liquidation_intensity",
        secondary_feature="liquidation_intensity_lag",
        horizon_bars=6,
        hold_bars=10,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_POST_LIQ_VOLUME_DROUGHT_V4",
        family="POST_LIQUIDATION_EXHAUSTION",
        economic_rationale=(
            "Post-cascade volume drought signals exhausted participants; range "
            "compression / quiet fade differs from immediate snapback timing."
        ),
        required_data=("volume", "liquidation_intensity_lag", "range_compression", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("drought measured on completed post-event bars <= t"),
        entry_hypothesis="Enter mean-revert when volume drought follows prior liq spike.",
        exit_hypothesis="Exit when volume normalizes or hold_bars.",
        failure_hypothesis="Fails if drought is merely a data gap mislabeled as quiet.",
        cost_sensitivity="Medium — quieter tape but still pay spread.",
        capacity_assumptions="Low participation; synthetic small size.",
        invalidating_conditions=("data_quality_gap", "misclassified_quiet"),
        signal_kind="post_liq_drought",
        primary_feature="volume",
        secondary_feature="liquidation_intensity_lag",
        horizon_bars=8,
        hold_bars=12,
        direction_mode="fade",
    ),
    # --- ABSORPTION (2) ---
    MechanismSpec(
        mechanism_id="MECH_ABSORPTION_PASSIVE_REVERSAL_V4",
        family="ABSORPTION",
        economic_rationale=(
            "Large passive liquidity absorbs aggressive flow without price progress; "
            "subsequent reversal is hypothesized."
        ),
        required_data=("absorption_score", "aggression_ratio", "mid_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("absorption_score[t] vs mid_return[t] contemporaneous"),
        entry_hypothesis="Fade aggression when absorption high and mid_return muted.",
        exit_hypothesis="Exit on mid displacement or hold_bars.",
        failure_hypothesis="Fails when absorption is temporary before breakthrough.",
        cost_sensitivity="Medium-high.",
        capacity_assumptions="Passive size must exceed probe notional.",
        invalidating_conditions=("breakthrough_continuation", "spoof_absorption"),
        signal_kind="absorption_fade",
        primary_feature="absorption_score",
        secondary_feature="mid_return",
        horizon_bars=6,
        hold_bars=11,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_ABSORPTION_ICEBERG_LEVEL_DEFENSE_V4",
        family="ABSORPTION",
        economic_rationale=(
            "Repeated refreshes at a defended price level (iceberg-like) imply "
            "level defense; fade away-from-level aggression is distinct from score-only absorption."
        ),
        required_data=("level_refresh_count", "distance_to_level_bps", "aggression_ratio", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("level refreshes counted on bars <= t; no future level discovery"),
        entry_hypothesis="Fade aggression into defended level when refresh_count elevated.",
        exit_hypothesis="Exit if level breaks with displacement or hold_bars.",
        failure_hypothesis="Fails when iceberg pulls and level breaks.",
        cost_sensitivity="High near defended levels (adverse selection).",
        capacity_assumptions="Assumes detectable refresh pattern in synthetic book.",
        invalidating_conditions=("level_break", "refresh_feed_noise"),
        signal_kind="iceberg_level_fade",
        primary_feature="level_refresh_count",
        secondary_feature="distance_to_level_bps",
        horizon_bars=5,
        hold_bars=9,
        direction_mode="fade",
    ),
    # --- LIQUIDITY_WITHDRAWAL (2) ---
    MechanismSpec(
        mechanism_id="MECH_LIQUIDITY_WITHDRAWAL_ADVERSE_V4",
        family="LIQUIDITY_WITHDRAWAL",
        economic_rationale=(
            "Sudden visible-depth withdrawal raises impact and gap risk; short-horizon "
            "adverse selection dominates unless carefully gated."
        ),
        required_data=("depth_withdrawal", "spread_bps", "impact_bps", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("depth_withdrawal[t] from book deltas <= t"),
        entry_hypothesis="Avoid-or-fade: enter reduced-risk fade only after withdrawal confirms.",
        exit_hypothesis="Exit when depth restores or hold_bars.",
        failure_hypothesis="Fails when withdrawal precedes informative breakout.",
        cost_sensitivity="Extreme — impact approximation central.",
        capacity_assumptions="Capacity collapses with depth; research probe only.",
        invalidating_conditions=("depth_restore_fast", "feed_book_desync"),
        signal_kind="depth_withdrawal_adverse",
        primary_feature="depth_withdrawal",
        secondary_feature="impact_bps",
        horizon_bars=3,
        hold_bars=5,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_LIQUIDITY_THIN_BOOK_GAP_RISK_V4",
        family="LIQUIDITY_WITHDRAWAL",
        economic_rationale=(
            "Thin-book gap risk after gradual depth erosion differs from sudden withdrawal "
            "spikes; focuses on cumulative thinness, not one-shot pull."
        ),
        required_data=("depth_gap", "spread_bps", "vol_z", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("cumulative depth_gap path ending at t"),
        entry_hypothesis="Stand-aside / micro fade when depth_gap and spread jointly elevated.",
        exit_hypothesis="Exit on depth replenishment proxy or hold_bars.",
        failure_hypothesis="Fails when thin book still trends informatively.",
        cost_sensitivity="Very high.",
        capacity_assumptions="Near-zero actionable size.",
        invalidating_conditions=("trend_informative_thin_book", "dq_gap"),
        signal_kind="thin_book_gap",
        primary_feature="depth_gap",
        secondary_feature="spread_bps",
        horizon_bars=4,
        hold_bars=6,
        direction_mode="fade",
    ),
    # --- SPREAD_SHOCK (2) ---
    MechanismSpec(
        mechanism_id="MECH_SPREAD_SHOCK_FADE_V4",
        family="SPREAD_SHOCK",
        economic_rationale=(
            "Transient spread shocks mark liquidity stress; fade after normalization "
            "is hypothesized but often cost-dominated."
        ),
        required_data=("spread_shock", "spread_bps", "mid_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("spread_shock[t] vs prior median ending at t"),
        entry_hypothesis="Fade mid move accompanying transient spread_shock after peak.",
        exit_hypothesis="Exit when spread normalizes or hold_bars.",
        failure_hypothesis="Fails when shock is start of lasting stress regime.",
        cost_sensitivity="Extreme — the shock IS the cost.",
        capacity_assumptions="Quotes unreliable; tiny synthetic size.",
        invalidating_conditions=("stress_regime_persist", "quote_flicker"),
        signal_kind="spread_shock_fade",
        primary_feature="spread_shock",
        secondary_feature="spread_bps",
        horizon_bars=4,
        hold_bars=7,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_SPREAD_SHOCK_STRESS_CONTINUATION_V4",
        family="SPREAD_SHOCK",
        economic_rationale=(
            "When spread shock coincides with rising vol_z, stress continuation differs "
            "from fade-to-normal; this is the stress-continuation branch."
        ),
        required_data=("spread_shock", "vol_z", "aggression_ratio", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("joint spread_shock and vol_z at t"),
        entry_hypothesis="Continue with aggression when spread_shock and vol_z co-elevate.",
        exit_hypothesis="Exit when vol_z compresses or hold_bars.",
        failure_hypothesis="Fails on quote-only shocks without trade aggression.",
        cost_sensitivity="Extreme.",
        capacity_assumptions="Research-only.",
        invalidating_conditions=("quote_only_shock", "aggression_absent"),
        signal_kind="spread_shock_stress_continue",
        primary_feature="spread_shock",
        secondary_feature="vol_z",
        horizon_bars=3,
        hold_bars=6,
        direction_mode="continuation",
    ),
    # --- VOL_EXPANSION (2) ---
    MechanismSpec(
        mechanism_id="MECH_VOL_EXPANSION_BREAKOUT_CONTINUATION_V4",
        family="VOL_EXPANSION",
        economic_rationale=(
            "Volatility expansion with directional mid displacement hypothesizes "
            "breakout continuation under elevated realized vol."
        ),
        required_data=("vol_z", "mid_return", "range_expansion", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("vol_z and range_expansion on bars <= t"),
        entry_hypothesis="Enter with mid_return sign when vol_z expands above baseline.",
        exit_hypothesis="Exit on vol compression or hold_bars.",
        failure_hypothesis="Fails on expansion without directional conviction (whipsaw).",
        cost_sensitivity="High — wider spreads in expansion.",
        capacity_assumptions="Assumes continuous trading; gaps not modeled beyond synthetic.",
        invalidating_conditions=("whipsaw_expansion", "gap_open"),
        signal_kind="vol_expand_continue",
        primary_feature="vol_z",
        secondary_feature="mid_return",
        horizon_bars=6,
        hold_bars=10,
        direction_mode="continuation",
    ),
    MechanismSpec(
        mechanism_id="MECH_VOL_EXPANSION_RANGE_REOPEN_V4",
        family="VOL_EXPANSION",
        economic_rationale=(
            "Vol expansion that re-opens a compressed range without clean trend may "
            "mean-revert to range mid — distinct from breakout continuation."
        ),
        required_data=("vol_z", "range_compression_lag", "zscore_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("prior compression lag known at t; no future range bounds"),
        entry_hypothesis="Fade zscore_return when expansion follows prior compression without trend label.",
        exit_hypothesis="Exit toward range mid proxy or hold_bars.",
        failure_hypothesis="Fails when expansion is true regime shift to trend.",
        cost_sensitivity="Medium-high.",
        capacity_assumptions="Synthetic.",
        invalidating_conditions=("regime_trend", "true_breakout"),
        signal_kind="vol_expand_reopen_fade",
        primary_feature="vol_z",
        secondary_feature="zscore_return",
        horizon_bars=8,
        hold_bars=12,
        direction_mode="fade",
    ),
    # --- VOL_COMPRESSION (2) ---
    MechanismSpec(
        mechanism_id="MECH_VOL_COMPRESSION_COIL_BREAKOUT_V4",
        family="VOL_COMPRESSION",
        economic_rationale=(
            "Sustained range compression (coil) precedes breakout attempts; "
            "direction taken from first decisive mid displacement."
        ),
        required_data=("range_compression", "mid_return", "volume", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("compression window ending at t; breakout bar <= t"),
        entry_hypothesis="Enter with breakout mid_return after elevated compression.",
        exit_hypothesis="Exit on failed follow-through or hold_bars.",
        failure_hypothesis="Fails on false breakouts from coils.",
        cost_sensitivity="Medium.",
        capacity_assumptions="Assumes coil measured on stable bar grid.",
        invalidating_conditions=("false_break", "compression_misread_dq"),
        signal_kind="compression_breakout",
        primary_feature="range_compression",
        secondary_feature="mid_return",
        horizon_bars=10,
        hold_bars=14,
        direction_mode="continuation",
    ),
    MechanismSpec(
        mechanism_id="MECH_VOL_COMPRESSION_SQUEEZE_FAILURE_FADE_V4",
        family="VOL_COMPRESSION",
        economic_rationale=(
            "Failed squeeze after compression (break then immediate reclaim) is a "
            "failure-fade mechanism distinct from coil breakout continuation."
        ),
        required_data=("range_compression", "breakout_fail_flag", "mid_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("failure confirmed only after reclaim bar <= t"),
        entry_hypothesis="Fade original breakout direction after reclaim confirmation.",
        exit_hypothesis="Exit toward coil mid or hold_bars.",
        failure_hypothesis="Fails when reclaim is pause before second break.",
        cost_sensitivity="High — double spread around failure.",
        capacity_assumptions="Synthetic.",
        invalidating_conditions=("second_break", "low_volume_noise"),
        signal_kind="compression_fail_fade",
        primary_feature="range_compression",
        secondary_feature="breakout_fail_flag",
        horizon_bars=7,
        hold_bars=11,
        direction_mode="fade",
    ),
    # --- FUNDING_DISLOCATION (2) ---
    MechanismSpec(
        mechanism_id="MECH_FUNDING_EXTREME_MEAN_REVERT_V4",
        family="FUNDING_DISLOCATION",
        economic_rationale=(
            "Extreme funding encodes crowding stress; mean-reversion of funding "
            "dislocation is hypothesized after extremes."
        ),
        required_data=("funding_z", "oi_change", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("funding_z known only after funding print receive_ts_ms <= as_of_ms"),
        entry_hypothesis="Fade funding_z sign at extremes.",
        exit_hypothesis="Exit as funding_z normalizes or hold_bars.",
        failure_hypothesis="Fails during squeeze regimes where extremes persist/expand.",
        cost_sensitivity="Includes explicit funding_cost component dominance.",
        capacity_assumptions="Assumes funding print latency modeled via receive_ts.",
        invalidating_conditions=("squeeze_persist", "funding_print_stale"),
        signal_kind="funding_extreme_fade",
        primary_feature="funding_z",
        secondary_feature="oi_change",
        horizon_bars=12,
        hold_bars=16,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_FUNDING_CROWDING_SQUEEZE_CONTINUATION_V4",
        family="FUNDING_DISLOCATION",
        economic_rationale=(
            "Crowding with rising OI and extreme funding can continue into squeeze — "
            "opposite economic branch from funding mean-revert."
        ),
        required_data=("funding_z", "oi_change", "aggression_ratio", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("funding and oi prints eligible only if received <= as_of_ms"),
        entry_hypothesis="Continue against crowded side when funding extreme and oi rising.",
        exit_hypothesis="Exit on funding normalization or hold_bars.",
        failure_hypothesis="Fails when crowding unwinds abruptly (snapback).",
        cost_sensitivity="Funding + impact both material.",
        capacity_assumptions="Squeeze capacity hostile; research probe only.",
        invalidating_conditions=("crowding_unwind", "oi_feed_lag"),
        signal_kind="funding_squeeze_continue",
        primary_feature="funding_z",
        secondary_feature="oi_change",
        horizon_bars=10,
        hold_bars=14,
        direction_mode="continuation",
    ),
    # --- BASIS_DISLOCATION (2) ---
    MechanismSpec(
        mechanism_id="MECH_BASIS_PREMIUM_MEAN_REVERT_V4",
        family="BASIS_DISLOCATION",
        economic_rationale=(
            "Mark-index basis premium extremes often mean-revert as cash-and-carry "
            "inventory rebalances (research hypothesis, not edge claim)."
        ),
        required_data=("basis_bps", "funding_z", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("basis_bps from mark/index prints <= as_of_ms"),
        entry_hypothesis="Fade basis_bps sign at dislocation extremes.",
        exit_hypothesis="Exit toward basis median proxy or hold_bars.",
        failure_hypothesis="Fails when basis dislocation is structural (halts, index issues).",
        cost_sensitivity="Medium — basis trades pay two legs in reality; synthetic single-leg proxy.",
        capacity_assumptions="Assumes index integrity.",
        invalidating_conditions=("index_fault", "structural_basis_shift"),
        signal_kind="basis_fade",
        primary_feature="basis_bps",
        secondary_feature="funding_z",
        horizon_bars=10,
        hold_bars=15,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_BASIS_SHOCK_MOMENTUM_V4",
        family="BASIS_DISLOCATION",
        economic_rationale=(
            "Sudden basis shocks with aggressive flow may continue briefly before "
            "arbitrage inventory arrives — momentum branch distinct from premium MR."
        ),
        required_data=("basis_bps", "basis_bps_lag", "aggression_ratio", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("basis shock delta from lags <= t"),
        entry_hypothesis="Continue with basis shock direction when aggression confirms.",
        exit_hypothesis="Exit when shock decelerates or hold_bars.",
        failure_hypothesis="Fails when arb inventory arrives instantly.",
        cost_sensitivity="High.",
        capacity_assumptions="Short window only.",
        invalidating_conditions=("instant_arb", "index_desync"),
        signal_kind="basis_shock_momentum",
        primary_feature="basis_bps",
        secondary_feature="basis_bps_lag",
        horizon_bars=4,
        hold_bars=7,
        direction_mode="continuation",
    ),
    # --- CROSS_ASSET_LEAD_LAG (2) ---
    MechanismSpec(
        mechanism_id="MECH_CROSS_ASSET_BTC_ALT_LEAD_LAG_V4",
        family="CROSS_ASSET_LEAD_LAG",
        economic_rationale=(
            "Lead-lag between related instruments (e.g. BTC→alt) may transfer "
            "short-horizon information; PIT alignment is mandatory."
        ),
        required_data=("lead_return", "lag_return", "lead_lag_score", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("leader bars must be received <= as_of_ms before follower signal"),
        entry_hypothesis="Enter follower with lagged leader sign when lead_lag_score elevated.",
        exit_hypothesis="Exit after hold_bars or score decay.",
        failure_hypothesis="Fails when leader move already fully priced into follower.",
        cost_sensitivity="Medium — two-symbol costs; synthetic single proxy used.",
        capacity_assumptions="Assumes synchronous clocks across symbols.",
        invalidating_conditions=("clock_skew", "leader_already_priced"),
        signal_kind="lead_lag_transfer",
        primary_feature="lead_lag_score",
        secondary_feature="lead_return",
        horizon_bars=5,
        hold_bars=9,
        direction_mode="continuation",
    ),
    MechanismSpec(
        mechanism_id="MECH_CROSS_ASSET_CORR_BREAKDOWN_RV_V4",
        family="CROSS_ASSET_LEAD_LAG",
        economic_rationale=(
            "Cross-correlation breakdown between paired assets creates relative-value "
            "dislocation distinct from directional lead-lag transfer."
        ),
        required_data=("cross_corr", "pair_residual", "vol_z", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("corr window ending at t; no future residual peek"),
        entry_hypothesis="Fade pair_residual when cross_corr drops from elevated baseline.",
        exit_hypothesis="Exit as residual normalizes or hold_bars.",
        failure_hypothesis="Fails on structural de-pairing (narrative divergence).",
        cost_sensitivity="Medium.",
        capacity_assumptions="Pair trading capacity constrained; research probe.",
        invalidating_conditions=("structural_depair", "corr_estimation_unstable"),
        signal_kind="corr_breakdown_rv",
        primary_feature="cross_corr",
        secondary_feature="pair_residual",
        horizon_bars=9,
        hold_bars=13,
        direction_mode="fade",
    ),
    # --- REGIME_COND_MEAN_REVERSION (2) ---
    MechanismSpec(
        mechanism_id="MECH_REGIME_RANGE_ZSCORE_REVERT_V4",
        family="REGIME_COND_MEAN_REVERSION",
        economic_rationale=(
            "Range regimes favor mean reversion of z-scored returns; trend regimes "
            "destroy it — conditioning is the mechanism."
        ),
        required_data=("regime_label", "zscore_return", "vol_z", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("regime_label available_at_ms <= as_of_ms"),
        entry_hypothesis="Fade zscore_return only when regime_label==RANGE.",
        exit_hypothesis="Exit toward zero zscore or hold_bars.",
        failure_hypothesis="Fails on silent regime transition mid-hold.",
        cost_sensitivity="Medium.",
        capacity_assumptions="Regime classifier must be PIT-safe.",
        invalidating_conditions=("regime_transition", "label_stale"),
        signal_kind="regime_range_mr",
        primary_feature="zscore_return",
        secondary_feature="regime_label",
        horizon_bars=10,
        hold_bars=14,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_REGIME_TRANSITION_MR_SHUTDOWN_V4",
        family="REGIME_COND_MEAN_REVERSION",
        economic_rationale=(
            "Detecting RANGE→TREND transition shuts down MR and optionally flips to "
            "stand-aside — a control mechanism, not a param variant of range MR."
        ),
        required_data=("regime_label", "regime_label_lag", "zscore_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("transition uses regime_label[t] vs [t-1] only"),
        entry_hypothesis="Flatten / no new MR entries when RANGE→TREND transition fires.",
        exit_hypothesis="Forced flat on transition; hold_bars unused when shutdown.",
        failure_hypothesis="Fails on noisy label chatter causing over-shutdown.",
        cost_sensitivity="Low direct; opportunity-cost oriented.",
        capacity_assumptions="N/A — control overlay.",
        invalidating_conditions=("label_chatter", "partial_regime_availability"),
        signal_kind="regime_transition_shutdown",
        primary_feature="regime_label",
        secondary_feature="regime_label_lag",
        horizon_bars=2,
        hold_bars=2,
        direction_mode="fade",
    ),
    # --- BREAKOUT_CONTINUATION (2) ---
    MechanismSpec(
        mechanism_id="MECH_BREAKOUT_RANGE_HIGH_FOLLOWTHROUGH_V4",
        family="BREAKOUT_CONTINUATION",
        economic_rationale=(
            "Break of recent range high with volume confirmation hypothesizes "
            "follow-through continuation."
        ),
        required_data=("range_high_break", "volume", "mid_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("range_high computed on lookback ending at t-1; break bar at t"),
        entry_hypothesis="Enter long on range_high_break with volume confirmation.",
        exit_hypothesis="Exit on failed follow-through or hold_bars.",
        failure_hypothesis="Fails on liquidity-driven false breaks.",
        cost_sensitivity="Medium-high.",
        capacity_assumptions="Break levels congested; synthetic small size.",
        invalidating_conditions=("false_break", "volume_unconfirmed"),
        signal_kind="range_high_breakout",
        primary_feature="range_high_break",
        secondary_feature="volume",
        horizon_bars=6,
        hold_bars=10,
        direction_mode="long_only",
    ),
    MechanismSpec(
        mechanism_id="MECH_BREAKOUT_VOL_CONFIRMED_CONTINUATION_V4",
        family="BREAKOUT_CONTINUATION",
        economic_rationale=(
            "Breakout continuation conditioned on simultaneous vol expansion differs "
            "from pure price level breaks."
        ),
        required_data=("range_high_break", "vol_z", "aggression_ratio", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("vol_z and break flags at t only"),
        entry_hypothesis="Enter with break direction when vol_z confirms expansion.",
        exit_hypothesis="Exit when vol_z collapses or hold_bars.",
        failure_hypothesis="Fails on vol expansion without directional persistence.",
        cost_sensitivity="High in expanding vol.",
        capacity_assumptions="Synthetic.",
        invalidating_conditions=("vol_whipsaw", "aggression_absent"),
        signal_kind="vol_confirmed_breakout",
        primary_feature="range_high_break",
        secondary_feature="vol_z",
        horizon_bars=5,
        hold_bars=9,
        direction_mode="continuation",
    ),
    # --- FAILED_BREAKOUT (2) ---
    MechanismSpec(
        mechanism_id="MECH_FAILED_BREAKOUT_SNAPBACK_V4",
        family="FAILED_BREAKOUT",
        economic_rationale=(
            "Break then reclaim of range boundary hypothesizes snapback into range."
        ),
        required_data=("breakout_fail_flag", "mid_return", "range_compression", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("fail flag requires reclaim bar <= t"),
        entry_hypothesis="Fade breakout direction after breakout_fail_flag.",
        exit_hypothesis="Exit toward range mid proxy or hold_bars.",
        failure_hypothesis="Fails when failure is pause before successful second break.",
        cost_sensitivity="High.",
        capacity_assumptions="Synthetic.",
        invalidating_conditions=("second_break_success", "low_liquidity_noise"),
        signal_kind="failed_break_snapback",
        primary_feature="breakout_fail_flag",
        secondary_feature="mid_return",
        horizon_bars=5,
        hold_bars=8,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_FAILED_BREAKOUT_ABSORPTION_REVERSE_V4",
        family="FAILED_BREAKOUT",
        economic_rationale=(
            "Failed break accompanied by absorption score spike implies defensive "
            "inventory — reverse entry distinct from pure snapback timing."
        ),
        required_data=("breakout_fail_flag", "absorption_score", "aggression_ratio", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("absorption and fail flag at t"),
        entry_hypothesis="Reverse after fail when absorption_score elevated.",
        exit_hypothesis="Exit on absorption collapse or hold_bars.",
        failure_hypothesis="Fails when absorption is spoofed.",
        cost_sensitivity="Medium-high.",
        capacity_assumptions="Requires absorption metric integrity.",
        invalidating_conditions=("spoof_absorption", "fail_flag_noise"),
        signal_kind="failed_break_absorption",
        primary_feature="breakout_fail_flag",
        secondary_feature="absorption_score",
        horizon_bars=6,
        hold_bars=9,
        direction_mode="fade",
    ),
    # --- VOLUME_PRICE_DIVERGENCE (2) ---
    MechanismSpec(
        mechanism_id="MECH_VOL_PRICE_BEARISH_DIVERGENCE_V4",
        family="VOLUME_PRICE_DIVERGENCE",
        economic_rationale=(
            "Rising volume with falling price divergence hypothesizes distribution / "
            "continuation lower or mean-revert depending on regime — here fade of sell climax."
        ),
        required_data=("volume", "mid_return", "volume_price_div", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("divergence score ending at t"),
        entry_hypothesis="Fade negative mid_return when volume elevated (climax fade).",
        exit_hypothesis="Exit on divergence collapse or hold_bars.",
        failure_hypothesis="Fails in informational selloffs with persistent volume.",
        cost_sensitivity="Medium.",
        capacity_assumptions="Synthetic tape.",
        invalidating_conditions=("informational_selloff", "volume_feed_gap"),
        signal_kind="vp_bearish_div_fade",
        primary_feature="volume_price_div",
        secondary_feature="volume",
        horizon_bars=7,
        hold_bars=11,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_VOL_PRICE_BULLISH_DROUGHT_DIVERGENCE_V4",
        family="VOLUME_PRICE_DIVERGENCE",
        economic_rationale=(
            "Price rising on volume drought divergence hypothesizes fragile advance "
            "and fade — distinct from climax-volume divergence."
        ),
        required_data=("volume", "mid_return", "volume_drought", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("drought vs price path ending at t"),
        entry_hypothesis="Fade positive mid_return when volume_drought true.",
        exit_hypothesis="Exit when volume returns or hold_bars.",
        failure_hypothesis="Fails on quiet grind trends.",
        cost_sensitivity="Medium.",
        capacity_assumptions="Synthetic.",
        invalidating_conditions=("quiet_grind_trend", "volume_miscalibrated"),
        signal_kind="vp_drought_fade",
        primary_feature="volume_drought",
        secondary_feature="mid_return",
        horizon_bars=8,
        hold_bars=12,
        direction_mode="fade",
    ),
    # --- OI_DISLOCATION (2) ---
    MechanismSpec(
        mechanism_id="MECH_OI_SURGE_PRICE_STALL_V4",
        family="OI_DISLOCATION",
        economic_rationale=(
            "OI surge with stalled mid implies leverage build without price discovery; "
            "subsequent displacement risk is the research object."
        ),
        required_data=("oi_change", "mid_return", "funding_z", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("oi prints received <= as_of_ms"),
        entry_hypothesis="Stand-aside / reduced probe fade when oi surges and mid stalls.",
        exit_hypothesis="Exit on mid displacement or hold_bars.",
        failure_hypothesis="Fails when OI surge is hedging not speculative.",
        cost_sensitivity="Medium.",
        capacity_assumptions="OI feed latency must be modeled.",
        invalidating_conditions=("hedge_oi", "oi_print_stale"),
        signal_kind="oi_surge_stall",
        primary_feature="oi_change",
        secondary_feature="mid_return",
        horizon_bars=9,
        hold_bars=13,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_OI_FLUSH_LIQUIDATION_ALIGNED_V4",
        family="OI_DISLOCATION",
        economic_rationale=(
            "OI flush aligned with liquidation intensity marks forced de-leveraging; "
            "continuation with flush direction differs from surge-stall."
        ),
        required_data=("oi_change", "liquidation_intensity", "aggression_ratio", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("oi flush and liq intensity at t"),
        entry_hypothesis="Continue with aggression when oi flush and liq intensity co-occur.",
        exit_hypothesis="Exit when oi stabilizes or hold_bars.",
        failure_hypothesis="Fails on reporting artifacts in OI.",
        cost_sensitivity="High.",
        capacity_assumptions="Research-only.",
        invalidating_conditions=("oi_artifact", "liq_feed_missing"),
        signal_kind="oi_flush_continue",
        primary_feature="oi_change",
        secondary_feature="liquidation_intensity",
        horizon_bars=4,
        hold_bars=7,
        direction_mode="continuation",
    ),
    # --- MARKET_IMPACT_ASYMMETRY (2) ---
    MechanismSpec(
        mechanism_id="MECH_IMPACT_ASYMMETRY_FADE_V4",
        family="MARKET_IMPACT_ASYMMETRY",
        economic_rationale=(
            "Bid vs ask impact asymmetry after large prints may mean-revert as "
            "liquidity restocks the depleted side."
        ),
        required_data=("impact_bid_bps", "impact_ask_bps", "impact_asymmetry", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("impact estimates from prints <= t"),
        entry_hypothesis="Fade toward restock side when impact_asymmetry elevated.",
        exit_hypothesis="Exit as asymmetry normalizes or hold_bars.",
        failure_hypothesis="Fails when asymmetry reflects lasting information.",
        cost_sensitivity="The mechanism IS cost structure — net often destroyed.",
        capacity_assumptions="Impact model is approximate synthetic.",
        invalidating_conditions=("info_driven_asymmetry", "impact_model_unstable"),
        signal_kind="impact_asym_fade",
        primary_feature="impact_asymmetry",
        secondary_feature="impact_bps",
        horizon_bars=5,
        hold_bars=8,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_IMPACT_PERSISTENCE_AFTER_PRINT_V4",
        family="MARKET_IMPACT_ASYMMETRY",
        economic_rationale=(
            "Persistence of impact after a large print hypothesizes short continuation "
            "before mean reversion — distinct from asymmetry fade."
        ),
        required_data=("impact_bps", "large_print_flag", "mid_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("large_print_flag at t; no future impact path in signal"),
        entry_hypothesis="Continue with print direction briefly when impact_bps elevated.",
        exit_hypothesis="Exit quickly (short hold) as persistence decays.",
        failure_hypothesis="Fails when print is immediately faded by passive rebound.",
        cost_sensitivity="Very high.",
        capacity_assumptions="Cannot participate in the large print itself; after-print only.",
        invalidating_conditions=("immediate_passive_rebound", "print_flag_noise"),
        signal_kind="impact_persist_continue",
        primary_feature="impact_bps",
        secondary_feature="large_print_flag",
        horizon_bars=2,
        hold_bars=4,
        direction_mode="continuation",
    ),
    # --- TIME_OF_DAY (3) ---
    MechanismSpec(
        mechanism_id="MECH_TOD_ASIA_OPEN_THIN_LIQUIDITY_V4",
        family="TIME_OF_DAY",
        economic_rationale=(
            "Asia-open thin liquidity windows elevate gap/impact risk; behavior is "
            "session-structured, not a feature-threshold clone."
        ),
        required_data=("tod_bucket", "depth_gap", "spread_bps", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("tod_bucket from exchange_ts_ms only; no calendar lookahead"),
        entry_hypothesis="Stand-aside / micro mean-revert only inside Asia-open bucket when depth thin.",
        exit_hypothesis="Exit by bucket end or hold_bars.",
        failure_hypothesis="Fails on Asia sessions with atypical deep liquidity.",
        cost_sensitivity="High due to thinness.",
        capacity_assumptions="Session capacity lower; synthetic tiny size.",
        invalidating_conditions=("atypical_deep_asia", "clock_tz_misconfig"),
        signal_kind="tod_asia_thin",
        primary_feature="tod_bucket",
        secondary_feature="depth_gap",
        horizon_bars=6,
        hold_bars=8,
        direction_mode="fade",
    ),
    MechanismSpec(
        mechanism_id="MECH_TOD_US_OPEN_VOL_EXPANSION_V4",
        family="TIME_OF_DAY",
        economic_rationale=(
            "US-open window often expands realized vol; continuation with opening "
            "displacement is a TOD-conditioned mechanism."
        ),
        required_data=("tod_bucket", "vol_z", "mid_return", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("tod_bucket from exchange_ts_ms; vol_z at t"),
        entry_hypothesis="Continue with mid_return inside US-open bucket when vol_z expands.",
        exit_hypothesis="Exit after hold_bars or bucket exit.",
        failure_hypothesis="Fails on quiet US opens.",
        cost_sensitivity="Medium-high.",
        capacity_assumptions="Synthetic.",
        invalidating_conditions=("quiet_us_open", "holiday_session"),
        signal_kind="tod_us_vol",
        primary_feature="tod_bucket",
        secondary_feature="vol_z",
        horizon_bars=5,
        hold_bars=8,
        direction_mode="continuation",
    ),
    MechanismSpec(
        mechanism_id="MECH_TOD_FUNDING_SETTLEMENT_WINDOW_V4",
        family="TIME_OF_DAY",
        economic_rationale=(
            "Funding settlement windows create distinctive inventory reshuffles; "
            "behavior near settlement differs from Asia/US open TOD mechanisms."
        ),
        required_data=("tod_bucket", "funding_z", "oi_change", "exchange_ts_ms", "receive_ts_ms"),
        pit_semantics=_pit("settlement bucket from exchange_ts; funding print eligibility by receive_ts"),
        entry_hypothesis="Fade funding_z inside settlement bucket when oi_change elevated.",
        exit_hypothesis="Exit after settlement window or hold_bars.",
        failure_hypothesis="Fails when settlement is uneventful.",
        cost_sensitivity="Funding_cost central.",
        capacity_assumptions="Crowded window; research probe only.",
        invalidating_conditions=("uneventful_settlement", "funding_print_missing"),
        signal_kind="tod_funding_settlement",
        primary_feature="tod_bucket",
        secondary_feature="funding_z",
        horizon_bars=4,
        hold_bars=6,
        direction_mode="fade",
    ),
)


def assert_catalog_distinct() -> None:
    if len(SPECS) < MIN_MECHANISM_COUNT:
        raise AssertionError(f"mechanism_count_below_min:{len(SPECS)}<{MIN_MECHANISM_COUNT}")
    ids = [s.mechanism_id for s in SPECS]
    if len(ids) != len(set(ids)):
        raise AssertionError("duplicate_mechanism_id")
    families = {s.family for s in SPECS}
    if not set(MECHANISM_FAMILIES).issubset(families):
        missing = set(MECHANISM_FAMILIES) - families
        raise AssertionError(f"missing_families:{sorted(missing)}")
    rationales = [s.economic_rationale for s in SPECS]
    if len(rationales) != len(set(rationales)):
        raise AssertionError("cosmetic_clone_rationale_detected")
    kinds = [(s.signal_kind, s.primary_feature, s.secondary_feature, s.direction_mode) for s in SPECS]
    if len(kinds) != len(set(kinds)):
        raise AssertionError("cosmetic_clone_signal_contract_detected")
    # Distinct horizons/holds alone must NOT be the only differentiator for same kind+features.
    by_contract: dict[tuple[str, str, str], list[MechanismSpec]] = {}
    for s in SPECS:
        key = (s.signal_kind, s.primary_feature, s.secondary_feature)
        by_contract.setdefault(key, []).append(s)
    for key, group in by_contract.items():
        if len(group) > 1:
            dirs = {g.direction_mode for g in group}
            rats = {g.economic_rationale for g in group}
            if len(dirs) == 1 and len(rats) == 1:
                raise AssertionError(f"param_only_variants:{key}")


def mechanism_catalog() -> list[dict[str, Any]]:
    assert_catalog_distinct()
    out: list[dict[str, Any]] = []
    for s in SPECS:
        row = asdict(s)
        row["required_data"] = list(s.required_data)
        row["invalidating_conditions"] = list(s.invalidating_conditions)
        for field in REQUIRED_MECHANISM_FIELDS:
            if field not in row or row[field] in (None, "", (), []):
                raise AssertionError(f"missing_required_field:{s.mechanism_id}:{field}")
        out.append(row)
    return out


def specs_by_id() -> dict[str, MechanismSpec]:
    return {s.mechanism_id: s for s in SPECS}

"""Development Reflection fixtures for V16-E Lesson Compiler.

Synthetic / development only. Not OOS. Not real ACTIVE lessons.
"""
from __future__ import annotations

from backend.nexus_lesson_compiler.contracts import ReflectionFixture

# Founder example (adapted): WHEN vol=EXPANSION AND crowding AND no OI → BLOCK breakout_long
REFLECTION_FIXTURES: tuple[ReflectionFixture, ...] = (
    ReflectionFixture(
        reflection_id="REFL_DEV_BREAKOUT_CROWDING_001",
        conditions=(
            {"field": "volatility_regime", "op": "EQ", "value": "EXPANSION"},
            {"field": "long_crowding", "op": "GT", "value": 0.72},
            {"field": "oi_confirmation", "op": "IS_FALSE", "value": False},
        ),
        then_action={
            "expert": "breakout_long",
            "action_kind": "BLOCK",
            "target": "entry_signal",
            "detail": "Block breakout_long when expansion + crowding without OI confirm",
        },
        scope="EXPERT",
        affected_expert="breakout_long",
        regimes=("EXPANSION",),
        expiry={"expires_at_ms": None, "max_age_bars": 5000, "revalidation_required": True},
        evidence_count=12,
        confidence=0.61,
        contradictory_evidence=("oi_spike_on_2_of_12_cases",),
        author_model="nexus_reflection_fixture",
        author_version="v16e.fixture.1",
        narrative="Expansion crowding without OI often fails breakout continuation.",
    ),
    ReflectionFixture(
        reflection_id="REFL_DEV_FAILED_BREAKOUT_002",
        conditions=(
            {"field": "breakout_failure_rate", "op": "GT", "value": 0.55},
            {"field": "volume_confirm", "op": "IS_FALSE", "value": False},
        ),
        then_action={
            "expert": "breakout_continuation",
            "action_kind": "ABSTAIN",
            "target": "entry_signal",
            "detail": "Abstain on failed-breakout regime without volume confirm",
        },
        scope="STRATEGY_FAMILY",
        affected_expert="breakout_continuation",
        regimes=("TREND", "EXPANSION"),
        expiry={"expires_at_ms": None, "max_age_bars": 3000, "revalidation_required": True},
        evidence_count=9,
        confidence=0.58,
        contradictory_evidence=("thin_sample_crypto_alts",),
        author_model="nexus_reflection_fixture",
        author_version="v16e.fixture.1",
        narrative="Failed breakouts without volume confirm warrant abstention.",
    ),
    ReflectionFixture(
        reflection_id="REFL_DEV_LIQ_CASCADE_003",
        conditions=(
            {"field": "liquidation_intensity", "op": "GE", "value": 0.8},
            {"field": "spread_shock", "op": "EQ", "value": True},
        ),
        then_action={
            "expert": "mean_revert_fade",
            "action_kind": "WAIT",
            "target": "entry_timing",
            "detail": "Wait through liquidation cascade + spread shock before fade",
        },
        scope="REGIME",
        affected_expert="mean_revert_fade",
        regimes=("LIQUIDATION_STRESS",),
        expiry={"expires_at_ms": None, "max_age_bars": 2000, "revalidation_required": True},
        evidence_count=15,
        confidence=0.66,
        contradictory_evidence=("fast_recovery_in_2_cases",),
        author_model="nexus_reflection_fixture",
        author_version="v16e.fixture.1",
        narrative="Liquidation cascades with spread shock punish early fades.",
    ),
    ReflectionFixture(
        reflection_id="REFL_DEV_FUNDING_DISLOC_004",
        conditions=(
            {"field": "funding_zscore", "op": "GT", "value": 2.5},
            {"field": "basis_alignment", "op": "IS_FALSE", "value": False},
        ),
        then_action={
            "expert": "funding_carry",
            "action_kind": "BLOCK",
            "target": "entry_signal",
            "detail": "Block funding carry when funding extreme without basis alignment",
        },
        scope="EXPERT",
        affected_expert="funding_carry",
        regimes=("FUNDING_DISLOCATION",),
        expiry={"expires_at_ms": None, "max_age_bars": 4000, "revalidation_required": True},
        evidence_count=11,
        confidence=0.63,
        contradictory_evidence=("basis_caught_up_late_in_3_cases",),
        author_model="nexus_reflection_fixture",
        author_version="v16e.fixture.1",
        narrative="Extreme funding without basis alignment is unsafe for carry.",
    ),
    ReflectionFixture(
        reflection_id="REFL_DEV_VOL_COMPRESS_005",
        conditions=(
            {"field": "volatility_regime", "op": "EQ", "value": "COMPRESSION"},
            {"field": "range_width_pct", "op": "LT", "value": 0.012},
        ),
        then_action={
            "expert": "breakout_long",
            "action_kind": "DEFER",
            "target": "entry_timing",
            "detail": "Defer breakout entries inside extreme compression ranges",
        },
        scope="REGIME",
        affected_expert="breakout_long",
        regimes=("COMPRESSION",),
        expiry={"expires_at_ms": None, "max_age_bars": 2500, "revalidation_required": True},
        evidence_count=10,
        confidence=0.55,
        contradictory_evidence=("false_break_then_trend_1_case",),
        author_model="nexus_reflection_fixture",
        author_version="v16e.fixture.1",
        narrative="Ultra-tight compression often produces false breakouts.",
    ),
    ReflectionFixture(
        reflection_id="REFL_DEV_FLOW_REVERSAL_006",
        conditions=(
            {"field": "aggression_flip", "op": "EQ", "value": True},
            {"field": "depth_recovery", "op": "IS_FALSE", "value": False},
        ),
        then_action={
            "expert": "order_flow_imbalance",
            "action_kind": "REDUCE",
            "target": "signal_weight",
            "detail": "Reduce flow-imbalance weight when aggression flips without depth recovery",
        },
        scope="EXPERT",
        affected_expert="order_flow_imbalance",
        regimes=("TREND", "MEAN_REVERT"),
        expiry={"expires_at_ms": None, "max_age_bars": 3500, "revalidation_required": True},
        evidence_count=14,
        confidence=0.59,
        contradictory_evidence=("depth_refilled_within_2_bars_occasionally",),
        author_model="nexus_reflection_fixture",
        author_version="v16e.fixture.1",
        narrative="Aggression flips without depth recovery weaken flow signals.",
    ),
    ReflectionFixture(
        reflection_id="REFL_DEV_CROSS_ASSET_007",
        conditions=(
            {"field": "lead_lag_confidence", "op": "LT", "value": 0.4},
            {"field": "data_freshness_s", "op": "GT", "value": 30},
        ),
        then_action={
            "expert": "cross_asset_lead_lag",
            "action_kind": "ABSTAIN",
            "target": "entry_signal",
            "detail": "Abstain when lead-lag confidence low and data stale",
        },
        scope="STRATEGY_FAMILY",
        affected_expert="cross_asset_lead_lag",
        regimes=("ANY",),
        expiry={"expires_at_ms": None, "max_age_bars": 1500, "revalidation_required": True},
        evidence_count=8,
        confidence=0.57,
        contradictory_evidence=("btc_eth_pair_still_worked_twice",),
        author_model="nexus_reflection_fixture",
        author_version="v16e.fixture.1",
        narrative="Stale cross-asset lead-lag with low confidence should abstain.",
    ),
    ReflectionFixture(
        reflection_id="REFL_DEV_TIME_OF_DAY_008",
        conditions=(
            {"field": "session_bucket", "op": "IN", "value": ["ASIA_THIN", "WEEKEND_GAP"]},
            {"field": "spread_pct", "op": "GT", "value": 0.0008},
        ),
        then_action={
            "expert": "time_of_day",
            "action_kind": "BLOCK",
            "target": "entry_signal",
            "detail": "Block time-of-day expert in thin/weekend sessions with wide spreads",
        },
        scope="EXPERT",
        affected_expert="time_of_day",
        regimes=("ANY",),
        expiry={"expires_at_ms": None, "max_age_bars": 6000, "revalidation_required": True},
        evidence_count=13,
        confidence=0.64,
        contradictory_evidence=("one_asia_open_continuation",),
        author_model="nexus_reflection_fixture",
        author_version="v16e.fixture.1",
        narrative="Thin/weekend sessions with wide spreads invalidate TOD edges.",
    ),
)


def fixture_catalog() -> list[dict]:
    rows = []
    for f in REFLECTION_FIXTURES:
        rows.append(
            {
                "reflection_id": f.reflection_id,
                "conditions": list(f.conditions),
                "then_action": dict(f.then_action),
                "scope": f.scope,
                "affected_expert": f.affected_expert,
                "regimes": list(f.regimes),
                "expiry": dict(f.expiry),
                "evidence_count": f.evidence_count,
                "confidence": f.confidence,
                "contradictory_evidence": list(f.contradictory_evidence),
                "author_model": f.author_model,
                "author_version": f.author_version,
                "narrative": f.narrative,
            }
        )
    return rows

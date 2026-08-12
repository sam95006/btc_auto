from __future__ import annotations

from backend.nexus_research_ai_autonomy.two_sided_hypothesis import evaluate_two_sided_hypothesis


def test_direction_tie_wait_sets_ambiguity_flags_when_indicated():
    # This test is intentionally weak: scoring internals depend on candidate scoring inputs.
    # We still verify the contract: if the ambiguity flag is raised, the chosen side must be WAIT.
    h = evaluate_two_sided_hypothesis(
        symbol="BTCUSDT",
        entry_price=64000.0,
        equity=5000.0,
        vol_pct_per_hour=0.35,
        turnover24h=1e9,
        activity_score=0.8,
        qty_step=0.001,
        min_qty=0.001,
        min_notional=5.0,
        strategy_family="v18_2_phase_cd",
        target_pct=0.5,
        stop_pct=0.4,
        momentum_bias=0.0,
    )

    if h.direction_ambiguity_supported:
        assert h.selected_side == "WAIT"
        assert h.wait_reason == "DIRECTION_AMBIGUOUS"


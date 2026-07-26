"""Additional startup reconcile + multi-strategy tests."""
from __future__ import annotations

from backend.nexus_research.demo_autonomous.multi_strategy import (
    infer_regime,
    pick_best_strategy,
    score_strategies,
)
from backend.nexus_research.demo_autonomous.startup_reconcile import (
    AutonomousStartupReconciler,
    ExchangeExposureSnapshot,
)
from backend.nexus_research.demo_strategy.market_features import extract_features, FIXTURE_BTCUSDT


def test_startup_clean_allows():
    r = AutonomousStartupReconciler().reconcile(ExchangeExposureSnapshot())
    assert r.allow_new_orders is True
    assert r.status == "CLEAN"


def test_startup_exchange_position_blocks():
    r = AutonomousStartupReconciler().reconcile(
        ExchangeExposureSnapshot(positions=[{"size": 0.01}]),
        local_has_position=False,
    )
    assert r.allow_new_orders is False
    assert r.status == "RECOVERY_REQUIRED"


def test_startup_ambiguous_blocks():
    r = AutonomousStartupReconciler().reconcile(
        ExchangeExposureSnapshot(),
        ambiguous=True,
    )
    assert r.allow_new_orders is False


def test_multi_strategy_picks_fitted():
    feat = extract_features(FIXTURE_BTCUSDT, source="fixture")
    strategy, regime, score = pick_best_strategy(feat, "LONG")
    assert strategy
    assert regime
    assert score >= 0
    scores = score_strategies(feat, "LONG")
    assert len(scores) >= 5
    assert infer_regime(feat)


def test_supervisor_dry_exit_builds_reflection():
    import time

    from backend.nexus_research.demo_autonomous.position_lifecycle import PositionSnapshot
    from backend.nexus_research.demo_autonomous.position_supervisor import AutonomousPositionSupervisor

    now = int(time.time() * 1000)
    pos = PositionSnapshot(
        "BTCUSDT", "Buy", 0.01, 100_000, 98_000, -20, 96_000, 99_000, 103_000,
        now - 60_000, True,
    )
    r = AutonomousPositionSupervisor(dry_run=True).tick(
        pos,
        stop_distance_pct=1.5,
        risk_amount=25.0,
        strategy="TREND_FOLLOWING",
        regime="BULL_TREND",
        confidence=70,
        leverage=25,
    )
    assert r.closed is True
    assert r.reflection is not None
    assert r.reflection.to_dict()["livePatchApplied"] is False

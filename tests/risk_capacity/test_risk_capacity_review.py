"""Tests for V15-H Risk and Capacity Review Engine."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend.nexus_risk_capacity.adversarial import run_adversarial_review
from backend.nexus_risk_capacity.ai_gate import (
    AIOverrideRejected,
    apply_ai_suggestion,
    assert_no_ai_override,
    refuse_ai_override,
)
from backend.nexus_risk_capacity.artifacts import (
    FORBIDDEN_ARTIFACT_NAMES,
    build_campaign_summary,
    write_immutable_artifacts,
)
from backend.nexus_risk_capacity.bans import hard_ban_probe_matrix
from backend.nexus_risk_capacity.classifier import classify_candidate
from backend.nexus_risk_capacity.constants import (
    ALLOWED_LABELS,
    CANONICAL_COST_AUTHORITY,
    HARD_BANS,
    REQUIRED_COST_COMPONENTS,
    REQUIRED_OUTPUT_KEYS,
    REVIEW_DIMENSIONS,
)
from backend.nexus_risk_capacity.cost_consumer import (
    account_round_trip,
    assert_canonical_authority,
)
from backend.nexus_risk_capacity.engine import run_risk_capacity_review
from backend.nexus_risk_capacity.scenarios import (
    assert_all_dimensions_covered,
    iter_scenario_points,
)


def test_canonical_authority_binding() -> None:
    meta = assert_canonical_authority()
    assert meta["canonical_cost_authority"] == CANONICAL_COST_AUTHORITY
    assert meta["canonical_cost_authority_count"] == 1


def test_all_review_dimensions_covered() -> None:
    assert_all_dimensions_covered()
    dims = {p.dimension for p in iter_scenario_points()}
    assert dims == set(REVIEW_DIMENSIONS)
    assert len(list(iter_scenario_points())) >= len(REVIEW_DIMENSIONS) * 2


def test_full_cost_components_via_canonical_path() -> None:
    rt = account_round_trip(
        side="LONG",
        qty=Decimal("0.01"),
        entry_price=Decimal("60000"),
        exit_price=Decimal("60100"),
        maker_taker_mix=1.0,
        spread_bps=Decimal("2"),
        slippage_bps=Decimal("2"),
        impact_bps=Decimal("3"),
        funding_rate=None,
        extra_fills=1,
        cancel_replace_cycles=1,
        latency_ms=100.0,
        queue_position=0.5,
        liquidity_collapse=1.2,
        size_scale=1.5,
    )
    for key in REQUIRED_COST_COMPONENTS:
        assert key in rt["cost_components"]
        assert Decimal(rt["cost_components"][key]) >= 0
    assert rt["cost_bridge_verified"] is True
    assert rt["market_impact_outside_cost_bridge"] is True
    assert rt["cost_authority"] == CANONICAL_COST_AUTHORITY


def test_engine_hard_bans_and_required_outputs() -> None:
    report = run_risk_capacity_review(pass_id=1)
    assert report["candidate_count"] == 14
    assert report["qualification_ready_count"] == 0
    assert report["strategy_promoted_count"] == 0
    assert report["ai_override_applied_count"] == 0
    assert report["ai_override_attempted_count"] == 14
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_executed"] is False
    assert report["oos_consumed"] is False
    assert report["demo_order_count"] == 0
    assert report["status_json_written"] is False
    assert report["auto_integrate_attempted"] is False
    assert set(HARD_BANS).issubset(set(report["hard_bans"]))
    assert set(report["review_dimensions"]) == set(REVIEW_DIMENSIONS)
    for c in report["candidates"]:
        assert c["label"] in ALLOWED_LABELS
        assert c["qualified"] is False
        assert c["strategy_promoted"] is False
        assert c["ai_override_applied"] is False
        assert c["ai_override_attempted"] is True
        for key in REQUIRED_COST_COMPONENTS:
            assert key in c["cost_components"]
        for key in REQUIRED_OUTPUT_KEYS:
            assert key in c
        assert c["data_lineage"] == "SYNTHETIC_DEVELOPMENT_FIXTURE"
        assert c["cost_authority"] == CANONICAL_COST_AUTHORITY


def test_classifier_priority_and_banned_claims() -> None:
    assert (
        classify_candidate(
            {
                "data_quality_blocked": True,
                "sample_trade_count": 30,
            }
        )
        == "DATA_QUALITY_BLOCKED"
    )
    assert (
        classify_candidate(
            {
                "sample_trade_count": 30,
                "_concentration_blocked": True,
                "_baseline_gross": Decimal("10"),
                "_baseline_net": Decimal("4"),
            }
        )
        == "CONCENTRATION_BLOCKED"
    )
    assert (
        classify_candidate(
            {
                "sample_trade_count": 30,
                "_drawdown_unsafe": True,
                "_baseline_gross": Decimal("10"),
                "_baseline_net": Decimal("4"),
            }
        )
        == "DRAWDOWN_ASSUMPTION_UNSAFE"
    )
    assert (
        classify_candidate(
            {
                "sample_trade_count": 30,
                "_liquidation_unsafe": True,
                "_baseline_gross": Decimal("10"),
                "_baseline_net": Decimal("4"),
            }
        )
        == "LIQUIDATION_DISTANCE_UNSAFE"
    )
    destroyed = classify_candidate(
        {
            "sample_trade_count": 30,
            "_baseline_gross": Decimal("10"),
            "_baseline_net": Decimal("-1"),
            "_fragility": Decimal("0.1"),
            "_capacity_limited": False,
        }
    )
    assert destroyed == "COST_DESTROYED"


def test_ai_cannot_override() -> None:
    base = {
        "candidate_id": "RC01",
        "label": "RISK_CAPACITY_OBSERVED",
        "net_expectancy": "1.23",
        "strategy_promoted": False,
        "ai_override_applied": False,
    }
    out = apply_ai_suggestion(
        base,
        {"label": "QUALIFIED", "net_expectancy": "999999", "strategy_promoted": True},
    )
    assert out["label"] == "RISK_CAPACITY_OBSERVED"
    assert out["net_expectancy"] == "1.23"
    assert out["strategy_promoted"] is False
    assert out["ai_override_attempted"] is True
    assert out["ai_override_applied"] is False
    assert out["ai_override_refusal"]["allowed"] is False
    refusal = refuse_ai_override(candidate_id="RC01", attempted_fields=["label"])
    assert refusal["applied"] is False
    with pytest.raises(AIOverrideRejected):
        assert_no_ai_override({**base, "ai_override_applied": True})


def test_hard_ban_probe_matrix() -> None:
    matrix = hard_ban_probe_matrix()
    assert matrix["all_refused"] is True
    assert "force_ai_override" in matrix["probes"]
    assert "force_promote" in matrix["probes"]
    assert "force_status_json" in matrix["probes"]


def test_adversarial_pass() -> None:
    report = run_risk_capacity_review(pass_id=2)
    adv = run_adversarial_review(report)
    assert adv["pass_ok"] is True, adv
    assert adv["remaining_count"] == 0
    assert adv["qualification_ready_count"] == 0
    assert adv["ai_override_applied_count"] == 0


def test_artifacts_forbid_status_json(tmp_path: Path) -> None:
    report = run_risk_capacity_review(pass_id=2)
    adv = run_adversarial_review(report)
    paths = write_immutable_artifacts(report, adv, root=tmp_path)
    assert "status" not in paths
    assert paths["campaign_summary"].name == "campaign_summary.json"
    for p in paths.values():
        assert p.name not in FORBIDDEN_ARTIFACT_NAMES
        assert not p.name.endswith("_status.json")
    out_dir = tmp_path / "artifacts" / "readiness" / "immutable" / "v15_risk_capacity"
    assert not (out_dir / "status.json").exists()
    assert not list(out_dir.glob("*_status.json"))
    summary = build_campaign_summary(report, adv, root=tmp_path)
    assert summary["qualification_ready_count"] == 0
    assert summary["status_json_written"] is False
    assert summary["strategy_promoted_count"] == 0


def test_negative_path_labels_present() -> None:
    report = run_risk_capacity_review(pass_id=1)
    hist = report["label_histogram"]
    assert hist["DATA_QUALITY_BLOCKED"] >= 1
    assert hist["CONCENTRATION_BLOCKED"] >= 1
    assert hist["DRAWDOWN_ASSUMPTION_UNSAFE"] >= 1
    assert hist["LIQUIDATION_DISTANCE_UNSAFE"] >= 1

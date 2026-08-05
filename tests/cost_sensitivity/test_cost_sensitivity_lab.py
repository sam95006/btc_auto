"""Tests for V14-E Cost and Execution Sensitivity Lab."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend.nexus_cost_sensitivity.adversarial import run_adversarial_review
from backend.nexus_cost_sensitivity.classifier import classify_candidate
from backend.nexus_cost_sensitivity.constants import (
    ALLOWED_LABELS,
    CANONICAL_COST_AUTHORITY,
    HARD_BANS,
    REQUIRED_COST_COMPONENTS,
    REQUIRED_OUTPUT_KEYS,
    SENSITIVITY_DIMENSIONS,
)
from backend.nexus_cost_sensitivity.cost_consumer import (
    account_round_trip,
    assert_canonical_authority,
)
from backend.nexus_cost_sensitivity.lab import run_cost_sensitivity_lab
from backend.nexus_cost_sensitivity.scenarios import (
    assert_all_dimensions_covered,
    iter_scenario_points,
)
from backend.nexus_cost_sensitivity.artifacts import (
    build_status_payload,
    write_immutable_artifacts,
    write_runtime_status,
)


def test_canonical_authority_binding() -> None:
    meta = assert_canonical_authority()
    assert meta["canonical_cost_authority"] == CANONICAL_COST_AUTHORITY
    assert meta["canonical_cost_authority_count"] == 1


def test_all_sensitivity_dimensions_covered() -> None:
    assert_all_dimensions_covered()
    dims = {p.dimension for p in iter_scenario_points()}
    assert dims == set(SENSITIVITY_DIMENSIONS)
    assert len(list(iter_scenario_points())) >= len(SENSITIVITY_DIMENSIONS) * 2


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
    assert Decimal(str(rt["net_pnl"])) == rt["cost_bridge_net_pnl"] - rt[
        "cost_components_decimal"
    ]["market_impact_approximation"]


def test_lab_hard_bans_and_required_outputs() -> None:
    report = run_cost_sensitivity_lab(pass_id=1)
    assert report["candidate_count"] == 12
    assert report["qualification_ready_count"] == 0
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_executed"] is False
    assert report["oos_consumed"] is False
    assert report["demo_order_count"] == 0
    assert report["shadow_order_count"] == 0
    assert report["exchange_write_attempt_count"] == 0
    assert report["profitability_claimed"] is False
    assert report["qualified_claimed"] is False
    assert report["pr27_merge_attempted"] is False
    assert report["auto_integrate_attempted"] is False
    assert report["canonical_cost_formula_mutated"] is False
    assert set(HARD_BANS).issubset(set(report["hard_bans"]))
    assert set(report["sensitivity_dimensions"]) == set(SENSITIVITY_DIMENSIONS)
    for c in report["candidates"]:
        assert c["label"] in ALLOWED_LABELS
        assert c["qualified"] is False
        assert c["qualification_ready"] is False
        for key in REQUIRED_COST_COMPONENTS:
            assert key in c["cost_components"]
        for key in REQUIRED_OUTPUT_KEYS:
            assert key in c
        assert c["data_lineage"] == "SYNTHETIC_DEVELOPMENT_FIXTURE"
        assert c["cost_authority"] == CANONICAL_COST_AUTHORITY


def test_classifier_never_emits_banned_claims() -> None:
    label = classify_candidate(
        {
            "sample_trade_count": 30,
            "_baseline_gross": Decimal("10"),
            "_baseline_net": Decimal("4"),
            "_fragility": Decimal("0.1"),
            "_capacity_limited": False,
        }
    )
    assert label == "COST_SENSITIVITY_OBSERVED"
    assert label in ALLOWED_LABELS
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


def test_adversarial_pass() -> None:
    report = run_cost_sensitivity_lab(pass_id=2)
    adv = run_adversarial_review(report)
    assert adv["pass_ok"] is True, adv
    assert adv["remaining_count"] == 0
    assert adv["qualification_ready_count"] == 0


def test_artifacts_and_runtime_status(tmp_path: Path) -> None:
    report = run_cost_sensitivity_lab(pass_id=2)
    adv = run_adversarial_review(report)
    paths = write_immutable_artifacts(report, adv, root=tmp_path)
    assert paths["status"].is_file()
    assert paths["candidate_metrics"].is_file()
    summary = build_status_payload(report, adv, root=tmp_path)
    assert summary["qualification_ready_count"] == 0
    assert summary["auto_integrate_attempted"] is False
    runtime = write_runtime_status(summary, runtime_root=tmp_path)
    assert runtime.name == "v14_e_status.json"
    text = runtime.read_text(encoding="utf-8")
    assert '"qualification_ready_count": 0' in text
    assert '"canonical_cost_formula_mutated": false' in text


def test_latency_and_queue_modify_canonical_inputs_only() -> None:
    # Latency feeds extra slippage into canonical slippage_bps (taker legs only).
    base_taker = account_round_trip(
        side="LONG",
        qty=Decimal("0.01"),
        entry_price=Decimal("60000"),
        exit_price=Decimal("60120"),
        maker_taker_mix=1.0,
        latency_ms=0.0,
        queue_position=0.0,
    )
    lat = account_round_trip(
        side="LONG",
        qty=Decimal("0.01"),
        entry_price=Decimal("60000"),
        exit_price=Decimal("60120"),
        maker_taker_mix=1.0,
        latency_ms=500.0,
        queue_position=0.0,
    )
    # Queue bias converts maker→taker without inventing parallel fee math.
    base_maker = account_round_trip(
        side="LONG",
        qty=Decimal("0.01"),
        entry_price=Decimal("60000"),
        exit_price=Decimal("60120"),
        maker_taker_mix=0.0,
        latency_ms=0.0,
        queue_position=0.0,
    )
    queue = account_round_trip(
        side="LONG",
        qty=Decimal("0.01"),
        entry_price=Decimal("60000"),
        exit_price=Decimal("60120"),
        maker_taker_mix=0.0,
        latency_ms=0.0,
        queue_position=1.0,
    )
    assert Decimal(lat["cost_components"]["slippage_cost"]) > Decimal(
        base_taker["cost_components"]["slippage_cost"]
    )
    assert Decimal(lat["scenario_modifiers"]["slippage_bps"]) > Decimal(
        base_taker["scenario_modifiers"]["slippage_bps"]
    )
    assert Decimal(queue["cost_components"]["entry_fee"]) + Decimal(
        queue["cost_components"]["exit_fee"]
    ) > Decimal(base_maker["cost_components"]["entry_fee"]) + Decimal(
        base_maker["cost_components"]["exit_fee"]
    )


def test_no_oos_fixture_consumption() -> None:
    report = run_cost_sensitivity_lab(pass_id=1)
    assert all(c["oos_consumed"] is False for c in report["candidates"])
    assert report["oos_consumed"] is False


def test_runner_root_resolves_to_worktree() -> None:
    """Pass-2 trap: nested tools/research/cost_sensitivity must use parents[3]."""
    runner = (
        Path(__file__).resolve().parents[2]
        / "tools"
        / "research"
        / "cost_sensitivity"
        / "run_cost_sensitivity_lab.py"
    )
    assert runner.is_file()
    text = runner.read_text(encoding="utf-8")
    assert "parents[3]" in text
    assert "parents[2]" not in text.split("parents[3]")[0][-80:]


def test_capacity_and_fragility_outputs_are_structured() -> None:
    report = run_cost_sensitivity_lab(pass_id=2)
    for c in report["candidates"]:
        cap = c["capacity_estimate"]
        assert "maximum_viable_size_scale" in cap
        assert "capacity_notional_usdt" in cap
        assert "impact_bps_cap" in cap
        assert Decimal(c["fragility_score"]) >= 0
        assert Decimal(c["fragility_score"]) <= 1
        assert Decimal(c["break_even_cost"]) == Decimal(c["baseline"]["gross_pnl"])


def test_banned_claim_labels_rejected() -> None:
    from backend.nexus_cost_sensitivity.classifier import _assert_label_legal

    with pytest.raises(AssertionError):
        _assert_label_legal("QUALIFIED")
    with pytest.raises(AssertionError):
        _assert_label_legal("PROFITABLE")
    with pytest.raises(AssertionError):
        _assert_label_legal("DEMO_READY")
    with pytest.raises(AssertionError):
        _assert_label_legal("EDGE_CONFIRMED")
    assert classify_candidate({"sample_trade_count": 5}) == "INSUFFICIENT_SAMPLE"

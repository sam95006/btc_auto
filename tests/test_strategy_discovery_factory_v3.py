"""Tests for V13-C Cost-Aware Strategy Discovery Factory V3."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from backend.nexus_strategy_discovery_factory_v3.adversarial import run_adversarial_review
from backend.nexus_strategy_discovery_factory_v3.classifier import classify_candidate
from backend.nexus_strategy_discovery_factory_v3.constants import (
    ALLOWED_LABELS,
    MECHANISM_FAMILIES,
    REQUIRED_COST_COMPONENTS,
)
from backend.nexus_strategy_discovery_factory_v3.cost_accounting import account_trade_costs
from backend.nexus_strategy_discovery_factory_v3.factory import run_discovery_factory
from backend.nexus_strategy_discovery_factory_v3.families import assert_families_distinct, family_catalog
from backend.nexus_strategy_discovery_factory_v3.artifacts import (
    build_status_payload,
    write_immutable_artifacts,
    write_runtime_status,
)


def test_families_are_semantically_distinct() -> None:
    assert_families_distinct()
    catalog = family_catalog()
    assert len(catalog) == 10
    assert {c["family_id"] for c in catalog} == set(MECHANISM_FAMILIES)
    priors = [c["economic_prior"] for c in catalog]
    assert len(priors) == len(set(priors))
    mechs = [c["semantic_mechanism_id"] for c in catalog]
    assert len(mechs) == len(set(mechs))


def test_full_cost_components_present() -> None:
    costs = account_trade_costs(
        side="LONG",
        qty=Decimal("0.01"),
        entry_price=Decimal("50000"),
        exit_price=Decimal("50100"),
        spread_bps=Decimal("2"),
        slippage_bps=Decimal("2"),
        impact_bps=Decimal("3"),
        funding_rate=None,
        extra_fills=1,
        cancel_replace_cycles=1,
    )
    for key in REQUIRED_COST_COMPONENTS:
        assert key in costs["cost_components"]
        assert Decimal(costs["cost_components"][key]) >= 0
    assert costs["cost_bridge_verified"] is True
    assert Decimal(str(costs["net_pnl"])) == costs["cost_bridge_net_pnl"] - costs[
        "cost_components_decimal"
    ]["market_impact_approximation"]


def test_factory_run_hard_bans_and_labels() -> None:
    report = run_discovery_factory(pass_id=1)
    assert report["mechanism_family_count"] == 10
    assert report["candidate_configuration_count"] == 10
    assert report["qualification_ready_count"] == 0
    assert report["formal_walk_forward_executed"] is False
    assert report["oos_executed"] is False
    assert report["oos_consumed"] is False
    assert report["demo_order_count"] == 0
    assert report["exchange_write_attempt_count"] == 0
    assert report["profitability_claimed"] is False
    assert report["qualified_claimed"] is False
    assert report["pr27_merge_attempted"] is False
    for c in report["candidates"]:
        assert c["label"] in ALLOWED_LABELS
        assert c["qualified"] is False
        assert c["qualification_ready"] is False
        for key in REQUIRED_COST_COMPONENTS:
            assert key in c["cost_components"]
        assert c["data_lineage"] == "SYNTHETIC_DEVELOPMENT_FIXTURE"
        assert c["point_in_time_proof"]["lookahead_forbidden"] is True


def test_classifier_never_emits_qualified() -> None:
    label = classify_candidate(
        {
            "trade_count": 30,
            "gross_pnl": 10.0,
            "net_pnl": 4.0,
            "regime_breakdown": {"RANGE": 10, "TREND": 10, "STRESS": 10},
            "stability_measures": {
                "fold_count": 4,
                "positive_fold_count": 3,
                "sign_flip_across_folds": False,
            },
        }
    )
    assert label == "DEVELOPMENT_PROMISING_NOT_QUALIFIED"
    assert "QUALIFIED" in label  # substring ok only via NOT_QUALIFIED
    assert label in ALLOWED_LABELS


def test_adversarial_pass() -> None:
    report = run_discovery_factory(pass_id=2)
    adv = run_adversarial_review(report)
    assert adv["pass_ok"] is True
    assert adv["remaining_count"] == 0
    assert adv["qualification_ready_count"] == 0


def test_artifacts_and_runtime_status(tmp_path: Path) -> None:
    report = run_discovery_factory(pass_id=2)
    adv = run_adversarial_review(report)
    paths = write_immutable_artifacts(report, adv, root=tmp_path)
    assert paths["status"].is_file()
    summary = build_status_payload(report, adv, root=tmp_path)
    assert summary["qualification_ready_count"] == 0
    runtime = write_runtime_status(summary, runtime_root=tmp_path)
    assert runtime.name == "v13_c_strategy_discovery_status.json"
    text = runtime.read_text(encoding="utf-8")
    assert "qualification_ready_count" in text
    assert '"qualification_ready_count": 0' in text


def test_illegal_qualified_flag_rejected() -> None:
    from backend.nexus_strategy_discovery_factory_v3.classifier import enforce_no_qualification

    with pytest.raises(AssertionError):
        enforce_no_qualification(
            [{"label": "RESEARCH_SIGNAL_ONLY", "qualified": True, "qualification_ready": False}]
        )

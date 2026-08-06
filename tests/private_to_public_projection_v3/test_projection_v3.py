"""Tests for PUB17-C Private-to-Public Projection V3."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_private_to_public_projection_v3.allowlist import (
    ForbiddenPayloadKeyError,
    collect_field_names,
    count_execution_controls,
    serialize_allowlist,
)
from backend.nexus_private_to_public_projection_v3.constants import (
    ALLOWED_PUBLIC_FIELDS,
    BANNED_PRIVATE_FIELDS,
    HARD_BANS,
    LANE,
)
from backend.nexus_private_to_public_projection_v3.fixtures import (
    adversarial_dirty_payload,
    private_core_fixture,
    private_core_threshold_variant,
)
from backend.nexus_private_to_public_projection_v3.hard_bans import (
    HardBanViolation,
    refuse_execution_controls,
    refuse_pr26_pr27,
    refuse_proprietary_thresholds,
    refuse_report_edit,
    run_three_passes,
)
from backend.nexus_private_to_public_projection_v3.inference_redteam import (
    run_inference_redteam,
)
from backend.nexus_private_to_public_projection_v3.projector import (
    REQUIRED_PUBLIC_KEYS,
    project_private_to_public,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_lane_identity() -> None:
    assert LANE == "PUB17-C"
    assert "allowlist_only_projection" in HARD_BANS
    assert "inference_attack_survivors_must_be_0" in HARD_BANS
    assert "member_execution_control_count_must_be_0" in HARD_BANS


def test_allowlist_covers_founder_fields() -> None:
    for key in (
        "market_state",
        "regime_summary",
        "ai_public_suggestion",
        "risk_category",
        "evidence_summary",
        "counter_evidence_summary",
        "abstention_reason",
        "data_trust",
        "historical_similarity_aggregate",
        "delayed_aggregated_performance",
    ):
        assert key in ALLOWED_PUBLIC_FIELDS


def test_banned_surface_covers_founder_bans() -> None:
    for key in (
        "private_trade_ledger",
        "exchange_credentials",
        "strategy_parameters",
        "entry_threshold",
        "founder_capital",
        "exact_private_position",
        "private_lesson_text",
        "raw_decision_memory_graph_nodes",
        "execution_controls",
    ):
        assert key in BANNED_PRIVATE_FIELDS


def test_project_keeps_allowlisted_and_drops_private() -> None:
    proj = project_private_to_public(private_core_fixture())
    for key in REQUIRED_PUBLIC_KEYS:
        assert key in proj
    names = collect_field_names(proj)
    for banned in (
        "entry_threshold",
        "founder_capital",
        "execution_controls",
        "private_lesson_text",
        "exchange_credentials",
        "private_trade_ledger",
        "raw_decision_memory_graph_nodes",
    ):
        assert banned not in names
    assert proj["member_execution_control_count"] == 0
    assert proj["private_fields_included"] is False
    assert proj["raw_memory_graph"] is False
    assert proj["ai_public_suggestion"] == "WAIT"
    assert proj["risk_category"] == "MEDIUM"
    assert proj["data_trust"] == "TRUSTED"
    assert proj["delayed_aggregated_performance"]["performance_band"] == "POSITIVE"
    assert proj["historical_similarity_aggregate"]["case_count_band"] == "MEDIUM"


def test_adversarial_smuggle_dropped() -> None:
    proj = project_private_to_public(adversarial_dirty_payload())
    names = collect_field_names(proj)
    assert "entry_threshold" not in names
    assert "execution_controls" not in names
    assert "founder_capital" not in names
    assert "private_lesson_text" not in names
    assert count_execution_controls(proj) == 0


def test_serialize_allowlist_drops_unknown() -> None:
    out = serialize_allowlist(
        {
            "market_state": "OK",
            "entry_threshold": 0.9,
            "execution_controls": {"place_order": True},
            "founder_capital": 100,
        }
    )
    assert out == {"market_state": "OK"}


def test_threshold_variants_identical_public() -> None:
    a = project_private_to_public(private_core_threshold_variant(0.22))
    b = project_private_to_public(private_core_threshold_variant(0.88))
    skip = {"published_at", "retrieved_at", "as_of", "lineage_id"}
    va = {k: v for k, v in a.items() if k not in skip}
    vb = {k: v for k, v in b.items() if k not in skip}
    assert va == vb


def test_inference_redteam_survivors_zero() -> None:
    report = run_inference_redteam()
    assert report["survivor_count"] == 0
    assert report["survivors"] == []
    assert report["status"] == "PASS"
    assert report["attack_count"] >= 5


def test_member_execution_control_count_zero() -> None:
    proj = project_private_to_public(private_core_fixture())
    assert proj["member_execution_control_count"] == 0
    assert count_execution_controls(proj) == 0


def test_three_passes_pass() -> None:
    result = run_three_passes()
    assert result["ok"] is True
    assert result["status"] == "PASS"
    assert result["member_execution_control_count"] == 0
    assert result["inference_survivor_count"] == 0
    assert result["recommendation"].endswith("_PASS")


def test_hard_ban_refusers() -> None:
    with pytest.raises(HardBanViolation):
        refuse_execution_controls()
    with pytest.raises(HardBanViolation):
        refuse_proprietary_thresholds()
    with pytest.raises(HardBanViolation):
        refuse_report_edit()
    with pytest.raises(HardBanViolation):
        refuse_pr26_pr27()


def test_unavailable_private_core() -> None:
    proj = project_private_to_public(None)
    assert proj["availability"] == "UNAVAILABLE"
    assert proj["ai_public_suggestion"] == "UNAVAILABLE"
    assert proj["member_execution_control_count"] == 0


def test_owned_paths_exist() -> None:
    assert (REPO_ROOT / "backend" / "nexus_private_to_public_projection_v3").is_dir()
    assert (REPO_ROOT / "tests" / "private_to_public_projection_v3").is_dir()

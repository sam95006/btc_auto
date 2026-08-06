"""V18-D Live Opportunity Pipeline fixture E2E tests."""
from __future__ import annotations

import pytest

from backend.nexus_live_opportunity_pipeline.constants import (
    DECISION_ENUM,
    HARD_BANS,
    PIPELINE_STAGES,
    REQUIRED_DECISION_FIELDS,
)
from backend.nexus_live_opportunity_pipeline.fixtures import fixture_case_catalog
from backend.nexus_live_opportunity_pipeline.hard_bans import (
    HardBanViolation,
    assert_shadow_flags,
    hard_ban_inventory,
    hard_ban_probe_matrix,
    refuse_ai_override_data_trust,
    refuse_candidate_as_trade_signal,
    refuse_demo_orders,
)
from backend.nexus_live_opportunity_pipeline.live_hooks import discover_live_readonly_adapters
from backend.nexus_live_opportunity_pipeline.pipeline import (
    run_fixture_e2e,
    run_symbol_pipeline,
    tip_module_presence,
)


def test_decision_enum_complete() -> None:
    assert DECISION_ENUM == (
        "LONG",
        "SHORT",
        "WAIT",
        "REDUCE",
        "ABSTAIN",
        "BLOCK",
    )


def test_pipeline_stages_order() -> None:
    assert PIPELINE_STAGES[0] == "eligible_universe"
    assert PIPELINE_STAGES[-1] == "shadow_decision"
    assert "candidate_score" in PIPELINE_STAGES
    assert "cost_feasibility" in PIPELINE_STAGES
    assert "risk_review" in PIPELINE_STAGES


def test_tip_modules_present() -> None:
    present = tip_module_presence()
    assert present
    assert all(present.values()), present


def test_hard_bans() -> None:
    inv = hard_ban_inventory()
    assert inv["enforced"] is True
    assert set(HARD_BANS) == set(inv["hard_bans"])
    matrix = hard_ban_probe_matrix()
    assert matrix["all_raised"] is True
    with pytest.raises(HardBanViolation):
        refuse_demo_orders()
    with pytest.raises(HardBanViolation):
        refuse_ai_override_data_trust()
    with pytest.raises(HardBanViolation):
        refuse_candidate_as_trade_signal()


def test_live_readonly_hooks_honest() -> None:
    hooks = discover_live_readonly_adapters()
    assert hooks["exchange_write"] is False
    assert hooks["demo_orders"] is False
    assert hooks["mainnet_trading"] is False
    assert hooks["actual_ordered"] is False
    assert hooks["status"] in {
        "ADAPTERS_ABSENT",
        "ADAPTERS_PRESENT_HOOK_IDLE",
        "LIVE_READ_ONLY_AVAILABLE",
    }
    # Without env gate, fixture path remains default.
    if hooks["status"] != "LIVE_READ_ONLY_AVAILABLE":
        assert hooks["data_class_default"] == "FIXTURE"


def test_fixture_e2e_shadow_only() -> None:
    campaign = run_fixture_e2e(force_fixture=True)
    assert campaign["case_count"] == len(fixture_case_catalog())
    assert campaign["actual_ordered_count"] == 0
    assert campaign["actual_filled_count"] == 0
    assert campaign["trade_signal_count"] == 0
    assert set(campaign["decision_enum"]) == set(DECISION_ENUM)

    seen: set[str] = set()
    for result in campaign["results"]:
        decision = result["decision"]
        for field in REQUIRED_DECISION_FIELDS:
            assert field in decision, field
        assert decision["decision"] in DECISION_ENUM
        assert decision["actual_ordered"] is False
        assert decision["actual_filled"] is False
        assert decision["is_trade_signal"] is False
        assert decision["exchange_order_id"] is None
        assert decision["data_class"] == "FIXTURE"
        assert_shadow_flags(decision)
        seen.add(str(decision["decision"]))
        # Candidate score must never be a trade signal.
        cand = decision.get("candidate_score")
        if cand is not None:
            assert cand.get("is_trade_signal") is False
            assert cand.get("candidate_only") is True
        # All pipeline stages executed (or early universe block).
        for stage in PIPELINE_STAGES:
            if "ineligible" in decision["decision_id"]:
                continue
            assert stage in result["stages"] or stage in {
                "supporting_evidence",
                "contradicting_evidence",
                "shadow_decision",
            }


def test_trust_dominance_ai99_cannot_force_entry() -> None:
    case = next(c for c in fixture_case_catalog() if c["case_id"] == "BLOCK_TRUST_DOMINANCE_AI99")
    result = run_symbol_pipeline(case, force_fixture=True)
    decision = result["decision"]
    assert decision["decision"] in {"WAIT", "ABSTAIN", "BLOCK"}
    assert decision["decision"] not in {"LONG", "SHORT"}
    assert decision["data_trust"]["ai_override_applied"] is False
    assert decision["ai_confidence"] == 0.99


def test_risk_gate_blocks_ai_override() -> None:
    case = next(c for c in fixture_case_catalog() if c["case_id"] == "BLOCK_RISK_GATE")
    result = run_symbol_pipeline(case, force_fixture=True)
    decision = result["decision"]
    assert decision["decision"] in {"WAIT", "REDUCE", "ABSTAIN", "BLOCK"}
    assert decision["decision"] not in {"LONG", "SHORT"}
    risk = result["stages"]["risk_review"]
    assert risk["ai_override_applied"] is False
    assert risk["ai_override_attempted"] is True


def test_license_block() -> None:
    case = next(c for c in fixture_case_catalog() if c["case_id"] == "BLOCK_STALE_LICENSE")
    result = run_symbol_pipeline(case, force_fixture=True)
    assert result["decision"]["decision"] == "BLOCK"
    assert result["decision"]["data_trust"]["trust_status"] == "LICENSE_BLOCKED"


def test_cost_infeasible_not_entry() -> None:
    case = next(c for c in fixture_case_catalog() if c["case_id"] == "WAIT_COST_INFEASIBLE")
    result = run_symbol_pipeline(case, force_fixture=True)
    assert result["decision"]["decision"] not in {"LONG", "SHORT"}
    assert result["decision"]["cost_estimate"]["feasible"] is False


def test_memory_graph_sealed() -> None:
    case = next(c for c in fixture_case_catalog() if c["case_id"] == "LONG_HEALTHY")
    result = run_symbol_pipeline(case, force_fixture=True)
    memory = result["stages"]["shadow_decision"]["memory"]
    assert memory["sealed"] is True
    assert memory.get("node_id")
    assert result["decision"]["lineage"].get("memory_lineage_hash")

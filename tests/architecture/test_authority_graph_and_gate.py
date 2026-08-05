"""Tests for authority graph builder and CI gate."""
from __future__ import annotations

from pathlib import Path

from tools.architecture.build_authority_graph import build_graph, classify_claim
from tools.architecture.ci_gate_duplicate_authorities import build_baseline, evaluate_gate
from tools.architecture.check_contract_drift import run_drift_checks
from tools.architecture.recommend_removals import build_recommendations
from backend.nexus_contracts.authority_registry import build_canonical_registry


ROOT = Path(__file__).resolve().parents[2]


def test_build_graph_finds_execution_claims():
    graph = build_graph(ROOT, include_extended=False)
    assert graph["schema"] == "nexus_authority_graph_v1"
    assert graph["scanned_files"] > 0
    assert "execution" in graph["competing_authorities"]
    assert graph["competing_authorities"]["execution"]["canonical_module"].endswith(
        "execution_simulator_v1_1"
    )


def test_classify_canonical():
    registry = build_canonical_registry()
    claim = {
        "module": "backend.nexus_execution.fill_engine",
        "domain": "fill",
        "symbol": "try_fill",
    }
    assert classify_claim(claim, registry) == "canonical"


def test_ci_gate_passes_on_baseline():
    baseline = build_baseline()
    report = evaluate_gate(ROOT, baseline=baseline)
    assert report["passed"] is True, report["violations"]
    assert report["violation_count"] == 0


def test_drift_report_cost_version_aligned():
    report = run_drift_checks(ROOT)
    codes = {f["code"] for f in report["findings"]}
    assert "COST_MODEL_VERSION_DIVERGENCE" not in codes
    # Lifecycle dual vocabulary remains an open Lane H critical (out of scope for C1).
    assert "DUAL_LIFECYCLE_VOCABULARY" in codes


def test_cost_authority_registry_active():
    registry = build_canonical_registry()
    cost = registry["by_domain"]["cost"]
    assert cost["status"] == "active_compat_present"
    assert cost["canonical_module"] == "backend.nexus_execution.cost_model"
    assert cost["canonical_symbol"] == "CostModelContract"
    assert "cost" not in registry["summary"]["contested_domains"]


def test_removal_recommendations_never_delete_now():
    report = build_recommendations()
    assert report["policy"]["delete_now_allowed"] is False
    assert all(not r["delete_now"] for r in report["recommendations"])
    assert report["recommendation_count"] > 0


def test_execution_shim_authority_trap_gate_passes():
    from tools.architecture.ci_gate_execution_shim_authority import evaluate

    report = evaluate(ROOT)
    assert report["passed"] is True, report["violations"]
    assert report["canonical_execution_authority_count"] == 1
    assert report["canonical_fill_authority_count"] == 1
    assert report["shim_embedded_fill_authority_count"] == 0


def test_compat_shim_no_longer_hardcodes_taker_fee():
    report = run_drift_checks(ROOT)
    codes = {f["code"] for f in report["findings"]}
    assert "COMPAT_SIM_HARDCODED_FEE" not in codes

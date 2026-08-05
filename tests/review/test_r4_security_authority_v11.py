"""R4 Security + Authority review — unit + negative tests (two-pass aware)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.review.r4_security_authority.ast_mutator import (
    mutate_remove_path_traversal_token_check,
    mutate_scan_secrets_always_empty,
)
from tools.review.r4_security_authority.authority_review import (
    find_backend_sccs,
    verify_cost_model_divergence,
)
from tools.review.r4_security_authority.campaign import run_r4_campaign
from tools.review.r4_security_authority.constants import (
    ARTIFACT_REL,
    OWNED_PATHS,
    PRODUCTION_MUTATION_TARGETS,
)
from tools.review.r4_security_authority.lane_g_audit import audit_lane_g_mutation_depth
from tools.review.r4_security_authority.origin_loader import resolve_origin_roots
from tools.review.r4_security_authority.production_mutation import run_production_ast_mutation
from tools.review.r4_security_authority.security_static import (
    check_demo_mainnet_boundary,
    check_path_traversal,
    check_secret_detection,
    check_unsafe_deserialization,
)


ROOT = Path(__file__).resolve().parents[2]


def test_owned_paths_only_constants() -> None:
    assert "tools/review/r4_security_authority/" in OWNED_PATHS
    assert "tests/review/test_r4_security_authority_v11.py" in OWNED_PATHS
    assert ARTIFACT_REL + "/" in OWNED_PATHS or ARTIFACT_REL in "".join(OWNED_PATHS)


def test_ast_mutator_removes_dotdot_guard() -> None:
    src = (ROOT / "backend/nexus_autonomy/security_persistence_v1.py").read_text(encoding="utf-8")
    mutated, spec = mutate_remove_path_traversal_token_check(src)
    assert spec is not None
    assert "persist_drop_dotdot_token_check" == spec.mutant_id
    assert mutated != src
    assert "path_traversal" not in mutated or mutated.count("path_traversal") < src.count(
        "path_traversal"
    )


def test_ast_mutator_secrets_noop() -> None:
    src = (ROOT / "backend/nexus_autonomy/security_persistence_v1.py").read_text(encoding="utf-8")
    mutated, spec = mutate_scan_secrets_always_empty(src)
    assert spec is not None
    assert "return []" in mutated.replace(" ", "") or "return[]" in mutated.replace(" ", "")


def test_production_ast_mutation_runs() -> None:
    report = run_production_ast_mutation(ROOT)
    assert report["mutation_kind"] == "production_ast"
    assert report["tool"] == "custom_ast_mutator"
    assert report["mutmut_used"] is False
    assert report["mutant_total"] >= 1
    assert report["killed_count"] + report["survivor_count"] + report["error_count"] + report[
        "equivalent_count"
    ] == report["mutant_total"]
    for t in PRODUCTION_MUTATION_TARGETS:
        assert (ROOT / t).is_file()


def test_path_traversal_blocked() -> None:
    r = check_path_traversal()
    assert r["passed"] is True


def test_secret_detection_and_json_blind_spot_flagged() -> None:
    r = check_secret_detection()
    assert r["passed"] is True
    # Known residual: assignment regex vs JSON
    assert r["credential_assignment_json_blind_spot"] is True


def test_demo_mainnet_boundary() -> None:
    r = check_demo_mainnet_boundary()
    assert r["passed"] is True
    assert r["mainnet_client_created_count"] == 0


def test_unsafe_deserialization_suite() -> None:
    r = check_unsafe_deserialization()
    assert r["passed"] is True
    assert r["raw_unsafe_loads_count"] == 0


def test_cost_model_divergence_confirmed_on_base() -> None:
    r = verify_cost_model_divergence(ROOT)
    assert r["confirmed"] is True
    assert r["execution_version"] != r["strategy_version"]


def test_sccs_detectable() -> None:
    sccs = find_backend_sccs(ROOT)
    # Base tree should include the known execution / demo / research cycles
    assert isinstance(sccs, list)
    assert len(sccs) >= 1


def test_lane_g_depth_audit_wrapper_only() -> None:
    origins = resolve_origin_roots()
    if not (origins["g"] / "artifacts/readiness/immutable/v11_security_mutation_redteam/findings_summary.json").is_file():
        pytest.skip("Lane G origin worktree artifacts unavailable")
    audit = audit_lane_g_mutation_depth(origins["g"])
    assert audit["mutation_depth"] == "wrapper_in_memory"
    assert audit["finding"] is not None
    assert audit["finding"]["code"] == "G_MUTATION_DEPTH_WRAPPER_ONLY"
    assert audit["finding"]["severity"] == "critical"


def test_negative_campaign_does_not_claim_pass_when_critical() -> None:
    """Pass-1 campaign must not emit PASS recommendation while critical findings exist."""
    origins = resolve_origin_roots()
    status = run_r4_campaign(root=ROOT, origin_g=origins["g"], origin_h=origins["h"], passes=1)
    if status["critical_findings"]:
        assert status["recommendation"] != "NEXUS_V11_R4_SECURITY_AUTHORITY_PASS"
        assert "BLOCK" in status["integration_recommendation"]


def test_two_pass_artifacts_written() -> None:
    origins = resolve_origin_roots()
    status = run_r4_campaign(root=ROOT, origin_g=origins["g"], origin_h=origins["h"], passes=2)
    out = ROOT / ARTIFACT_REL
    assert (out / "pass1_report.json").is_file()
    assert (out / "pass2_report.json").is_file()
    assert (out / "findings_summary.json").is_file()
    assert (out / "mutation_report.json").is_file()
    assert (out / "authority_review.json").is_file()
    assert status["passes_completed"] == 2
    summary = json.loads((out / "findings_summary.json").read_text(encoding="utf-8"))
    assert summary["critical_count"] == len(status["critical_findings"])
    # Safety counters
    assert summary["exchange_write_attempt_count"] == 0
    assert summary["mainnet_client_created_count"] == 0


def test_pass2_adversarial_flags_lane_g_false_confidence() -> None:
    origins = resolve_origin_roots()
    if not (origins["g"] / "backend/nexus_autonomy/security_mutation_v11").exists():
        pytest.skip("Lane G origin unavailable")
    status = run_r4_campaign(root=ROOT, origin_g=origins["g"], origin_h=origins["h"], passes=2)
    p2 = json.loads((ROOT / ARTIFACT_REL / "pass2_report.json").read_text(encoding="utf-8"))
    flags = p2["adversarial_review"]["false_pass_flags"]
    codes = {f["code"] for f in flags}
    assert "LANE_G_FALSE_CONFIDENCE_PASS" in codes or any(
        c.get("code") == "G_MUTATION_DEPTH_WRAPPER_ONLY" for c in status["critical_findings"]
    )
    assert "G_PASS_DESPITE_PRODUCTION_AST_SURVIVORS" in codes or status["counters"][
        "production_ast_survivor_count"
    ] == 0
    multi_scope = [
        c
        for c in status["critical_findings"]
        if c.get("code") == "MULTI_SCOPE_AUTHORITY"
    ]
    domains = {
        c.get("domain") or (c.get("detail") or {}).get("domain") for c in multi_scope
    }
    assert "lifecycle" in domains
    assert "checkpoint" in domains


def test_negative_rejects_wrapper_only_as_production_proof() -> None:
    """Explicit negative: wrapper-depth G audit must never be treated as production AST."""
    origins = resolve_origin_roots()
    if not (origins["g"] / "artifacts/readiness/immutable/v11_security_mutation_redteam/findings_summary.json").is_file():
        pytest.skip("Lane G origin unavailable")
    audit = audit_lane_g_mutation_depth(origins["g"])
    assert audit["mutation_depth"] != "production_ast"
    assert audit.get("writes_production_sources") is False


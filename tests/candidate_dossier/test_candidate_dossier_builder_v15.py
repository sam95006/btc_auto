"""Tests for Founder V15-E Candidate Dossier Builder."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_candidate_dossier.bans import hard_ban_probe_matrix
from backend.nexus_candidate_dossier.builder import (
    build_dossier,
    expect_histogram_coverage,
    inject_forbidden_status_attempt,
)
from backend.nexus_candidate_dossier.constants import (
    ALLOWED_DOSSIER_STATUSES,
    ARTIFACT_REL,
    FORBIDDEN_OUTPUT_STATUSES,
    FORMAL_STATUS_BLOCKED,
    HARD_BANS,
    INFRA_STATUS_BLOCKED_READY,
    OWNED_PATHS,
    REQUIRED_DOSSIER_FIELDS,
    SCHEMA_ID,
)
from backend.nexus_candidate_dossier.controller import (
    CandidateDossierBuilderV15E,
    run_candidate_dossier_builder,
    run_two_pass_dossier,
    write_immutable_artifacts,
)
from backend.nexus_candidate_dossier.fixtures import build_synthetic_dossier_inputs

ROOT = Path(__file__).resolve().parents[2]

SECRET_PATTERNS = (
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)(?<!g)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)gsk_[A-Za-z0-9]{20,}"),
)


def test_schema_and_blocked_qualification():
    summary = run_candidate_dossier_builder()
    assert summary["schema"] == SCHEMA_ID
    assert summary["qualification_status"] == FORMAL_STATUS_BLOCKED
    assert summary["infrastructure_status"] == INFRA_STATUS_BLOCKED_READY
    assert summary["qualification_ready_count"] == 0
    assert summary["formal_walk_forward_executed"] is False
    assert summary["oos_touched"] is False
    assert summary["selected_strategy"] is None
    assert summary["promoted_strategy"] is None
    assert summary["lane_status_json_written"] is False


def test_status_ceiling_and_required_fields():
    summary = run_candidate_dossier_builder()
    hist = summary["dossiers"]["status_histogram"]
    assert expect_histogram_coverage(hist)
    for status in FORBIDDEN_OUTPUT_STATUSES:
        assert hist.get(status, 0) == 0
    for d in summary["dossiers"]["dossiers"]:
        assert d["dossier_status"] in ALLOWED_DOSSIER_STATUSES
        for field in REQUIRED_DOSSIER_FIELDS:
            assert field in d
            assert d[field] not in (None, "")
        assert d["qualified"] is False
        assert d["promoted"] is False
        assert d["demo_ready"] is False
        assert d["formal_walk_forward_executed"] is False
        assert d["oos_touched"] is False
        assert len(d["failed_sibling_experiments"]) >= 1
        assert d["universe_checksum"]
        assert d["code_checksum"]
        assert d["parameter_checksum"]
        assert d["feature_version"]
        assert d["cost_version"]
        assert d["risk_version"]
        assert d["execution_version"]
        assert d["regime_breakdown"]
        assert d["symbol_breakdown"]
        assert d["cost_breakdown"]


def test_per_candidate_expected_status():
    summary = run_candidate_dossier_builder()
    by_id = {d["candidate_id"]: d["dossier_status"] for d in summary["dossiers"]["dossiers"]}
    assert by_id["SYN_V15E_REVIEW_001"] == "DEVELOPMENT_REVIEW"
    assert by_id["SYN_V15E_PROMISING_002"] == "DEVELOPMENT_PROMISING_NOT_QUALIFIED"


def test_lineage_and_breakdown_integrity():
    inputs = build_synthetic_dossier_inputs()
    for c in inputs["candidates"]:
        d = build_dossier(c)
        assert d["data_lineage"]["fixture_only"] is True
        assert d["dossier_checksum"]
        assert set(d["symbol_breakdown"]) == set(c["symbol_breakdown"])
        assert "fees" in d["cost_breakdown"]
        assert "vol_high" in d["regime_breakdown"]
        assert d["capacity_assumptions"]["thin_market_block"] is True
        assert "formal_walk_forward_blocked" in d["remaining_blockers"]


def test_hard_bans_refuse_all():
    probe = hard_ban_probe_matrix("SYN_V15E_REVIEW_001")
    assert probe["all_refused"] is True
    assert "no_status_json_lane_reports" in HARD_BANS
    assert set(HARD_BANS).issubset(set(probe["hard_bans"]))
    ctrl = CandidateDossierBuilderV15E()
    ctrl.bootstrap()
    assert ctrl.attempt_formal_walk_forward()["allowed"] is False
    assert ctrl.attempt_oos()["allowed"] is False
    assert ctrl.attempt_select_strategy("x")["allowed"] is False
    assert ctrl.attempt_promote_strategy("x")["allowed"] is False
    assert ctrl.attempt_qualify("x")["allowed"] is False
    assert ctrl.attempt_demo_ready("x")["allowed"] is False
    assert ctrl.attempt_demo_order("x")["allowed"] is False
    assert ctrl.attempt_shadow_order("x")["allowed"] is False
    assert ctrl.attempt_auto_integrate()["allowed"] is False
    assert ctrl.attempt_exchange_write()["allowed"] is False
    assert ctrl.attempt_status_json_write()["allowed"] is False


def test_forbidden_status_injection_blocked():
    cand = build_synthetic_dossier_inputs()["candidates"][0]
    for status in ("QUALIFIED", "PROMOTED", "DEMO_READY", "OOS_READY", "WALK_FORWARD_READY"):
        result = inject_forbidden_status_attempt(cand, status)
        assert result["forbidden_accepted"] is False


def test_two_pass_deterministic():
    two = run_two_pass_dossier()
    assert two["both_passes_ok"] is True
    assert two["pass2"]["adversarial_ok"] is True
    assert two["lane_status_json_written"] is False
    assert all(two["pass2"]["stability"].values())
    assert (
        two["pass1"]["dossiers"]["bundle_digest"]
        == two["pass2"]["stable_rerun"]["bundle_digest"]
    )


def test_write_artifacts_no_status_json(tmp_path: Path):
    two = run_two_pass_dossier()
    paths = write_immutable_artifacts(two, root=tmp_path)
    art = tmp_path / ARTIFACT_REL
    assert art.is_dir()
    assert not list(art.glob("*status*.json"))
    for p in paths.values():
        assert p.exists()
        assert "status" not in p.name.lower()
        assert not p.name.endswith("_status.json")
    dossiers = json.loads(paths["dossiers"].read_text(encoding="utf-8"))
    assert dossiers["dossier_count"] == 2
    assert dossiers["status_ceiling_ok"] is True


def test_owned_paths_and_secret_scan():
    for rel in OWNED_PATHS[:3]:
        assert (ROOT / rel).exists()
    hits = []
    for rel in OWNED_PATHS[:3]:
        target = ROOT / rel
        if not target.exists():
            continue
        files = (
            [p for p in target.rglob("*.py") if p.is_file()]
            if target.is_dir()
            else [target]
        )
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(str(path))
                    break
    assert hits == []

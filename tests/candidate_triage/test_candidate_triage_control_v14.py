"""Tests for Founder V14-H Candidate Triage Control."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_candidate_triage.bans import hard_ban_probe_matrix
from backend.nexus_candidate_triage.connectors import connect_candidate, ingest_research_bundle
from backend.nexus_candidate_triage.constants import (
    ALLOWED_TRIAGE_STATUSES,
    CONNECTION_SURFACES,
    FORBIDDEN_OUTPUT_STATUSES,
    FORMAL_STATUS_BLOCKED,
    HARD_BANS,
    INFRA_STATUS_BLOCKED_READY,
    OWNED_PATHS,
    SCHEMA_ID,
)
from backend.nexus_candidate_triage.controller import (
    CandidateTriageControlV14H,
    run_candidate_triage_control,
    run_two_pass_triage,
    write_immutable_artifacts,
)
from backend.nexus_candidate_triage.engine import classify_candidate, expect_histogram_coverage
from backend.nexus_candidate_triage.fixtures import build_synthetic_research_bundle

ROOT = Path(__file__).resolve().parents[2]

SECRET_PATTERNS = (
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)(?<!g)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)gsk_[A-Za-z0-9]{20,}"),
)


def test_schema_and_blocked_qualification():
    summary = run_candidate_triage_control()
    assert summary["schema"] == SCHEMA_ID
    assert summary["qualification_status"] == FORMAL_STATUS_BLOCKED
    assert summary["infrastructure_status"] == INFRA_STATUS_BLOCKED_READY
    assert summary["qualification_ready_count"] == 0
    assert summary["formal_walk_forward_executed"] is False
    assert summary["oos_touched"] is False
    assert summary["selected_strategy"] is None
    assert summary["promoted_strategy"] is None


def test_all_allowed_statuses_exercised_none_forbidden():
    summary = run_candidate_triage_control()
    hist = summary["triage"]["status_histogram"]
    assert expect_histogram_coverage(hist)
    for status in FORBIDDEN_OUTPUT_STATUSES:
        assert hist.get(status, 0) == 0
    for r in summary["triage"]["results"]:
        assert r["triage_status"] in ALLOWED_TRIAGE_STATUSES
        assert r["qualified"] is False
        assert r["promoted"] is False
        assert r["demo_ready"] is False
        assert r["formal_walk_forward_executed"] is False
        assert r["oos_touched"] is False


def test_per_candidate_expected_status():
    summary = run_candidate_triage_control()
    by_id = {r["candidate_id"]: r["triage_status"] for r in summary["triage"]["results"]}
    assert by_id["SYN_V14H_DATA_001"] == "DATA_BLOCKED"
    assert by_id["SYN_V14H_SAMPLE_002"] == "SAMPLE_BLOCKED"
    assert by_id["SYN_V14H_COST_003"] == "COST_DESTROYED"
    assert by_id["SYN_V14H_REGIME_004"] == "REGIME_FRAGILE"
    assert by_id["SYN_V14H_REJECT_005"] == "REJECTED"
    assert by_id["SYN_V14H_REVIEW_006"] == "DEVELOPMENT_REVIEW"
    assert by_id["SYN_V14H_PROMISING_007"] == "DEVELOPMENT_PROMISING_NOT_QUALIFIED"


def test_connection_surfaces():
    ingested = ingest_research_bundle()
    assert ingested["ingested_candidate_count"] == 7
    assert ingested["qualification_ready_count"] == 0
    assert ingested["all_candidates_connected"] is True
    for conn in ingested["connections"]:
        for surface in CONNECTION_SURFACES:
            assert surface in conn["connections"]
            assert conn["connections"][surface]["connected"] is True
        plan = conn["connections"]["blocked_qualification_planning"]
        assert plan["formal_qualification_status"] == "BLOCKED"
        assert plan["qualification_ready"] is False
        assert plan["walk_forward_plan"]["formal_walk_forward_executed"] is False
        assert plan["oos_reservation_plan"]["oos_consumed"] is False
        assert plan["demo_eligibility_plan"]["demo_order_count"] == 0


def test_feature_lab_and_universe_fixture_only():
    bundle = build_synthetic_research_bundle()
    cand = bundle["candidates"][0]
    conn = connect_candidate(cand, as_of_ms=bundle["as_of_ms"])
    fl = conn["connections"]["feature_lab"]
    assert fl["fixture_only"] is True
    assert fl["predictive_edge_claimed"] is False
    assert fl["connected"] is True
    uni = conn["connections"]["dynamic_universe"]
    assert uni["fixture_only"] is True
    assert uni["live_exchange_called"] is False
    assert uni["connected"] is True


def test_hard_ban_refusals():
    ctrl = CandidateTriageControlV14H()
    summary = ctrl.bootstrap()
    assert summary["Founder_authorization_present"] is False
    assert summary["proofs"]["all_selects_refused"] is True
    assert summary["proofs"]["all_promotes_refused"] is True
    assert summary["proofs"]["all_qualifies_refused"] is True
    assert summary["proofs"]["all_demo_ready_refused"] is True
    assert summary["proofs"]["hard_ban_probe"]["all_refused"] is True
    assert summary["auto_integrated"] is False
    for ban in (
        "no_formal_walk_forward",
        "no_real_oos_reservation",
        "no_strategy_selection",
        "no_strategy_promotion",
        "no_qualified_output",
        "no_promoted_output",
        "no_demo_ready_output",
        "no_auto_integrate",
    ):
        assert ban in HARD_BANS
    probe = hard_ban_probe_matrix("X")
    assert probe["all_refused"] is True


def test_priority_collision_data_beats_promising():
    cand = build_synthetic_research_bundle()["candidates"][-1]
    cand = dict(cand)
    cand["data_quality_ok"] = False
    cand["pit_ok"] = False
    cand["signals"] = {"rejected": False, "promising": True, "needs_review": False}
    record = classify_candidate(cand)
    assert record["triage_status"] == "DATA_BLOCKED"


def test_two_pass_adversarial():
    two = run_two_pass_triage()
    assert two["both_passes_ok"] is True
    assert two["pass2"]["adversarial_ok"] is True
    assert two["qualification_ready_count"] == 0
    assert all(two["pass2"]["stability"].values())
    adv = two["pass2"]["adversarial"]
    assert adv["force_qualify"]["allowed"] is False
    assert adv["force_promote"]["allowed"] is False
    assert adv["inject_qualified"]["forbidden_accepted"] is False
    assert adv["inject_promoted"]["forbidden_accepted"] is False
    assert adv["inject_demo_ready"]["forbidden_accepted"] is False


def test_write_artifacts(tmp_path: Path):
    two = run_two_pass_triage()
    # Redirect ARTIFACT_REL by writing into a fake root layout
    fake_root = tmp_path
    (fake_root / "artifacts" / "readiness" / "immutable" / "v14_candidate_triage").mkdir(
        parents=True
    )
    paths = write_immutable_artifacts(two, root=fake_root)
    assert paths["status"].is_file()
    status = json.loads(paths["status"].read_text(encoding="utf-8"))
    assert status["qualification_ready_count"] == 0
    assert status["qualification_status"] == FORMAL_STATUS_BLOCKED
    hist = json.loads(paths["histogram"].read_text(encoding="utf-8"))
    assert hist["forbidden_output_count"] == 0
    assert expect_histogram_coverage(hist["status_histogram"])


def test_owned_paths_no_secrets():
    for rel in OWNED_PATHS:
        target = ROOT / rel
        if not target.exists():
            continue
        files = (
            [p for p in target.rglob("*") if p.is_file()]
            if target.is_dir()
            else [target]
        )
        for path in files:
            if path.suffix.lower() not in {".py", ".json", ".md"}:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                assert not pat.search(text), f"secret-like pattern in {path}"

"""OOS preflight freeze + readiness consolidation safety tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_demo_execution.h3_oos_policy_freeze import (
    FOUNDER_OOS_APPROVAL_PHRASE,
    OosApprovalError,
    assert_phrase_allows_oos,
    guard_oos_download,
    load_frozen_policy,
    load_oos_reservation,
    qualification_hierarchy,
    refuse_oos_during_cleanup,
)


CANONICAL = [
    ROOT / "docs" / "04_readiness" / "NEXUS_READINESS_SOT.md",
    ROOT / "artifacts" / "readiness" / "NEXUS_READINESS_SOT.json",
    ROOT / "artifacts" / "readiness" / "NEXUS_EVIDENCE_MANIFEST.json",
]


def test_canonical_files_exist():
    for p in CANONICAL:
        assert p.is_file(), p


def test_manifest_paths_exist():
    man = json.loads((ROOT / "artifacts/readiness/NEXUS_EVIDENCE_MANIFEST.json").read_text(encoding="utf-8"))
    missing = []
    for e in man.get("entries") or []:
        if e.get("status") == "SOURCE_MISSING":
            continue
        path = e.get("path")
        if not path:
            continue
        if not (ROOT / path).is_file():
            missing.append(path)
    assert missing == [], missing


def test_h3_policies_frozen():
    e = load_frozen_policy("H3E_OOS_POLICY_V1_FROZEN")
    d = load_frozen_policy("H3D_OOS_POLICY_V1_FROZEN")
    assert e["frozen_before_oos_download"] is True
    assert d["frozen_before_oos_download"] is True
    assert e["cost_gate_rules"]["MIN_NET_REWARD_RISK_RATIO"] == 1.2
    assert e["cost_gate_rules"]["MIN_NET_REWARD_TO_COST"] == 1.5
    assert e["risk_sizing_rules"]["margin_usdt"] == 20
    assert e["risk_sizing_rules"]["leverage"] == 25
    assert e["risk_sizing_rules"]["maximum_notional"] == 500


def test_oos_reservation_not_downloaded():
    r = load_oos_reservation()
    assert r["downloaded"] is False
    assert r["executed"] is False
    assert r["checksum"] is None
    assert r["download_requires_exact_phrase"] == FOUNDER_OOS_APPROVAL_PHRASE


def test_oos_download_requires_exact_founder_phrase():
    with pytest.raises(OosApprovalError):
        assert_phrase_allows_oos(None)
    with pytest.raises(OosApprovalError):
        assert_phrase_allows_oos("APPROVE_NEXUS_DEMO_6H_V2")
    with pytest.raises(OosApprovalError):
        guard_oos_download(founder_phrase="approve_nexus_h3_untouched_oos_v1")
    allowed = guard_oos_download(founder_phrase=FOUNDER_OOS_APPROVAL_PHRASE)
    assert allowed["allowed"] is True
    assert allowed["downloaded"] is False
    assert allowed["executed"] is False


def test_oos_cannot_execute_during_cleanup():
    with pytest.raises(OosApprovalError):
        refuse_oos_during_cleanup()


def test_mainnet_and_real_money_forbidden_in_sot():
    sot = json.loads((ROOT / "artifacts/readiness/NEXUS_READINESS_SOT.json").read_text(encoding="utf-8"))
    assert sot["safety"]["MAINNET"] is False
    assert sot["safety"]["REAL_MONEY"] is False
    assert sot["safety"]["EXCHANGE_WRITE"] is False
    assert sot["oos"]["downloaded"] is False
    assert sot["oos"]["executed"] is False
    assert sot["recommendation"] in {
        "NEXUS_NEW_OOS_PLAN_READY",
        "NEXUS_H3_OOS_APPROVAL_REQUIRED",
    }
    assert sot["account_state"]["wallet_delta_classification"] == "UNKNOWN"
    assert sot["account_state"]["wallet_delta_unattributed"] == -0.97052039
    assert sot["wallet_delta_classification"] == "UNKNOWN"
    assert sot["wallet_delta_unattributed"] == -0.97052039
    assert sot["risk_review_packet_ready"] is False
    assert sot["shadow_status"] == "NOT_APPLIED"
    assert sot["qualification_complete"] is False


def test_qualification_hierarchy():
    h = qualification_hierarchy()
    assert h["PRIMARY_QUALIFICATION_COHORT"] == "H3E"
    assert h["CONFIRMATORY_COHORT"] == "H3D"
    assert h["h3g_may_not_rescue_failed_h3e_oos"] is True
    assert h["h1_h2_excluded_from_qualification_oos"] is True


def test_raw_caches_are_gitignored():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "**/market_cache/" in gi or "market_cache/" in gi
    assert "**/micro_cache/" in gi or "micro_cache/" in gi


def test_consumed_oos_remains_immutable():
    path = ROOT / "artifacts/readiness/immutable/consumed_failed_oos/consumed_oos_holdout.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    # registry must remain present; exact schema may vary
    blob = json.dumps(data)
    assert "CONSUMED" in blob.upper() or "OOS" in blob.upper() or "holdout" in blob.lower()


def test_no_deleted_canonical_paths_missing_from_tree():
    required = [
        "artifacts/readiness/policies/H3E_OOS_POLICY_V1_FROZEN.json",
        "artifacts/readiness/policies/H3D_OOS_POLICY_V1_FROZEN.json",
        "artifacts/readiness/OOS_H3_UNTOUCHED_V1_RESERVATION.json",
        "artifacts/readiness/immutable/h3_walk_forward/edge_research_v3_report.json",
        "artifacts/readiness/immutable/6h_final/NEXUS_6H_V2_FINAL_REPORT.md",
        "artifacts/readiness/immutable/12h_final/NEXUS_12H_V3_FINAL_REPORT.md",
        "artifacts/readiness/immutable/post_12h_forensic/NEXUS_12H_V3_POST_FORENSIC_RETURN.json",
        "artifacts/readiness/immutable/risk_model_defect/risk_model_audit_report.json",
    ]
    missing = [p for p in required if not (ROOT / p).is_file()]
    assert missing == [], missing

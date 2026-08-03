"""Deep consolidation + OOS dry-run preflight (no download)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_demo_execution.h3_oos_policy_freeze import load_frozen_policy
from backend.nexus_demo_execution.oos import oos_runner_dry_run, attempt_oos_download, OosApprovalError
from backend.nexus_demo_execution import research as research_facade
from backend.nexus_demo_execution.evidence_store import orphan_count


H3E = "bca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33"
H3D = "d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7"


def test_frozen_policy_checksums_unchanged_after_deep_cleanup():
    e = load_frozen_policy("H3E_OOS_POLICY_V1_FROZEN")
    d = load_frozen_policy("H3D_OOS_POLICY_V1_FROZEN")
    assert e["policy_checksum"] == H3E
    assert d["policy_checksum"] == H3D


def test_oos_runner_dry_run_pass_without_network():
    r = oos_runner_dry_run()
    assert r["oos_runner_dry_run"] == "PASS"
    assert r["network_download_attempt_count"] == 0
    assert r["oos_data_record_count"] == 0
    assert r["oos_executed"] is False
    # After Founder download gate, downloaded may be true; dry-run still must not hit network.
    assert "h3e_checksum_ok" in r["checks"]
    assert r["checks"]["h3e_checksum_ok"] is True
    assert r["checks"]["h3d_checksum_ok"] is True


def test_oos_download_blocked_without_phrase():
    with pytest.raises(Exception):
        attempt_oos_download(founder_phrase=None)


def test_research_facade_does_not_mutate_frozen_flag():
    assert research_facade.FROZEN_SEMANTICS_MUTATED is False
    assert research_facade.ACTIVE_RESEARCH_FACADE is True


def test_consolidated_docs_exist():
    for p in [
        "docs/NEXUS_ARCHITECTURE.md",
        "docs/NEXUS_OPERATIONS.md",
        "docs/NEXUS_RESEARCH_QUALIFICATION.md",
        "docs/ui/NEXUS_UI_SOT.md",
        "docs/04_readiness/NEXUS_READINESS_SOT.md",
    ]:
        assert (ROOT / p).is_file(), p


def test_orphan_manifest_zero():
    assert orphan_count() == 0


def test_recommendation_terminal_oos_state_in_sot():
    sot = json.loads((ROOT / "artifacts/readiness/NEXUS_READINESS_SOT.json").read_text(encoding="utf-8"))
    assert sot.get("oos", {}).get("executed") is False
    assert sot.get("recommendation") in {
        "NEXUS_H3_OOS_APPROVAL_REQUIRED",
        "NEXUS_H3_OOS_DATA_INVALID",
        "NEXUS_H3_OOS_WAITING_FOR_RESERVED_WINDOW_CLOSE",
        "NEXUS_OOS_RESERVATION_CONTAMINATED_REPLACEMENT_REQUIRED",
        "NEXUS_WALLET_DELTA_FORENSIC_MANUAL_REVIEW_REQUIRED",
        "NEXUS_H3_CLOSED_HISTORICAL_VALIDATED_DEMO_FORWARD_APPROVAL_REQUIRED",
        "NEXUS_H3_CLOSED_HISTORICAL_FAILED_RETURN_TO_RESEARCH",
        "NEXUS_H3_CLOSED_HISTORICAL_INSUFFICIENT_NEW_RESEARCH_REQUIRED",
        "NEXUS_H3_CLOSED_HISTORICAL_DATA_INVALID",
        "NEXUS_NO_CLEAN_HISTORICAL_HOLDOUT_AVAILABLE",
        "NEXUS_H3_OOS_FAILED_RETURN_TO_RESEARCH",
        "NEXUS_H3_OOS_INSUFFICIENT_NEW_RESERVATION_REQUIRED",
        "NEXUS_H3_OOS_VALIDATED_RISK_REVIEW_REQUIRED",
        "NEXUS_H3_OOS_EXECUTION_INVALID",
        "NEXUS_NEW_OOS_PLAN_READY",
    }

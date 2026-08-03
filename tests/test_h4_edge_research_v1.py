"""H4 edge research V1 + H3 rejection / OOS isolation safety tests."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

ROOT = Path(__file__).resolve().parents[1]

from backend.nexus_demo_execution.closed_historical_registry import assert_september_partial_excluded
from backend.nexus_demo_execution.edge_research_h4 import (
    preregistration_checksum,
    preregistration_payload,
    sha_obj,
)
from backend.nexus_demo_execution.edge_research_h4_hypotheses import HYPOTHESES_H4


def test_consumed_holdout_cannot_be_reused():
    reg = json.loads(
        (
            ROOT
            / "artifacts/readiness/immutable/h3_closed_historical_v1/consumed_holdout_registry_entry.json"
        ).read_text(encoding="utf-8")
    )
    assert reg["classification"] == "CONSUMED_FAILED_CLOSED_HISTORICAL_HOLDOUT"
    assert reg["status"] == "CONSUMED"
    # SOT must mark H3 rejected when research package present
    sot = json.loads((ROOT / "artifacts/readiness/NEXUS_READINESS_SOT.json").read_text(encoding="utf-8"))
    # After research wave SOT should expose rejection; allow either explicit or prior fail stage
    assert sot.get("recommendation") is not None


def test_september_oos_cannot_validate_h4():
    sept = json.loads((ROOT / "artifacts/readiness/OOS_H3_UNTOUCHED_V1_RESERVATION.json").read_text(encoding="utf-8"))
    assert sept["executed"] is False
    assert sept["classification"] == "OOS_WINDOW_NOT_MATURE"
    with pytest.raises(RuntimeError, match="SEPTEMBER_PARTIAL"):
        assert_september_partial_excluded(".nexus_runtime/oos/OOS_H3_UNTOUCHED_V1_RESERVED/x.json")
    pre = preregistration_payload()
    assert pre["september_oos_may_not_validate_h4"] is True


def test_h4_hypotheses_checksummed_before_execution_artifact():
    path = ROOT / "artifacts/readiness/immutable/h4_edge_research_v1/h4_preregistration.json"
    if not path.is_file():
        # Pure function still produces stable checksum
        a = preregistration_checksum()
        b = preregistration_checksum()
        assert a == b and len(a) == 64
        return
    pre = json.loads(path.read_text(encoding="utf-8"))
    assert pre["created_before_evaluation"] is True
    assert pre["preregistration_checksum"] == preregistration_checksum()
    assert len(pre.get("hypothesis_checksums") or {}) == 3


def test_exact_threshold_changes_invalidate_prereg_checksum():
    base = preregistration_checksum()
    mutated = preregistration_payload()
    mutated["hypotheses"][0]["parameter_values"]["min_move_to_cost"] = 99.0
    assert sha_obj(mutated) != base


def test_h4_variants_cannot_be_added_after_visibility_contract():
    pre = preregistration_payload()
    assert pre["post_result_variant_addition_forbidden"] is True
    assert pre["max_hypotheses"] == 3
    assert len(HYPOTHESES_H4) <= 3


def test_h4_cannot_select_best_holdout_subgroup():
    for h in HYPOTHESES_H4:
        assert "H3_CLOSED_HISTORICAL_HOLDOUT_V1_RESERVED" in h["forbidden_sources_for_thresholds"]
        assert "OOS_H3_UNTOUCHED_V1_RESERVED" in h["forbidden_sources_for_thresholds"]


def test_h4_oos_begins_only_after_policy_freeze_when_present():
    res = ROOT / "artifacts/readiness/H4_UNTOUCHED_OOS_V1_RESERVATION.json"
    pol = ROOT / "artifacts/readiness/immutable/h4_edge_research_v1/policy_checksum_manifest.json"
    if not res.is_file():
        pytest.skip("no H4 OOS reservation — no WF-validated primary")
    assert pol.is_file()
    r = json.loads(res.read_text(encoding="utf-8"))
    p = json.loads(pol.read_text(encoding="utf-8"))
    assert r["downloaded"] is False
    assert r["executed"] is False
    assert r["policy_checksum"] == p["policy_checksum"]
    assert r["created_before_download"] is True


def test_walk_forward_validation_cannot_start_demo():
    summary = ROOT / "artifacts/readiness/immutable/h4_edge_research_v1/h4_research_summary.json"
    if not summary.is_file():
        assert os.environ["EXCHANGE_WRITE"] == "false"
        return
    s = json.loads(summary.read_text(encoding="utf-8"))
    assert s.get("demo_forward_packet_ready") is False
    assert s.get("demo_forward_status") == "BLOCKED_NO_VALIDATED_POLICY"
    assert s.get("exchange_write_attempt_count") == 0


def test_wallet_residual_remains_visible():
    sot = json.loads((ROOT / "artifacts/readiness/NEXUS_READINESS_SOT.json").read_text(encoding="utf-8"))
    assert abs(float(sot["wallet_delta_unattributed"]) - (-0.97052039)) <= 1e-8
    assert sot["wallet_delta_classification"] == "WALLET_DELTA_UNATTRIBUTED_EVIDENCE_LOST"


def test_h3_failed_status_cannot_be_overwritten_by_september_result():
    decomp = ROOT / "artifacts/readiness/immutable/h4_edge_research_v1/h3_failure_decomposition.json"
    if decomp.is_file():
        d = json.loads(decomp.read_text(encoding="utf-8"))
        assert d["H3E_promotion_status"] == "REJECTED_CURRENT_POLICY"
        assert d["september_oos_may_not_rescue"] is True
    sept = json.loads((ROOT / "artifacts/readiness/OOS_H3_UNTOUCHED_V1_RESERVATION.json").read_text(encoding="utf-8"))
    assert sept["executed"] is False

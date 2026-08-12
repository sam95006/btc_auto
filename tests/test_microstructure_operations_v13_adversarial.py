"""V13-A Pass 2 — adversarial self-review + negative tests."""
from __future__ import annotations

import os
from pathlib import Path

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ["DEMO"] = "false"

from backend.nexus_microstructure.ops_v13.adversarial import run_adversarial_pass2
from backend.nexus_microstructure.ops_v13.controller import MicrostructureOperationsControllerV13

REPO = Path(__file__).resolve().parents[1]


def test_adversarial_pass2_all_negative_tests(tmp_path: Path):
    result = run_adversarial_pass2(tmp_path / "adv")
    assert result["all_passed"] is True
    assert result["live_capture_started"] is False
    assert result["event_study_readiness_status"] == "NOT_READY"
    assert result["self_review"]["no_live_capture_from_agent"] is True
    assert result["self_review"]["no_event_study"] is True
    assert result["self_review"]["findings"] == []
    names = {t["name"] for t in result["negative_tests"]}
    required = {
        "neg_undersized_symbol_design",
        "neg_live_flags_without_coordinator",
        "neg_block_when_preflight_fails",
        "neg_disk_floor_blocks_start",
        "neg_clock_rollback_without_resume",
        "neg_duplicate_writer_conflict",
        "neg_hard_cap_stop",
        "neg_event_study_must_stay_not_ready",
        "neg_forbid_prior_campaign_id_reuse_as_live",
    }
    assert required <= names
    for t in result["negative_tests"]:
        assert t["status"] == "PASS", t


def test_controller_both_passes_keep_live_false(tmp_path: Path):
    ctl = MicrostructureOperationsControllerV13(
        REPO,
        work_root=tmp_path / "both",
        disk_root=str(tmp_path),
        previous_campaign_finalized=True,
    )
    both = ctl.run_both_passes()
    assert both["live_capture_started"] is False
    assert both["event_study_readiness_status"] == "NOT_READY"
    assert both["auto_integration"] is False
    assert both["pass2"]["all_passed"] is True
    assert both["pass1"]["preflight"]["all_passed"] is True

"""Tests for Integration Spine + Event Study framework."""
from __future__ import annotations

import os

os.environ["EXCHANGE_WRITE"] = "false"

from backend.nexus_autonomy.integration_spine_v1 import evaluate_spine
from backend.nexus_microstructure.event_study_framework_v1 import run_framework_self_test


def test_integration_spine_pass():
    r = evaluate_spine()
    assert r["integration_spine_status"] == "NEXUS_PRIVATE_INTEGRATION_SPINE_V1_PASS"
    assert r["missing_critical_stage_count"] == 0
    assert r["fixture_only_stage_count"] == 0
    assert r["exchange_write_attempt_count"] == 0
    assert r["real_learning_claimed"] is False


def test_event_study_framework_no_real_execution():
    r = run_framework_self_test()
    assert r["event_study_framework_status"] == "PASS"
    assert r["event_study_real_execution"] is False
    assert r["event_study_readiness_status"] == "NOT_READY"
    assert r["new_strategy_generated_count"] == 0
    assert r["profitability_claim_count"] == 0

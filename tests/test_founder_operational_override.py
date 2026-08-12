"""Founder operational override gate tests — honesty over silent skips."""
from __future__ import annotations

import os

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"

from backend.nexus_demo_execution.founder_operational_override import (
    ABORT_REASON,
    ABORT_STATUS,
    assert_override_cannot_bypass_12h_machine_gate,
    build_override_record,
    evaluate_operational_observation_gate,
)
from backend.nexus_demo_execution.v2_policy import MIN_NET_REWARD_RISK_RATIO as V2_RR


PASS_TEXT = """
observation_status=COMPLETE
operational_observation_pass=true
NEXUS_SINGLE_SERVICE_OPERATIONAL_24H_PASS
"""

INCOMPLETE_TEXT = """
observation_status=IN_PROGRESS
operational_observation_pass=false
observation_completed_full_24h=false
# no abort status
"""

ABORT_TEXT = f"""
observation_status={ABORT_STATUS}
operational_observation_pass=false
observation_completed_full_24h=false
reason={ABORT_REASON}
"""


def _override(text: str = ABORT_TEXT):
    return build_override_record(
        founder_override_id="FO-TEST-ABORT-24H",
        approved_at="2026-07-31T10:05:06Z",
        source_observation_report="docs/04_readiness/NEXUS_SINGLE_SERVICE_OPERATIONAL_OBSERVATION_ABORTED_REPORT.md",
        source_text=text,
    )


def test_incomplete_observation_without_override_blocks():
    r = evaluate_operational_observation_gate(observation_text=INCOMPLETE_TEXT, env={})
    assert r["allow_6h_v2_start"] is False
    assert "observation_incomplete_or_unmarked" in r["problems"]


def test_aborted_observation_without_founder_approval_blocks():
    r = evaluate_operational_observation_gate(
        observation_text=ABORT_TEXT,
        env={},  # flags absent
        override=_override(),
    )
    assert r["allow_6h_v2_start"] is False
    assert any(p.startswith("aborted_without_founder_flags") for p in r["problems"])


def test_aborted_observation_with_exact_founder_approval_allows():
    env = {
        "FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H": "true",
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2": "true",
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3": "true",
        "MAINNET": "false",
        "REAL_MONEY": "false",
    }
    r = evaluate_operational_observation_gate(
        observation_text=ABORT_TEXT,
        env=env,
        override=_override(),
    )
    assert r["allow_6h_v2_start"] is True
    assert r["path"] == "founder_abort_override"
    assert r["can_enable_mainnet"] is False
    assert r["can_disable_risk_controls"] is False
    assert r["can_bypass_6h_to_12h_machine_gate"] is False
    assert r["net_rr_floor"] == 1.2


def test_default_or_empty_override_flags_do_not_skip():
    env = {
        "FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H": "",
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2": "0",
    }
    r = evaluate_operational_observation_gate(
        observation_text=ABORT_TEXT,
        env=env,
        override=_override(),
    )
    assert r["allow_6h_v2_start"] is False


def test_override_cannot_enable_mainnet():
    env = {
        "FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H": "true",
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2": "true",
        "MAINNET": "true",
        "REAL_MONEY": "false",
    }
    r = evaluate_operational_observation_gate(
        observation_text=ABORT_TEXT,
        env=env,
        override=_override(),
    )
    assert r["allow_6h_v2_start"] is False
    assert "mainnet_forbidden" in r["problems"]


def test_override_cannot_disable_risk_controls_via_scope():
    env = {
        "FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H": "true",
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2": "true",
        "MAINNET": "false",
        "REAL_MONEY": "false",
    }
    r = evaluate_operational_observation_gate(
        observation_text=ABORT_TEXT,
        env=env,
        override=_override(),
        proposed_scope=["disable_risk_controls"],
    )
    assert r["allow_6h_v2_start"] is False
    assert any("forbidden_override_scope" in p for p in r["problems"])


def test_override_cannot_lower_net_rr():
    assert V2_RR == 1.2
    env = {
        "FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H": "true",
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2": "true",
        "MIN_NET_REWARD_RISK_RATIO": "0.5",
        "MAINNET": "false",
        "REAL_MONEY": "false",
    }
    r = evaluate_operational_observation_gate(
        observation_text=ABORT_TEXT,
        env=env,
        override=_override(),
    )
    assert r["allow_6h_v2_start"] is False
    assert "net_rr_lowered_forbidden" in r["problems"]


def test_override_cannot_bypass_6h_to_12h_machine_gate():
    env = {
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2": "true",
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3": "true",
        "BYPASS_6H_TO_12H_MACHINE_GATE": "true",
    }
    failed_6h = {
        "recommendation": "DEMO_AUTONOMOUS_6H_V2_FAILED",
        "session_completed": True,
        "write_window_closed": True,
        "position_count": 0,
        "open_order_count": 0,
        "reconciliation": "MATCH",
        "export_complete": True,
        "session_id": "6h-a",
        "proposed_12h_session_id": "12h-b",
    }
    r = assert_override_cannot_bypass_12h_machine_gate(failed_6h, env=env)
    assert r["allow_12h"] is False
    assert "bypass_flag_forbidden" in r["problems"]

    # Without bypass flag, failed 6H still blocked despite founder 12H flag.
    env2 = {
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2": "true",
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3": "true",
    }
    r2 = assert_override_cannot_bypass_12h_machine_gate(failed_6h, env=env2)
    assert r2["allow_12h"] is False
    assert "founder_flag_cannot_bypass_machine_gate" in r2["problems"]


def test_observation_pass_path_still_allows_without_override():
    r = evaluate_operational_observation_gate(observation_text=PASS_TEXT, env={"MAINNET": "false"})
    assert r["allow_6h_v2_start"] is True
    assert r["path"] == "observation_pass"

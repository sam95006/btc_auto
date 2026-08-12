"""Tests for DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION helpers."""
from backend.nexus_demo_execution.session_limits import SESSION_DURATION_SEC, SESSION_GATE_NAME


def test_session_duration_is_six_hours():
    assert SESSION_DURATION_SEC == 6 * 60 * 60


def test_session_gate_name_is_v2():
    assert SESSION_GATE_NAME == "DEMO_AUTONOMOUS_6H_V2_BOUNDED_VALIDATION"

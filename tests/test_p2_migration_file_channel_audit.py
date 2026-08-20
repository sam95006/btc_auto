"""File-channel audit vs stdout-authoritative migration preflight."""
from __future__ import annotations

from pathlib import Path

from tools.ci.p2_migration_atomic import (
    control_decision_from_channels,
    extract_authoritative_migration_stdout,
    file_channel_audit,
    preflight_may_continue_to_migration,
    stdout_exec_probe_pass,
)

WORKFLOW = Path(".github/workflows/founder_approved_staging_postgres_p2_migration.yml")
MARKER = "P2_MIGRATION_STDOUT_PROBE_5_1"


def test_stdout_present_file_api_200_zero_bytes_allows_preflight_continue():
    stdout = stdout_exec_probe_pass(expected_marker=MARKER, captured_stdout=f"noise\n{MARKER}\n")
    audit = file_channel_audit(http_status=200, bytes_count=0)
    decision = preflight_may_continue_to_migration(stdout_probe=stdout, file_audit=audit)
    assert stdout["P2_MIGRATION_SERVICE_EXEC_STDOUT_PASS"] is True
    assert audit["P2_MIGRATION_FILE_CHANNEL_AVAILABLE"] is False
    assert audit["file_channel_control_failure"] is False
    assert decision["may_continue"] is True
    assert decision["file_channel_blocks_migration"] is False


def test_stdout_marker_missing_fails_closed_before_migration():
    stdout = stdout_exec_probe_pass(expected_marker=MARKER, captured_stdout="service exec ok\n")
    audit = file_channel_audit(http_status=200, bytes_count=12, downloaded=b"x", expected_marker="x")
    decision = preflight_may_continue_to_migration(stdout_probe=stdout, file_audit=audit)
    assert stdout["P2_MIGRATION_SERVICE_EXEC_STDOUT_PASS"] is False
    assert decision["may_continue"] is False
    assert decision["fail_closed"] is True


def test_file_channel_unavailable_is_audit_only_not_control_failure():
    audit = file_channel_audit(http_status=404, bytes_count=0)
    assert audit["P2_MIGRATION_FILE_CHANNEL_AUDIT"] is True
    assert audit["P2_MIGRATION_FILE_CHANNEL_AVAILABLE"] is False
    assert audit["file_channel_authoritative"] is False
    assert audit["file_channel_control_failure"] is False
    stdout = stdout_exec_probe_pass(expected_marker=MARKER, captured_stdout=MARKER)
    decision = preflight_may_continue_to_migration(stdout_probe=stdout, file_audit=audit)
    assert decision["may_continue"] is True


def test_authoritative_stdout_pass_with_empty_file_channel_remains_pass():
    raw = (
        "P2_MIGRATION_PYTHON_STARTED=true\n"
        '{"P2_MIGRATION_0007_APPLIED_PASS": true, "exchange_write_call_count": 0, "create_order_calls": 0}\n'
    )
    stdout = extract_authoritative_migration_stdout(raw)
    control = control_decision_from_channels(
        stdout_result=stdout,
        file_http_status=200,
        file_bytes=0,
        file_payload=None,
    )
    assert stdout["decision"] == "PASS"
    assert control["decision"] == "PASS"
    assert control["file_channel_authoritative"] is False
    assert control["file_channel_override"] is False
    assert control["exchange_write_call_count"] == 0


def test_workflow_file_channel_is_audit_only_and_stdout_probe_is_required():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Prove authoritative service-exec stdout transport" in source
    assert "P2_MIGRATION_SERVICE_EXEC_STDOUT_PASS=true" in source
    assert "P2_MIGRATION_STDOUT_PROBE_" in source
    assert "Audit file channel without blocking migration" in source
    assert "P2_MIGRATION_FILE_CHANNEL_AUDIT=true" in source
    assert "P2_MIGRATION_FILE_CHANNEL_AVAILABLE=" in source
    assert "file_channel_authoritative=false" in source
    assert "Prove migration service exec and file download share filesystem" not in source
    assert "P2_MIGRATION_SERVICE_EXEC_FILE_CHANNEL_PASS=true" not in source
    assert 'test "$FOUND" = true' not in source
    assert source.index("Prove authoritative service-exec stdout transport") < source.index(
        "Apply and verify only migration 0007 through atomic same-exec"
    )
    assert source.index("Audit file channel without blocking migration") < source.index(
        "Apply and verify only migration 0007 through atomic same-exec"
    )

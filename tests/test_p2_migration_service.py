"""P2 migration 0007 dedicated Zeabur service identity and diagnostic parsing."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.ci.p2_migration_atomic import (
    FRESH_SERVICE_MAX_ATOMIC_ATTEMPTS,
    FRESH_SERVICE_ROLLOUT_MAX_ATTEMPTS,
    MAX_STALE_ATTEMPTS,
    PYTHON_STARTED_MARKER,
    STALE_POD_MARKER,
    current_pod_shell_gates_pass,
    extract_authoritative_migration_stdout,
    sanitize_prebootstrap_failure,
)
from tools.ci.p2_migration_service_identity import (
    LEARNING_VALIDATION_SERVICE_NAME,
    MIGRATION_SERVICE_NAME,
    assert_distinct_migration_service,
    safe_service_id_prefix,
)

WORKFLOW = Path(".github/workflows/founder_approved_staging_postgres_p2_migration.yml")
FIXTURE_CURRENT_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FIXTURE_OLD_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
LEARNING_VALIDATION_ID = "111111111111111111111111"
MIGRATION_ID = "222222222222222222222222"
FORBIDDEN = {
    "6a3b81652fdef84a45a2a553",
    "69d559cb2696d526abde8cda",
    "6a744ba3472e2c91a9e728a8",
    LEARNING_VALIDATION_ID,
}
SAFE = dict(
    postgres_url="postgresql://ledger",
    mainnet="false",
    real_money="false",
    demo_autonomous_enabled="false",
    autonomous_send="false",
    exchange_write="false",
)


def test_migration_service_name_is_distinct_from_learning_validation():
    assert MIGRATION_SERVICE_NAME == "nexus-p2-migration-0007"
    assert LEARNING_VALIDATION_SERVICE_NAME == "nexus-bybit-demo-learning-validation"
    assert MIGRATION_SERVICE_NAME != LEARNING_VALIDATION_SERVICE_NAME


def test_distinct_migration_service_passes_identity_gate():
    result = assert_distinct_migration_service(
        MIGRATION_ID,
        learning_validation_service_id=LEARNING_VALIDATION_ID,
        forbidden_service_ids=FORBIDDEN,
    )
    assert result["migration_service_distinct"] is True
    assert result["migration_service_id_prefix"] == safe_service_id_prefix(MIGRATION_ID)


def test_learning_validation_service_id_is_rejected():
    with pytest.raises(ValueError, match="migration_service_equals_learning_validation"):
        assert_distinct_migration_service(
            LEARNING_VALIDATION_ID,
            learning_validation_service_id=LEARNING_VALIDATION_ID,
            forbidden_service_ids=FORBIDDEN,
        )


def test_forbidden_service_id_is_rejected():
    forbidden_id = next(iter(FORBIDDEN))
    with pytest.raises(ValueError, match="migration_service_forbidden"):
        assert_distinct_migration_service(
            forbidden_id,
            learning_validation_service_id=LEARNING_VALIDATION_ID,
            forbidden_service_ids=FORBIDDEN,
        )


def test_fresh_service_bounded_attempt_constants():
    assert MAX_STALE_ATTEMPTS == FRESH_SERVICE_MAX_ATOMIC_ATTEMPTS == 3
    assert FRESH_SERVICE_ROLLOUT_MAX_ATTEMPTS == 12


def test_missing_baked_sha_fails_before_python():
    gate = current_pod_shell_gates_pass(
        expected=FIXTURE_CURRENT_SHA,
        baked="",
        source="",
        helper_present=True,
        **SAFE,
    )
    assert gate["python_may_start"] is False
    assert gate["stale_pod"] is True
    assert gate["marker"] == STALE_POD_MARKER


def test_service_exec_log_lines_are_parsed_as_data_not_python(tmp_path: Path):
    raw = (
        "expected_sha_prefix=914e715ddc3d\n"
        "baked_sha_prefix=\n"
        "source_sha_prefix=\n"
        "helper_present=true\n"
        f"{STALE_POD_MARKER}\n"
        "P2_MIGRATION_PYTHON_STARTED=false\n"
    )
    log_path = tmp_path / "p2_migration_service_exec.out"
    log_path.write_text(raw, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "tools/ci/p2_migration_parse_service_exec.py", str(log_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert proc.returncode == 0, proc.stderr
    diag = json.loads(proc.stdout)
    assert diag["expected_sha_prefix"] == "914e715ddc3d"
    assert diag["baked_sha_prefix"] == ""
    assert diag["python_started"] is False
    assert diag["stale_pod"] is True
    assert "SyntaxError" not in proc.stderr


def test_workflow_uses_isolated_migration_service_and_file_parser():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'SERVICE_NAME: nexus-p2-migration-0007' in source
    assert "ensure_p2_migration_zeabur_service.py" in source
    assert "ensure_demo_validation_zeabur_service.py" not in source
    assert "nexus-bybit-demo-learning-validation" not in source
    assert "p2_migration_parse_service_exec.py" in source
    assert "python - <<'PY' < /tmp/p2_migration_service_exec.out" not in source
    assert "MAX_ATTEMPTS=3" in source
    assert "MAX_ATTEMPTS=36" not in source
    assert "deploy/zeabur_p2_migration_0007/entrypoint.sh" in source
    assert "/tmp/nexus_p2_migration_0007/" in source


def test_migration_stdout_remains_authoritative():
    raw = (
        "noise\n"
        "P2_MIGRATION_CURRENT_POD_GATES_PASS=true\n"
        f"{PYTHON_STARTED_MARKER}\n"
        + json.dumps(
            {
                "P2_MIGRATION_0007_APPLIED_PASS": True,
                "exchange_write_call_count": 0,
                "create_order_calls": 0,
            }
        )
    )
    result = extract_authoritative_migration_stdout(raw)
    assert result["authoritative"] is True
    assert result["kind"] == "migration"
    assert result["payload"]["exchange_write_call_count"] == 0

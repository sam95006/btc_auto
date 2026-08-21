"""P2 migration 0007 dedicated Zeabur service identity and diagnostic parsing."""
from __future__ import annotations

import json
import os
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
    MIGRATION_SERVICE_BASE_NAME,
    MIGRATION_SERVICE_NAME,
    MIGRATION_SERVICE_NAME_PREFIX,
    assert_distinct_migration_service,
    assert_run_scoped_service_name,
    build_run_scoped_migration_service_name,
    safe_service_id_prefix,
)

WORKFLOW = Path(".github/workflows/founder_approved_staging_postgres_p2_migration.yml")
ROOT = Path(__file__).resolve().parents[1]
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


def test_migration_service_base_name_is_distinct_from_learning_validation():
    assert MIGRATION_SERVICE_BASE_NAME == "nexus-p2-migration-0007"
    assert MIGRATION_SERVICE_NAME == MIGRATION_SERVICE_BASE_NAME
    assert MIGRATION_SERVICE_NAME_PREFIX == "nexus-p2m7"
    assert LEARNING_VALIDATION_SERVICE_NAME == "nexus-bybit-demo-learning-validation"
    assert MIGRATION_SERVICE_BASE_NAME != LEARNING_VALIDATION_SERVICE_NAME


def test_run_scoped_names_differ_across_workflow_runs():
    name_a = build_run_scoped_migration_service_name(run_id=100, run_attempt=1)
    name_b = build_run_scoped_migration_service_name(run_id=101, run_attempt=1)
    assert name_a == "nexus-p2m7-100-1"
    assert name_b == "nexus-p2m7-101-1"
    assert name_a != name_b
    assert name_a != MIGRATION_SERVICE_BASE_NAME
    assert name_b != MIGRATION_SERVICE_BASE_NAME
    meta_a = assert_run_scoped_service_name(name_a, run_id=100, run_attempt=1)
    assert meta_a["P2_MIGRATION_RUN_SCOPED_SERVICE"] is True
    assert meta_a["P2_MIGRATION_PREVIOUS_SERVICE_REUSED"] is False
    assert meta_a["exchange_write_call_count"] == 0


def test_fixed_legacy_migration_service_name_is_rejected_for_runtime():
    with pytest.raises(ValueError, match="legacy_fixed_migration_service_name_forbidden"):
        assert_run_scoped_service_name(
            MIGRATION_SERVICE_BASE_NAME,
            run_id=100,
            run_attempt=1,
        )
    with pytest.raises(ValueError, match="legacy_fixed_migration_service_name_forbidden"):
        assert_distinct_migration_service(
            MIGRATION_ID,
            learning_validation_service_id=LEARNING_VALIDATION_ID,
            forbidden_service_ids=FORBIDDEN,
            service_name=MIGRATION_SERVICE_BASE_NAME,
        )


def test_distinct_migration_service_passes_identity_gate():
    result = assert_distinct_migration_service(
        MIGRATION_ID,
        learning_validation_service_id=LEARNING_VALIDATION_ID,
        forbidden_service_ids=FORBIDDEN,
        service_name="nexus-p2m7-100-1",
    )
    assert result["migration_service_distinct"] is True
    assert result["migration_service_id_prefix"] == safe_service_id_prefix(MIGRATION_ID)
    assert result["P2_MIGRATION_PREVIOUS_SERVICE_REUSED"] is False


def test_learning_validation_service_id_is_rejected():
    with pytest.raises(ValueError, match="migration_service_equals_learning_validation"):
        assert_distinct_migration_service(
            LEARNING_VALIDATION_ID,
            learning_validation_service_id=LEARNING_VALIDATION_ID,
            forbidden_service_ids=FORBIDDEN,
        )


def test_forbidden_service_id_is_rejected():
    forbidden_id = "6a3b81652fdef84a45a2a553"
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


def test_workflow_uses_run_scoped_migration_service_and_file_parser():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "P2_MIGRATION_SERVICE_NAME: nexus-p2m7-${{ github.run_id }}-${{ github.run_attempt }}" in source
    assert 'SERVICE_NAME: nexus-p2-migration-0007' not in source
    assert "P2_MIGRATION_RUN_SCOPED_SERVICE=true" in source
    assert "P2_MIGRATION_PREVIOUS_SERVICE_REUSED=false" in source
    assert "P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP=true" in source
    assert "python -m tools.ci.ensure_p2_migration_zeabur_service" in source
    assert "python tools/ci/ensure_p2_migration_zeabur_service.py" not in source
    assert "ensure_demo_validation_zeabur_service.py" not in source
    assert "nexus-bybit-demo-learning-validation" not in source
    assert "python -m tools.ci.p2_migration_parse_service_exec" in source
    assert "python -m tools.ci.p2_extract_migration_authoritative_stdout" in source
    assert "python - <<'PY' < /tmp/p2_migration_service_exec.out" not in source
    assert "MAX_ATTEMPTS=3" in source
    assert "MAX_ATTEMPTS=36" not in source
    assert "build_migration_context" in source
    assert "zeabur_p2_migration_0007" in (ROOT / "tools" / "ci" / "p2_migration_bootstrap.py").read_text(encoding="utf-8")
    assert "/tmp/nexus_p2_migration_0007/" in source
    resolve_idx = source.index("Create run-scoped migration service with single migration-context deploy")
    apply_idx = source.index("Apply and verify only migration 0007 through atomic same-exec")
    resolve_block = source[resolve_idx:apply_idx]
    assert "PYTHONPATH: ${{ github.workspace }}" in resolve_block
    assert "python -m tools.ci.ensure_p2_migration_zeabur_service" in resolve_block
    assert "P2_MIGRATION_SERVICE_NAME" in resolve_block
    assert "P2_MIGRATION_CONTEXT_DIR" in resolve_block
    assert "github.run_id" in resolve_block
    assert "P2_MIGRATION_SERVICE_EXEC_STDOUT_PASS=true" in source
    assert "P2_MIGRATION_FILE_CHANNEL_AUDIT=true" in source
    assert "Prove migration service exec and file download share filesystem" not in source
    assert 'test "$FOUND" = true' not in source
    assert source.index("Build migration deployment context before service create") < resolve_idx
    assert "P2_MIGRATION_SECOND_SERVICE_CREATED=false" in source


def test_ensure_p2_migration_module_invocation_bootstraps_without_tools_import_error():
    """Reproduce GitHub runner: repo-root cwd + module invocation, no secrets."""
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["GITHUB_RUN_ID"] = "100"
    env["GITHUB_RUN_ATTEMPT"] = "1"
    env["P2_MIGRATION_SERVICE_NAME"] = "nexus-p2m7-100-1"
    for key in (
        "ZEABUR_TOKEN",
        "ZEABUR_PROJECT_ID",
        "PRESET_SERVICE_ID",
        "LEARNING_VALIDATION_SERVICE_ID",
        "ZEABUR_DEMO_VALIDATION_SERVICE_ID",
    ):
        env.pop(key, None)
    proc = subprocess.run(
        [sys.executable, "-m", "tools.ci.ensure_p2_migration_zeabur_service"],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "ModuleNotFoundError: No module named 'tools'" not in combined
    assert "No module named 'tools'" not in combined
    assert proc.returncode == 2
    assert "missing_ZEABUR_TOKEN_or_PROJECT_ID" in combined


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

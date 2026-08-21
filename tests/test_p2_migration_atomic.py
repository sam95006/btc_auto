"""P2 migration Zeabur multi-pod TOCTOU: atomic import+apply; stdout is control."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.ci.p2_migration_atomic import (
    ATOMIC_REMOTE_SH,
    MIGRATION_HELPER_PATH,
    PYTHON_STARTED_MARKER,
    STALE_POD_MARKER,
    classify_atomic_exec_output,
    control_decision_from_channels,
    current_pod_shell_gates_pass,
    extract_authoritative_migration_stdout,
    run_atomic_migration_with_stale_retry,
    sanitize_prebootstrap_failure,
    write_authoritative_artifact,
)

# Fixture-only identities — not bound to repository HEAD / GITHUB_SHA.
FIXTURE_CURRENT_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
FIXTURE_OLD_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
WORKFLOW = Path(".github/workflows/founder_approved_staging_postgres_p2_migration.yml")
SAFE = dict(
    postgres_url="postgresql://ledger",
    mainnet="false",
    real_money="false",
    demo_autonomous_enabled="false",
    autonomous_send="false",
    exchange_write="false",
)


def _migration_payload(*, applied: bool = True) -> dict:
    return {
        "P2_MIGRATION_0007_APPLIED_PASS": applied,
        "exchange_write_call_count": 0,
        "create_order_calls": 0,
        "post_migration": {"p2_research_lessons_present": applied},
    }


def _stale_stdout() -> str:
    return (
        "P2_MIGRATION_ATOMIC_EXEC=true\n"
        "P2_MIGRATION_PYTHON_STARTED=false\n"
        + STALE_POD_MARKER
        + "\n"
    )


def _current_pass_stdout(*, applied: bool = True) -> str:
    return (
        "P2_MIGRATION_ATOMIC_EXEC=true\n"
        "P2_MIGRATION_CURRENT_POD_GATES_PASS=true\n"
        + PYTHON_STARTED_MARKER
        + "\nwrapper\n"
        + json.dumps(_migration_payload(applied=applied))
        + "\n"
    )


def test_stale_pod_before_python_allows_retry():
    gate = current_pod_shell_gates_pass(
        expected=FIXTURE_CURRENT_SHA,
        baked=FIXTURE_OLD_SHA,
        source=FIXTURE_OLD_SHA,
        helper_present=True,
        **SAFE,
    )
    assert gate["python_may_start"] is False
    assert gate["stale_pod"] is True
    classified = classify_atomic_exec_output(_stale_stdout())
    assert classified["retry_allowed"] is True
    assert classified["python_started"] is False


def test_current_pod_starts_python_once_in_same_script():
    gate = current_pod_shell_gates_pass(
        expected=FIXTURE_CURRENT_SHA,
        baked=FIXTURE_CURRENT_SHA,
        source=FIXTURE_CURRENT_SHA,
        helper_present=True,
        **SAFE,
    )
    assert gate["python_may_start"] is True
    assert MIGRATION_HELPER_PATH.replace("/app/", "$APP_ROOT/") in ATOMIC_REMOTE_SH
    assert ATOMIC_REMOTE_SH.count("p2_staging_migration_0007") >= 2
    assert "exec python -m tools.ci.p2_staging_migration_0007" in ATOMIC_REMOTE_SH


def test_mismatched_baked_sha_fails_closed():
    gate = current_pod_shell_gates_pass(
        expected=FIXTURE_CURRENT_SHA,
        baked=FIXTURE_OLD_SHA,
        source=FIXTURE_CURRENT_SHA,
        helper_present=True,
        **SAFE,
    )
    assert gate["current_pod"] is False
    assert gate["python_may_start"] is False


def test_helper_missing_on_current_sha_fails_closed():
    gate = current_pod_shell_gates_pass(
        expected=FIXTURE_CURRENT_SHA,
        baked=FIXTURE_CURRENT_SHA,
        source=FIXTURE_CURRENT_SHA,
        helper_present=False,
        **SAFE,
    )
    assert gate["python_may_start"] is False
    assert gate["stale_pod"] is True


def test_mixed_pod_sequence_retries_then_starts_once():
    starts = {"n": 0}

    def exec_attempt(attempt: int) -> dict:
        if attempt < 4:
            return {"stdout": _stale_stdout(), "exit_code": 42}
        starts["n"] += 1
        return {"stdout": _current_pass_stdout(), "exit_code": 0}

    result = run_atomic_migration_with_stale_retry(
        exec_attempt=exec_attempt,
        max_attempts=4,
        sleep=lambda _s: None,
    )
    assert result["migration_started"] is True
    assert result["python_starts"] == 1
    assert starts["n"] == 1
    assert result["attempts"] == 4


def test_no_retry_after_python_starts():
    attempts: list[int] = []

    def exec_attempt(attempt: int) -> dict:
        attempts.append(attempt)
        return {"stdout": _current_pass_stdout(applied=False), "exit_code": 1}

    result = run_atomic_migration_with_stale_retry(
        exec_attempt=exec_attempt,
        max_attempts=3,
        sleep=lambda _s: None,
    )
    assert result["migration_started"] is True
    assert result["python_starts"] == 1
    assert attempts == [1]


def test_migration_stdout_is_authoritative():
    raw = "noise\n" + _current_pass_stdout(applied=True)
    result = extract_authoritative_migration_stdout(raw)
    assert result["authoritative"] is True
    assert result["kind"] == "migration"
    assert result["payload"]["P2_MIGRATION_0007_APPLIED_PASS"] is True
    control = control_decision_from_channels(stdout_result=result, file_payload={"P2_MIGRATION_0007_APPLIED_PASS": False})
    assert control["decision"] == "PASS"
    assert control["file_channel_authoritative"] is False
    assert control["file_channel_override"] is False


def test_file_channel_cannot_override_missing_stdout():
    control = control_decision_from_channels(
        stdout_result={"authoritative": False, "kind": "missing"},
        file_payload={"P2_MIGRATION_0007_APPLIED_PASS": True},
    )
    assert control["decision"] == "HOLD"


def test_prebootstrap_import_failure_is_sanitized(tmp_path: Path):
    raw = (
        f"expected_sha_prefix={FIXTURE_CURRENT_SHA[:12]}\n"
        f"baked_sha_prefix={FIXTURE_CURRENT_SHA[:12]}\n"
        f"source_sha_prefix={FIXTURE_CURRENT_SHA[:12]}\n"
        "helper_present=true\n"
        + json.dumps(
            {
                "P2_MIGRATION_PREBOOTSTRAP_FAILURE": True,
                "stage": "import",
                "exception_type": "ModuleNotFoundError",
                "python_started": False,
            }
        )
    )
    diag = sanitize_prebootstrap_failure(raw)
    assert diag["stage"] == "import"
    assert diag["exception_type"] == "ModuleNotFoundError"
    assert diag["python_started"] is False
    auth = extract_authoritative_migration_stdout(raw)
    assert auth["kind"] == "prebootstrap"
    out = tmp_path / "evidence.json"
    write_authoritative_artifact(auth, out)
    assert not out.exists()
    assert (tmp_path / "p2_migration_prebootstrap_failure.json").exists()


def test_workflow_uses_atomic_same_exec_and_baked_sha():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "nexus-p2m7-${{ github.run_id }}-${{ github.run_attempt }}" in source
    assert "python -m tools.ci.ensure_p2_migration_zeabur_service" in source
    assert "DEPLOYMENT_COMMIT" in source
    assert "SOURCE_COMMIT" in source
    assert "build_migration_context" in source
    assert "P2_MIGRATION_DEPLOYMENT_CONVERGED=true" in source
    assert "p2_migration_atomic.py --print-remote-script" in source
    assert "python -m tools.ci.p2_extract_migration_authoritative_stdout" in source
    assert "python -m tools.ci.p2_migration_parse_service_exec" in source
    assert "file_channel_authoritative=false" in source
    assert "Require migration helper imports before apply" not in source
    assert source.index("Operational service-exec readiness") < source.index(
        "Apply and verify only migration 0007 through atomic same-exec"
    )
    assert "python -m tools.ci.p2_staging_migration_0007" in source
    assert "P2_MIGRATION_SERVICE_EXEC_STDOUT_PASS=true" in source
    assert "P2_MIGRATION_FILE_CHANNEL_AUDIT=true" in source
    assert "P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP=true" in source
    from tools.ci.p2_migration_bootstrap import DOCKERFILE_BODY

    assert "COPY DEPLOYMENT_COMMIT /app/DEPLOYMENT_COMMIT" in DOCKERFILE_BODY
    assert "COPY SOURCE_COMMIT /app/SOURCE_COMMIT" in DOCKERFILE_BODY


def test_local_atomic_script_runs_stale_then_current(tmp_path: Path):
    if os.name == "nt" and not shutil.which("sh"):
        pytest.skip("posix sh unavailable")
    app = tmp_path / "app"
    app.mkdir()
    # First invocation: stale image identity (baked != expected).
    (app / "DEPLOYMENT_COMMIT").write_text(FIXTURE_OLD_SHA + "\n", encoding="ascii")
    (app / "SOURCE_COMMIT").write_text(FIXTURE_OLD_SHA + "\n", encoding="ascii")
    helper_dir = app / "tools" / "ci"
    helper_dir.mkdir(parents=True)
    helper_dir.joinpath("p2_staging_migration_0007.py").write_text("X=1\n", encoding="utf-8")
    script = tmp_path / "atomic.sh"
    script.write_bytes(ATOMIC_REMOTE_SH.replace("\r\n", "\n").encode("utf-8"))
    env = os.environ.copy()
    env.update(
        {
            "EXPECTED": FIXTURE_CURRENT_SHA,
            "APP_ROOT": str(app),
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "NEXUS_POSTGRES_URL": "postgresql://test",
            "MAINNET": "false",
            "REAL_MONEY": "false",
            "DEMO_AUTONOMOUS_ENABLED": "false",
            "AUTONOMOUS_SEND": "false",
            "EXCHANGE_WRITE": "false",
        }
    )
    stale = subprocess.run(["sh", str(script)], capture_output=True, text=True, env=env, check=False)
    assert STALE_POD_MARKER in stale.stdout
    assert "P2_MIGRATION_PYTHON_STARTED=false" in stale.stdout
    assert PYTHON_STARTED_MARKER not in stale.stdout
    # Simulate rollout: rewrite baked identity to current image.
    (app / "DEPLOYMENT_COMMIT").write_text(FIXTURE_CURRENT_SHA + "\n", encoding="ascii")
    (app / "SOURCE_COMMIT").write_text(FIXTURE_CURRENT_SHA + "\n", encoding="ascii")
    current = subprocess.run(["sh", str(script)], capture_output=True, text=True, env=env, check=False)
    assert STALE_POD_MARKER not in current.stdout
    assert PYTHON_STARTED_MARKER in current.stdout or "P2_MIGRATION_PREBOOTSTRAP_FAILURE" in current.stdout


def test_local_atomic_script_current_pod_missing_dsn_is_not_stale(tmp_path: Path):
    if os.name == "nt" and not shutil.which("sh"):
        pytest.skip("posix sh unavailable")
    app = tmp_path / "app"
    app.mkdir()
    (app / "DEPLOYMENT_COMMIT").write_text(FIXTURE_CURRENT_SHA + "\n", encoding="ascii")
    (app / "SOURCE_COMMIT").write_text(FIXTURE_CURRENT_SHA + "\n", encoding="ascii")
    helper_dir = app / "tools" / "ci"
    helper_dir.mkdir(parents=True)
    helper_dir.joinpath("p2_staging_migration_0007.py").write_text("X=1\n", encoding="utf-8")
    script = tmp_path / "atomic.sh"
    script.write_bytes(ATOMIC_REMOTE_SH.replace("\r\n", "\n").encode("utf-8"))
    env = os.environ.copy()
    env.update(
        {
            "EXPECTED": FIXTURE_CURRENT_SHA,
            "APP_ROOT": str(app),
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "NEXUS_POSTGRES_URL": "",
            "MAINNET": "false",
            "REAL_MONEY": "false",
            "DEMO_AUTONOMOUS_ENABLED": "false",
            "AUTONOMOUS_SEND": "false",
            "EXCHANGE_WRITE": "false",
        }
    )
    result = subprocess.run(["sh", str(script)], capture_output=True, text=True, env=env, check=False)
    assert "P2_MIGRATION_ATOMIC_GATE_FAIL=dsn_missing" in result.stdout
    assert "P2_MIGRATION_PYTHON_STARTED=false" in result.stdout
    assert STALE_POD_MARKER not in result.stdout
    assert PYTHON_STARTED_MARKER not in result.stdout

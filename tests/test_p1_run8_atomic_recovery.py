"""Mixed-pod TOCTOU: identity and bootstrap share one exec; stdout is control."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.ci.p1_run8_atomic_recovery import (
    ATOMIC_REMOTE_SH,
    BOOTSTRAP_STARTED_MARKER,
    STALE_POD_MARKER,
    classify_atomic_exec_output,
    control_decision_from_channels,
    current_pod_shell_gates_pass,
    extract_authoritative_run8_stdout,
    run_atomic_recovery_with_stale_retry,
    write_authoritative_artifact,
)
from tools.ci.p1_zeabur_transport import parse_run8_accounting_recovery_evidence

CURRENT = "8bebadb7a2c0e2c1ade81256b543c10b40cb448a"
OLD = "0b74538756f253a5f1060605a89ccc2ff1998158"
WORKFLOW = Path(".github/workflows/founder_approved_bybit_demo_p1_run8_accounting_recovery.yml")
SAFE = dict(
    postgres_url="postgresql://ledger",
    mainnet="false",
    real_money="false",
    demo_autonomous_enabled="false",
    autonomous_send="false",
    exchange_write="false",
)


def _run8_payload(*, verdict: str = "PASS") -> dict:
    return {
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": verdict,
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": "HOLD",
        "recovery_stage": "LEDGER_FINALIZATION" if verdict == "PASS" else "CLOSED_PNL_READ",
        "candidate_count": 1,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "P1_ENTRY_RECONCILIATION_PASS": verdict == "PASS",
        "P1_CLOSE_RECONCILIATION_PASS": verdict == "PASS",
        "P1_EXCHANGE_REALIZED_PNL_PASS": verdict == "PASS",
        "P1_DURABLE_LEDGER_LIFECYCLE_PASS": verdict == "PASS",
        "P1_RUN8_POSITION_FLAT": verdict == "PASS",
        "P1_RUN8_EXACT_CLOSED_PNL_MATCH": verdict == "PASS",
        "P1_RUN8_LEDGER_FINALIZED": verdict == "PASS",
        "entry_read_pass": True,
        "close_read_pass": True,
        "position_flat": True,
        "execution_identity_pass": True,
        "closed_pnl_exact_match": verdict == "PASS",
        "ledger_finalization_pass": verdict == "PASS",
        "error": None if verdict == "PASS" else "exact_closed_pnl_unavailable",
    }


def _bootstrap_payload() -> dict:
    return {
        "BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "HOLD",
        "AUTONOMOUS_BYBIT_DEMO_ARM_READY": "HOLD",
        "recovery_stage": "MODULE_IMPORT",
        "exception_type": "RuntimeError",
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def _stale_stdout() -> str:
    return "P1_RUN8_ATOMIC_EXEC=true\nP1_RUN8_PYTHON_BOOTSTRAP_STARTED=false\n" + STALE_POD_MARKER + "\n"


def _current_pass_stdout() -> str:
    return (
        "P1_RUN8_ATOMIC_EXEC=true\n"
        "P1_RUN8_CURRENT_POD_GATES_PASS=true\n"
        + BOOTSTRAP_STARTED_MARKER
        + "\nwrapper\n"
        + json.dumps(_run8_payload(verdict="PASS"))
        + "\n"
    )


def test_stale_pod_does_not_start_python():
    gate = current_pod_shell_gates_pass(
        expected=CURRENT, baked=OLD, source=OLD, script_present=True, **SAFE
    )
    assert gate["python_may_start"] is False
    assert gate["stale_pod"] is True
    assert gate["create_order_calls"] == 0
    assert gate["exchange_write_call_count"] == 0


def test_current_pod_starts_python_once_in_same_script():
    gate = current_pod_shell_gates_pass(
        expected=CURRENT, baked=CURRENT, source=CURRENT, script_present=True, **SAFE
    )
    assert gate["python_may_start"] is True
    assert "p1_run8_accounting_recovery_bootstrap" in ATOMIC_REMOTE_SH
    assert ATOMIC_REMOTE_SH.index("DEPLOYMENT_COMMIT") < ATOMIC_REMOTE_SH.index(
        "p1_run8_accounting_recovery_bootstrap"
    )
    assert ATOMIC_REMOTE_SH.count("p1_run8_accounting_recovery_bootstrap") == 1
    assert "exec python -m backend.nexus_demo_execution.p1_run8_accounting_recovery_bootstrap" in ATOMIC_REMOTE_SH


def test_mixed_pod_sequence_retries_then_starts_once():
    starts = {"n": 0}

    def exec_attempt(attempt: int) -> dict:
        if attempt < 4:
            return {"stdout": _stale_stdout(), "exit_code": 42}
        starts["n"] += 1
        return {"stdout": _current_pass_stdout(), "exit_code": 1}

    result = run_atomic_recovery_with_stale_retry(exec_attempt=exec_attempt, sleep=lambda _s: None)
    assert result["recovery_started"] is True
    assert result["python_bootstrap_starts"] == 1
    assert starts["n"] == 1
    assert result["attempts"] == 4
    assert result["history"][0]["retry_allowed"] is True
    assert result["create_order_calls"] == 0
    assert result["exchange_write_call_count"] == 0


def test_no_retry_after_bootstrap_even_if_transport_nonzero():
    calls = {"n": 0}

    def exec_attempt(_attempt: int) -> dict:
        calls["n"] += 1
        return {"stdout": _current_pass_stdout(), "exit_code": 17}

    result = run_atomic_recovery_with_stale_retry(exec_attempt=exec_attempt, sleep=lambda _s: None)
    assert calls["n"] == 1
    assert result["retry_after_bootstrap"] is False
    assert result["python_bootstrap_starts"] == 1
    extracted = extract_authoritative_run8_stdout(result["stdout"])
    assert extracted["decision"] == "PASS"
    assert extracted["authoritative"] is True


def test_valid_pass_stdout_missing_file_stays_pass():
    stdout = extract_authoritative_run8_stdout(_current_pass_stdout())
    decision = control_decision_from_channels(
        stdout_result=stdout, file_http_status=200, file_bytes=0, file_payload=None
    )
    assert stdout["decision"] == "PASS"
    assert decision["decision"] == "PASS"
    assert decision["file_channel_override"] is False


def test_valid_hold_stdout_missing_file_stays_hold():
    stdout = extract_authoritative_run8_stdout("wrapper\n" + json.dumps(_run8_payload(verdict="HOLD")))
    decision = control_decision_from_channels(stdout_result=stdout, file_http_status=404, file_bytes=0)
    assert stdout["decision"] == "HOLD"
    assert decision["decision"] == "HOLD"


def test_malformed_stdout_holds_and_never_infers_pass():
    stdout = extract_authoritative_run8_stdout("zeabur service exec ok\nnot json")
    decision = control_decision_from_channels(
        stdout_result=stdout,
        file_http_status=200,
        file_bytes=12,
        file_payload={"BYBIT_DEMO_SINGLE_TRADE_E2E_PASS": "PASS"},
    )
    assert stdout["authoritative"] is False
    assert decision["decision"] == "HOLD"
    assert decision["file_channel_override"] is False


def test_local_github_artifact_is_written_from_validated_stdout(tmp_path: Path):
    destination = tmp_path / "artifacts" / "bybit_demo_p1" / "p1_run8_accounting_recovery_evidence.json"
    result = extract_authoritative_run8_stdout(_current_pass_stdout())
    written = write_authoritative_artifact(result, destination)
    assert written == destination
    parsed = parse_run8_accounting_recovery_evidence(destination.read_text(encoding="utf-8"))
    assert parsed["BYBIT_DEMO_SINGLE_TRADE_E2E_PASS"] == "PASS"
    control = json.loads((destination.parent / "p1_run8_control_decision.json").read_text(encoding="utf-8"))
    assert control["control_decision"] == "PASS"
    assert control["file_channel_authoritative"] is False


def test_workflow_has_no_separate_exec_between_identity_and_bootstrap():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Probe baked container code identity" not in source
    recover = source.index("Perform read-only exchange and ledger recovery")
    upload = source.index("Upload sanitized recovery evidence")
    block = source[recover:upload]
    assert "P1_RUN8_EXEC_POD_NOT_CURRENT=true" in block
    assert "P1_RUN8_PYTHON_BOOTSTRAP_STARTED=true" in block
    assert "p1_run8_accounting_recovery_bootstrap" in block
    assert "p1_extract_run8_authoritative_stdout.py" in block
    assert "file_channel_authoritative=false" in block
    assert block.count("zeabur service exec") == 1
    assert "/bin/sh /app/p1_run8_baked_identity_probe.sh" not in source
    deploy = source.index("Deploy disarmed recovery-capable validation image")
    converge = source.index("Wait for current-image rollout convergence")
    ready = source.index("Require final validation runtime readiness")
    transport = source.index("Prove service-exec and file-download share the current filesystem")
    assert deploy < converge < ready < transport < recover
    assert "rollout_convergence_is_advisory=true" in source


def test_bootstrap_json_in_stdout_is_hold_and_not_retried():
    noisy = "noise\n" + json.dumps(_bootstrap_payload()) + "\n" + BOOTSTRAP_STARTED_MARKER
    extracted = extract_authoritative_run8_stdout(noisy)
    assert extracted["kind"] == "bootstrap"
    assert extracted["decision"] == "HOLD"
    classified = classify_atomic_exec_output(noisy)
    assert classified["retry_allowed"] is False
    assert classified["bootstrap_started"] is True


def test_posix_stale_image_does_not_exec_python(tmp_path: Path):
    git_sh = Path(r"C:\Program Files\Git\bin\sh.exe")
    sh_bin = str(git_sh) if git_sh.is_file() else shutil.which("sh")
    if not sh_bin:
        pytest.skip("POSIX sh required")
    app = tmp_path / "app"
    app.mkdir()
    (app / "DEPLOYMENT_COMMIT").write_text(OLD + "\n", encoding="ascii")
    (app / "SOURCE_COMMIT").write_text(OLD + "\n", encoding="ascii")
    (app / "p1_run8_baked_identity_probe.sh").write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
    marker = tmp_path / "python_started"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_py = fake_bin / "python"
    fake_py.write_text("#!/bin/sh\necho started > \"$1\"\n", encoding="ascii")
    fake_py.write_text(
        "#!/bin/sh\nprintf started > '" + marker.as_posix().replace("'", "") + "'\nexit 0\n",
        encoding="ascii",
    )
    script = tmp_path / "atomic.sh"
    script.write_bytes(ATOMIC_REMOTE_SH.replace("\r\n", "\n").encode("utf-8"))

    def posix(path: Path) -> str:
        text = str(path.resolve())
        if len(text) >= 2 and text[1] == ":":
            return "/" + text[0].lower() + text[2:].replace("\\", "/")
        return text.replace("\\", "/")

    env = os.environ.copy()
    env["EXPECTED"] = CURRENT
    env["APP_ROOT"] = posix(app)
    env["NEXUS_POSTGRES_URL"] = "postgresql://ledger"
    env["MAINNET"] = "false"
    env["REAL_MONEY"] = "false"
    env["DEMO_AUTONOMOUS_ENABLED"] = "false"
    env["AUTONOMOUS_SEND"] = "false"
    env["EXCHANGE_WRITE"] = "false"
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    ran = subprocess.run([sh_bin, posix(script)], capture_output=True, text=True, check=False, env=env)
    assert ran.returncode == 42, ran.stdout + ran.stderr
    assert STALE_POD_MARKER in ran.stdout
    assert BOOTSTRAP_STARTED_MARKER not in ran.stdout
    assert not marker.exists()

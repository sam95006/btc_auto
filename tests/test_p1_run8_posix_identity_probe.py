"""Execute the Run #8 identity probe under /bin/sh, not YAML static search only."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.nexus_demo_execution.p1_run8_accounting_recovery import evaluate_run8_baked_code_identity

WORKFLOW = Path(".github/workflows/founder_approved_bybit_demo_p1_run8_accounting_recovery.yml")
SCRIPT = Path("tools/ci/p1_run8_baked_identity_probe.sh")
CURRENT = "a6c1ddcab1be6f21f5492cfab308d98d4890bfbf"
STALE = "000000000000bbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _sh_bin() -> str:
    git_sh = Path(r"C:\Program Files\Git\bin\sh.exe")
    if git_sh.is_file():
        return str(git_sh)
    found = shutil.which("sh")
    if found:
        return found
    pytest.skip("POSIX sh is required for identity probe execution tests")


def _posix(path: Path) -> str:
    text = str(path.resolve())
    if len(text) >= 2 and text[1] == ":":
        return "/" + text[0].lower() + text[2:].replace("\\", "/")
    return text.replace("\\", "/")


def _run_probe(tmp_path: Path, *, expected: str, baked: str | None = None, source: str | None = None, omit: str | None = None):
    app = tmp_path / "app"
    app.mkdir()
    body = SCRIPT.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    script = app / "p1_run8_baked_identity_probe.sh"
    script.write_bytes(body)
    if omit != "baked":
        (app / "DEPLOYMENT_COMMIT").write_bytes(((baked if baked is not None else expected) + "\n").encode("ascii"))
    if omit != "source":
        (app / "SOURCE_COMMIT").write_bytes(((source if source is not None else expected) + "\n").encode("ascii"))
    app_posix = _posix(app)
    script_posix = _posix(script)
    command = f"export EXPECTED='{expected}'; export APP_ROOT='{app_posix}'; /bin/sh '{script_posix}'"
    return subprocess.run([_sh_bin(), "-lc", command], capture_output=True, text=True, check=False)


def test_posix_probe_match_exits_zero(tmp_path: Path):
    result = _run_probe(tmp_path, expected=CURRENT)
    assert result.returncode == 0, result.stderr
    assert "P1_RUN8_BAKED_IDENTITY_PASS=true" in result.stdout
    assert f"expected_sha_prefix={CURRENT[:12]}" in result.stdout


def test_posix_probe_stale_baked_nonzero(tmp_path: Path):
    result = _run_probe(tmp_path, expected=CURRENT, baked=STALE, source=CURRENT)
    assert result.returncode != 0


def test_posix_probe_stale_source_nonzero(tmp_path: Path):
    result = _run_probe(tmp_path, expected=CURRENT, baked=CURRENT, source=STALE)
    assert result.returncode != 0


def test_posix_probe_missing_file_nonzero(tmp_path: Path):
    result = _run_probe(tmp_path, expected=CURRENT, omit="baked")
    assert result.returncode != 0


def test_workflow_and_script_have_no_bash_substring():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    for blob in (workflow, script):
        assert "${BAKED:0:12}" not in blob
        assert "${SOURCE:0:12}" not in blob
        assert "${EXPECTED:0:12}" not in blob
        assert "${VAR:0:12}" not in blob
    assert "COPY p1_run8_baked_identity_probe.sh /app/p1_run8_baked_identity_probe.sh" in workflow
    assert "/bin/sh /app/p1_run8_baked_identity_probe.sh" not in workflow
    assert "cut -c1-12" in script


def test_python_identity_requires_full_sha_equality(monkeypatch):
    monkeypatch.setenv("NEXUS_EXPECTED_SHA", CURRENT)
    monkeypatch.setattr(
        "backend.nexus_demo_execution.p1_run8_accounting_recovery.read_container_baked_commit",
        lambda: (CURRENT, "file:/app/DEPLOYMENT_COMMIT"),
    )
    monkeypatch.setattr(
        "backend.nexus_demo_execution.p1_run8_accounting_recovery.read_container_source_commit",
        lambda: (CURRENT, "file:/app/SOURCE_COMMIT"),
    )
    ok = evaluate_run8_baked_code_identity()
    assert ok["runtime_code_identity_pass"] is True
    monkeypatch.setattr(
        "backend.nexus_demo_execution.p1_run8_accounting_recovery.read_container_baked_commit",
        lambda: (CURRENT[:12], "file:/app/DEPLOYMENT_COMMIT"),
    )
    short = evaluate_run8_baked_code_identity()
    assert short["runtime_code_identity_pass"] is False
    assert short["error"] == "malformed_sha"

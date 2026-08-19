"""Run #8 rollout convergence: stale image retries; recovery only after current image."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.ci.p1_run8_rollout_convergence import (
    INLINE_IMAGE_PROBE_SH,
    ImageProbeSnapshot,
    current_image_ready,
    wait_for_current_image,
)

CURRENT = "0b74538756f253a5f1060605a89ccc2ff1998158"
OLD = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WORKFLOW = Path(".github/workflows/founder_approved_bybit_demo_p1_run8_accounting_recovery.yml")


def test_old_image_without_script_is_not_current():
    snap = ImageProbeSnapshot(expected=CURRENT, baked=OLD, source=OLD, script_present=False)
    assert current_image_ready(snap) is False


def test_current_sha_without_script_is_not_current():
    snap = ImageProbeSnapshot(expected=CURRENT, baked=CURRENT, source=CURRENT, script_present=False)
    assert current_image_ready(snap) is False


def test_current_sha_with_script_is_current():
    snap = ImageProbeSnapshot(expected=CURRENT, baked=CURRENT, source=CURRENT, script_present=True)
    assert current_image_ready(snap) is True


def test_rollout_sequence_retries_then_converges():
    snapshots = [
        ImageProbeSnapshot(expected=CURRENT, baked=OLD, source=OLD, script_present=False),
        ImageProbeSnapshot(expected=CURRENT, baked=OLD, source=OLD, script_present=False),
        ImageProbeSnapshot(expected=CURRENT, baked=CURRENT, source=CURRENT, script_present=False),
        ImageProbeSnapshot(expected=CURRENT, baked=CURRENT, source=CURRENT, script_present=True),
        ImageProbeSnapshot(expected=CURRENT, baked=CURRENT, source=CURRENT, script_present=True),
        ImageProbeSnapshot(expected=CURRENT, baked=CURRENT, source=CURRENT, script_present=True),
    ]
    calls = {"n": 0}

    def probe(_attempt: int) -> ImageProbeSnapshot:
        idx = min(calls["n"], len(snapshots) - 1)
        calls["n"] += 1
        return snapshots[idx]

    sleeps: list[float] = []
    result = wait_for_current_image(
        probe=probe,
        max_attempts=36,
        consecutive_needed=3,
        retry_interval_sec=5,
        consecutive_gap_sec=2,
        sleep=sleeps.append,
    )
    assert result["converged"] is True
    assert result["recovery_may_run"] is True
    assert result["attempts"] == 6
    assert result["create_order_calls"] == 0
    assert result["exchange_write_call_count"] == 0
    assert calls["n"] == 6
    assert result["history"][0]["current_image"] is False
    assert result["history"][2]["current_image"] is False
    assert [row["current_image"] for row in result["history"][3:]] == [True, True, True]


def test_rollout_timeout_does_not_run_recovery():
    def probe(_attempt: int) -> ImageProbeSnapshot:
        return ImageProbeSnapshot(expected=CURRENT, baked=OLD, source=OLD, script_present=False)

    recovery_executed = False

    def maybe_recover(converged: bool) -> None:
        nonlocal recovery_executed
        if converged:
            recovery_executed = True

    result = wait_for_current_image(
        probe=probe,
        max_attempts=4,
        consecutive_needed=3,
        sleep=lambda _s: None,
    )
    maybe_recover(result["converged"])
    assert result["converged"] is False
    assert result["recovery_may_run"] is False
    assert result["error"] == "rollout_timeout"
    assert recovery_executed is False
    assert result["create_order_calls"] == 0
    assert result["exchange_write_call_count"] == 0


def test_workflow_order_converges_before_readiness_and_recovery():
    source = WORKFLOW.read_text(encoding="utf-8")
    deploy = source.index("Deploy disarmed recovery-capable validation image")
    converge = source.index("Wait for current-image rollout convergence")
    ready = source.index("Require final validation runtime readiness")
    transport = source.index("Prove service-exec and file-download share the current filesystem")
    recovery = source.index("Perform read-only exchange and ledger recovery")
    assert deploy < converge < ready < transport < recovery
    assert "Probe baked container code identity" not in source
    assert "P1_RUN8_DEPLOYMENT_CONVERGED=true" in source
    assert "ROLLOUT_NOT_CONVERGED_YET" in source
    assert source.index("P1_RUN8_DEPLOYMENT_CONVERGED=true") < source.index("P1_VALIDATION_SERVICE_RUNTIME_READY=true")
    assert "/app/p1_run8_baked_identity_probe.sh" in source
    wait_block = source[converge:ready]
    assert "[ -f /app/p1_run8_baked_identity_probe.sh ]" in wait_block
    assert "/bin/sh /app/p1_run8_baked_identity_probe.sh" not in wait_block


def test_inline_probe_script_is_posix_and_independent_of_new_helper(tmp_path: Path):
    sh = shutil.which("sh") or r"C:\Program Files\Git\bin\sh.exe"
    if not Path(sh).exists() and shutil.which("sh") is None:
        pytest.skip("POSIX sh required")
    git_sh = Path(r"C:\Program Files\Git\bin\sh.exe")
    sh_bin = str(git_sh) if git_sh.is_file() else shutil.which("sh")
    if not sh_bin:
        pytest.skip("POSIX sh required")
    app = tmp_path / "app"
    app.mkdir()
    (app / "DEPLOYMENT_COMMIT").write_text(CURRENT + "\n", encoding="ascii")
    (app / "SOURCE_COMMIT").write_text(CURRENT + "\n", encoding="ascii")
    (app / "p1_run8_baked_identity_probe.sh").write_text("#!/bin/sh\nexit 0\n", encoding="ascii")
    script = tmp_path / "inline.sh"
    script.write_bytes(("#!/bin/sh\nset -e\n" + INLINE_IMAGE_PROBE_SH.strip() + "\n").replace("\r\n", "\n").encode("utf-8"))

    def posix(path: Path) -> str:
        text = str(path.resolve())
        if len(text) >= 2 and text[1] == ":":
            return "/" + text[0].lower() + text[2:].replace("\\", "/")
        return text.replace("\\", "/")

    env = os.environ.copy()
    env["EXPECTED"] = CURRENT
    env["APP_ROOT"] = posix(app)
    ok = subprocess.run([sh_bin, posix(script)], capture_output=True, text=True, check=False, env=env)
    assert ok.returncode == 0, ok.stderr + ok.stdout
    (app / "DEPLOYMENT_COMMIT").write_text(OLD + "\n", encoding="ascii")
    bad = subprocess.run([sh_bin, posix(script)], capture_output=True, text=True, check=False, env=env)
    assert bad.returncode != 0

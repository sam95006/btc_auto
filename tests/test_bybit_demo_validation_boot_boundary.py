from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy" / "zeabur_bybit_demo_validation"


def test_validation_entrypoint_uses_minimal_health_server_and_disarms() -> None:
    entrypoint = (DEPLOY / "entrypoint.sh").read_text(encoding="utf-8")
    assert "export DEMO_AUTONOMOUS_ENABLED=false" in entrypoint
    assert "export AUTONOMOUS_SEND=false" in entrypoint
    assert "export EXCHANGE_WRITE=false" in entrypoint
    assert "exec python ./validation_health_server.py" in entrypoint
    assert "gunicorn" not in entrypoint
    assert "app:app" not in entrypoint


def test_validation_dockerfile_excludes_full_web_boot_dependencies() -> None:
    dockerfile = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY backend/ backend/" in dockerfile
    assert "validation_health_server.py" in dockerfile
    assert "COPY static/" not in dockerfile
    assert "COPY templates/" not in dockerfile
    assert "app.py run.py" not in dockerfile
    assert "gunicorn.conf.py" not in dockerfile


def test_p1_modules_import_without_web_application_boot() -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    command = [
        sys.executable,
        "-c",
        (
            "import backend.nexus_demo_execution.p1_recovery; "
            "import backend.nexus_demo_execution.p1_qualification"
        ),
    ]
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_health_server_reports_disarmed_flags() -> None:
    port = 18991
    env = {
        **os.environ,
        "PORT": str(port),
        "MAINNET": "false",
        "REAL_MONEY": "false",
        "DEMO_AUTONOMOUS_ENABLED": "false",
        "EXCHANGE_WRITE": "false",
    }
    process = subprocess.Popen(
        [sys.executable, str(DEPLOY / "validation_health_server.py")],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(20):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.25) as response:
                    payload = json.loads(response.read())
                break
            except OSError:
                time.sleep(0.05)
        else:
            raise AssertionError(process.stderr.read().decode("utf-8", errors="replace"))
        assert payload == {
            "ok": True,
            "service": "nexus-bybit-demo-learning-validation",
            "mode": "BYBIT_DEMO_VALIDATION",
            "mainnet": False,
            "real_money": False,
            "demo_autonomous_enabled": False,
            "exchange_write": False,
        }
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_p1_workflows_require_final_runtime_readiness_before_transport_probe() -> None:
    for name in (
        "founder_approved_bybit_demo_p1_run2_recovery.yml",
        "founder_approved_bybit_demo_p1_qualification.yml",
    ):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        assert "P1_VALIDATION_SERVICE_RUNTIME_READY=true" in workflow
        assert "echo P1_VALIDATION_CONTAINER_READY" in workflow
        assert workflow.index("P1_VALIDATION_SERVICE_RUNTIME_READY=true") < workflow.index("Prove service-exec")


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker is required for container smoke coverage")
def test_validation_container_boots_disarmed_and_imports_p1_modules() -> None:
    image = "nexus-bybit-demo-validation-smoke"
    port = 18992
    build = subprocess.run(
        ["docker", "build", "-f", str(DEPLOY / "Dockerfile"), "-t", image, "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    container = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-p",
            f"{port}:8080",
            "-e",
            "MAINNET=false",
            "-e",
            "REAL_MONEY=false",
            "-e",
            "DEMO_AUTONOMOUS_ENABLED=false",
            "-e",
            "AUTONOMOUS_SEND=false",
            "-e",
            "EXCHANGE_WRITE=false",
            image,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert container.returncode == 0, container.stderr
    container_id = container.stdout.strip()
    try:
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                    payload = json.loads(response.read())
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise AssertionError("validation container did not serve /health")
        assert payload["ok"] is True
        assert all(payload[flag] is False for flag in ("mainnet", "real_money", "demo_autonomous_enabled", "exchange_write"))
        imports = subprocess.run(
            [
                "docker",
                "exec",
                container_id,
                "python",
                "-c",
                "import backend.nexus_demo_execution.p1_recovery; import backend.nexus_demo_execution.p1_qualification",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert imports.returncode == 0, imports.stderr
    finally:
        subprocess.run(["docker", "stop", container_id], capture_output=True, check=False)

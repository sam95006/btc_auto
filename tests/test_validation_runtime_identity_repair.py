"""Validation runtime identity repair: build SHA bake + fail-closed lease."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.nexus_bounded_runtime import runtime_lease

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy" / "zeabur_bybit_demo_validation" / "resolve_deployment_identity.sh"
FULL_DOCKERFILE = ROOT / "deploy" / "zeabur_bybit_demo_validation" / "Dockerfile.full_engine"
MINIMAL_DOCKERFILE = ROOT / "deploy" / "zeabur_bybit_demo_validation" / "Dockerfile"

GOOD_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
WRONG_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
SHA_ENV_KEYS = (
    "NEXUS_DEPLOYMENT_COMMIT",
    "NEXUS_SOURCE_COMMIT",
    "GITHUB_SHA",
    "ZEABUR_GIT_COMMIT_SHA",
    "ZEABUR_ENV_GITHUB_SHA",
    "ZEABUR_ENV_ZEABUR_GIT_COMMIT_SHA",
    "SOURCE_COMMIT",
)


def _sh() -> str:
    candidates = [
        str(path)
        for path in (
            Path("C:/Program Files/Git/usr/bin/sh.exe"),
            Path("C:/Program Files/Git/bin/bash.exe"),
        )
        if path.exists()
    ]
    candidates.extend(
        shell
        for shell in (shutil.which("sh"), shutil.which("bash"))
        if shell and "WindowsApps" not in shell
    )
    for shell in candidates:
        if not shell:
            continue
        probe = subprocess.run([shell, "-c", "true"], capture_output=True, text=True)
        if probe.returncode == 0:
            return shell
    pytest.skip("POSIX shell not available")


def _run_script(tmp_path: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    shell = _sh()
    child_env = dict(os.environ)
    for key in SHA_ENV_KEYS:
        child_env.pop(key, None)
    child_env.update(env or {})
    child_env["PATH"] = str(Path(shell).parent) + os.pathsep + child_env.get("PATH", "")
    return subprocess.run(
        [shell, str(SCRIPT), "write"],
        cwd=tmp_path,
        env=child_env,
        text=True,
        capture_output=True,
        check=True,
    )


def test_build_sha_available_bakes_identity_files(tmp_path: Path) -> None:
    _run_script(tmp_path, env={"ZEABUR_GIT_COMMIT_SHA": GOOD_SHA})
    assert (tmp_path / "DEPLOYMENT_COMMIT").read_text(encoding="utf-8").strip() == GOOD_SHA
    assert (tmp_path / "SOURCE_COMMIT").read_text(encoding="utf-8").strip() == GOOD_SHA


def test_missing_build_sha_writes_empty_identity_files(tmp_path: Path) -> None:
    _run_script(tmp_path, env={"GITHUB_SHA": "", "ZEABUR_GIT_COMMIT_SHA": ""})
    assert (tmp_path / "DEPLOYMENT_COMMIT").read_text(encoding="utf-8") == ""
    assert (tmp_path / "SOURCE_COMMIT").read_text(encoding="utf-8") == ""


def test_dockerfiles_accept_zeabur_build_phase_sha_aliases() -> None:
    for dockerfile in (FULL_DOCKERFILE, MINIMAL_DOCKERFILE):
        text = dockerfile.read_text(encoding="utf-8")
        assert "ARG ZEABUR_GIT_COMMIT_SHA" in text
        assert "ARG ZEABUR_ENV_ZEABUR_GIT_COMMIT_SHA" in text
        assert "resolve_deployment_identity.sh write" in text
        assert "1a8b38a6193b75ee59c31ff90a63069aad116662" not in text


def test_runtime_lease_correct_deployed_sha_permits_validation_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.nexus_demo_execution.runtime_identity.read_container_baked_commit",
        lambda: (GOOD_SHA, "file:/app/DEPLOYMENT_COMMIT"),
    )
    assert runtime_lease.validate_runtime_sha(expected=GOOD_SHA, deployed=runtime_lease.runtime_sha())["ok"] is True


def test_runtime_lease_wrong_sha_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.nexus_demo_execution.runtime_identity.read_container_baked_commit",
        lambda: (WRONG_SHA, "file:/app/DEPLOYMENT_COMMIT"),
    )
    result = runtime_lease.validate_runtime_sha(expected=GOOD_SHA, deployed=runtime_lease.runtime_sha())
    assert result == {"ok": False, "reason": "runtime_sha_mismatch"}


def test_runtime_lease_no_sha_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.nexus_demo_execution.runtime_identity.read_container_baked_commit",
        lambda: ("", "missing"),
    )
    for key in SHA_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    result = runtime_lease.validate_runtime_sha(expected=GOOD_SHA, deployed=runtime_lease.runtime_sha())
    assert result == {"ok": False, "reason": "deployed_runtime_sha_missing"}

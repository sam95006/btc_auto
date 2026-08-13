"""P0.3 packaging — promotion analyzer must enter the Zeabur image."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANALYZER = ROOT / "tools" / "research" / "run_promotion_review_candidate.py"


def test_analyzer_source_exists() -> None:
    assert ANALYZER.is_file()


def test_dockerignore_excludes_research_but_allowlists_analyzer() -> None:
    text = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    # Parent-dir ban would block exceptions — must not use bare tools/research/
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        assert stripped != "tools/research/", (
            "bare tools/research/ in .dockerignore blocks allow-list exceptions"
        )
    assert "tools/research/*" in text
    assert "!tools/research/run_promotion_review_candidate.py" in text


def test_dockerfile_asserts_analyzer_present() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "/app/tools/research/run_promotion_review_candidate.py" in text
    assert "MISSING promotion review analyzer" in text


def test_deploy_workflow_includes_packaging_paths() -> None:
    text = (ROOT / ".github" / "workflows" / "nexus_deploy_zeabur_on_main.yml").read_text(
        encoding="utf-8"
    )
    assert "Dockerfile" in text
    assert ".dockerignore" in text
    assert "tools/research/run_promotion_review_candidate.py" in text


def test_analyzer_help_starts() -> None:
    proc = subprocess.run(
        [sys.executable, str(ANALYZER), "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "campaign-root" in (proc.stdout + proc.stderr)


def test_no_demo_write_defaults_in_dockerfile() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "EXCHANGE_WRITE=false" in text
    assert "NEXUS_AUTONOMY_EXCHANGE_WRITE=false" in text
    assert "MAINNET=false" in text
    assert "REAL_MONEY=false" in text


def test_docker_build_context_includes_analyzer() -> None:
    """Best-effort: if docker is available, verify file survives ignore rules via build."""
    try:
        subprocess.run(["docker", "version"], capture_output=True, check=True, timeout=15)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        # Packaging rules + Dockerfile assertion still cover CI/image; skip local docker.
        return

    # Use a tiny build that only COPYs after ignore — full image build is heavy;
    # instead list context with BuildKit / docker build dry approach via stdin Dockerfile.
    df = """
FROM busybox:1.36
WORKDIR /app
COPY tools/research/run_promotion_review_candidate.py /app/tools/research/run_promotion_review_candidate.py
RUN test -f /app/tools/research/run_promotion_review_candidate.py
"""
    tag = "nexus-promotion-analyzer-ctx-check"
    proc = subprocess.run(
        ["docker", "build", "-t", tag, "-f", "-", "."],
        cwd=str(ROOT),
        input=df,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    # cleanup best-effort
    subprocess.run(["docker", "rmi", "-f", tag], capture_output=True, check=False)

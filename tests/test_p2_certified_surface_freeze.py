"""Certified-surface freeze check for P2 migration diagnostics-only commits."""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Paths that must not change during transport/diagnostics hardening.
FORBIDDEN_PREFIXES = (
    "backend/nexus_demo_execution/",
    "backend/nexus_persistence_pg/migrations/0001_",
    "backend/nexus_persistence_pg/migrations/0002_",
    "backend/nexus_persistence_pg/migrations/0003_",
    "backend/nexus_persistence_pg/migrations/0004_",
    "backend/nexus_persistence_pg/migrations/0005_",
    "backend/nexus_persistence_pg/migrations/0006_",
    ".github/workflows/founder_approved_bybit_demo_p1_",
    ".github/workflows/founder_approved_staging_postgres_p1_migration.yml",
    "backend/bybit/",
    "tools/ci/p2_1_postgres_qualification.py",
)

# Accepted diagnostics baseline (historical lock + initial diagnostics).
BASELINE_SHA = "bce441792de7e36264f706ab80c0273bad386060"


def _git(*args: str) -> list[str]:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line.strip().replace("\\", "/") for line in proc.stdout.splitlines() if line.strip()]


def _is_noise(path: str) -> bool:
    return (
        "/__pycache__/" in f"/{path}/"
        or path.endswith(".pyc")
        or path.endswith(".pyo")
        or "/.pytest_cache/" in f"/{path}/"
    )


def _is_forbidden(path: str) -> bool:
    if _is_noise(path):
        return False
    return any(path.startswith(prefix) or path == prefix.rstrip("/") for prefix in FORBIDDEN_PREFIXES)


def test_diagnostics_scope_does_not_touch_forbidden_certified_surfaces():
    # Content diffs only (avoids CRLF-only porcelain false positives).
    changed = set(_git("diff", "--name-only", f"{BASELINE_SHA}..HEAD"))
    changed.update(_git("diff", "--name-only", "HEAD"))
    changed.update(_git("diff", "--name-only", "--cached"))
    changed.update(_git("ls-files", "--others", "--exclude-standard"))
    violations = sorted(path for path in changed if _is_forbidden(path))
    assert violations == [], f"certified surfaces modified outside diagnostics scope: {violations}"

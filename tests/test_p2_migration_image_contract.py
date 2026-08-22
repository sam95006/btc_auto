"""Static contract for P2 migration one-shot image (no live deploy)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.ci.p2_migration_bootstrap import DOCKERFILE_BODY, build_migration_context, validate_migration_context

ROOT = Path(__file__).resolve().parents[1]
ENTRY = (ROOT / "deploy" / "zeabur_p2_migration_0007" / "entrypoint.sh").read_text(encoding="utf-8")
HEALTH = ROOT / "deploy" / "zeabur_p2_migration_0007" / "migration_health_server.py"
SHA = "c5add473bdc047ad57f21763b381396e3599dbad"


def test_entrypoint_binds_all_interfaces_and_uses_port_env():
    assert "bind_host=0.0.0.0" in ENTRY
    assert 'PORT_RESOLVED="${PORT:-}"' in ENTRY
    assert "exec python ./migration_health_server.py" in ENTRY
    assert "EXCHANGE_WRITE=false" in ENTRY
    assert "MAINNET" in ENTRY


def test_dockerfile_defaults_disarmed_and_uses_isolated_migration_requirements():
    assert "MAINNET=false" in DOCKERFILE_BODY
    assert "REAL_MONEY=false" in DOCKERFILE_BODY
    assert "DEMO_AUTONOMOUS_ENABLED=false" in DOCKERFILE_BODY
    assert "AUTONOMOUS_SEND=false" in DOCKERFILE_BODY
    assert "EXCHANGE_WRITE=false" in DOCKERFILE_BODY
    assert "NEXUS_POSTGRES_URL" not in DOCKERFILE_BODY
    assert "requirements-migration.txt" in DOCKERFILE_BODY
    assert "COPY requirements.txt" not in DOCKERFILE_BODY
    assert "COPY DEPLOYMENT_COMMIT /app/DEPLOYMENT_COMMIT" in DOCKERFILE_BODY
    assert "COPY SOURCE_COMMIT /app/SOURCE_COMMIT" in DOCKERFILE_BODY
    mig_req = (ROOT / "deploy" / "zeabur_p2_migration_0007" / "requirements-migration.txt").read_text(
        encoding="utf-8"
    )
    assert "psycopg" in mig_req
    global_req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "requirements-migration.txt" not in global_req


def test_health_metadata_is_run_scoped_or_generic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Import freshly from deploy path via PYTHONPATH-style load.
    import importlib.util

    spec = importlib.util.spec_from_file_location("migration_health_server", HEALTH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.delenv("P2_MIGRATION_SERVICE_NAME", raising=False)
    monkeypatch.delenv("SERVICE_NAME", raising=False)
    assert mod._service_name() == "nexus-p2-migration"
    monkeypatch.setenv("P2_MIGRATION_SERVICE_NAME", "nexus-p2m7-8-1")
    assert mod._service_name() == "nexus-p2m7-8-1"


def test_built_context_contains_helper_and_commit_files(tmp_path: Path):
    ctx = build_migration_context(repo_root=ROOT, destination=tmp_path / "ctx", github_sha=SHA)
    meta = validate_migration_context(ctx, expected_sha=SHA)
    assert meta["helper_present"] is True
    assert meta["dsn_baked_in_image"] is False
    assert (ctx / "migration_health_server.py").is_file()
    assert (ctx / "entrypoint.sh").is_file()
    assert meta["exchange_write_call_count"] == 0


@pytest.mark.skipif(os.name == "nt" and not Path("/").exists(), reason="posix container smoke optional")
def test_health_server_module_imports_without_exchange_side_effects():
    env = {**os.environ, "MAINNET": "false", "EXCHANGE_WRITE": "false"}
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib.util; "
            f"p=r'{HEALTH.as_posix()}'; "
            "s=importlib.util.spec_from_file_location('m', p); m=importlib.util.module_from_spec(s); "
            "s.loader.exec_module(m); assert m._false('EXCHANGE_WRITE') is False",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

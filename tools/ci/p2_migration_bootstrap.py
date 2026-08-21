"""P2 migration single-deploy bootstrap planning and context validation (no secrets)."""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

DOCKERFILE_BODY = """FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app MAINNET=false REAL_MONEY=false DEMO_AUTONOMOUS_ENABLED=false AUTONOMOUS_SEND=false EXCHANGE_WRITE=false NEXUS_DATA_DIR=/tmp/nexus_p2_migration_0007 PORT=8080
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY DEPLOYMENT_COMMIT /app/DEPLOYMENT_COMMIT
COPY SOURCE_COMMIT /app/SOURCE_COMMIT
RUN chmod +x entrypoint.sh
CMD ["/bin/sh", "./entrypoint.sh"]
"""


def build_migration_context(*, repo_root: Path, destination: Path, github_sha: str) -> Path:
    sha = (github_sha or "").strip()
    if not sha:
        raise ValueError("github_sha_missing")
    root = Path(repo_root)
    dest = Path(destination)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / "tools").mkdir(parents=True)
    shutil.copy2(root / "requirements.txt", dest / "requirements.txt")
    shutil.copytree(root / "backend", dest / "backend")
    shutil.copytree(root / "config", dest / "config")
    shutil.copytree(root / "tools" / "ci", dest / "tools" / "ci")
    shutil.copy2(root / "deploy" / "zeabur_p2_migration_0007" / "entrypoint.sh", dest / "entrypoint.sh")
    shutil.copy2(
        root / "deploy" / "zeabur_p2_migration_0007" / "migration_health_server.py",
        dest / "migration_health_server.py",
    )
    (dest / "DEPLOYMENT_COMMIT").write_text(sha + "\n", encoding="ascii")
    (dest / "SOURCE_COMMIT").write_text(sha + "\n", encoding="ascii")
    (dest / "Dockerfile").write_text(DOCKERFILE_BODY, encoding="utf-8")
    return dest


def validate_migration_context(context_dir: Path, *, expected_sha: str | None = None) -> dict[str, Any]:
    ctx = Path(context_dir)
    deployment = (ctx / "DEPLOYMENT_COMMIT").read_text(encoding="utf-8").strip() if (ctx / "DEPLOYMENT_COMMIT").is_file() else ""
    source = (ctx / "SOURCE_COMMIT").read_text(encoding="utf-8").strip() if (ctx / "SOURCE_COMMIT").is_file() else ""
    helper = ctx / "tools" / "ci" / "p2_staging_migration_0007.py"
    dockerfile = ctx / "Dockerfile"
    expected = (expected_sha or "").strip()
    ok = bool(
        deployment
        and source
        and deployment == source
        and helper.is_file()
        and dockerfile.is_file()
        and "NEXUS_POSTGRES_URL" not in dockerfile.read_text(encoding="utf-8")
        and (not expected or (deployment == expected and source == expected))
    )
    if not ok:
        raise ValueError("migration_context_invalid")
    return {
        "ok": True,
        "deployment_commit_prefix": deployment[:12],
        "source_commit_prefix": source[:12],
        "helper_present": True,
        "dsn_baked_in_image": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def plan_single_create_deploy(
    *,
    context_dir: Path | str,
    service_name: str,
    project_id: str,
    environment_id: str,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    ctx = str(Path(context_dir).resolve())
    root = str(Path(repo_root).resolve()) if repo_root else ""
    env_id = (environment_id or "").strip()
    if not service_name.strip():
        raise ValueError("service_name_missing")
    if not project_id.strip():
        raise ValueError("project_id_missing")
    if not env_id:
        raise ValueError("environment_id_missing")
    if root and Path(ctx).resolve() == Path(root).resolve():
        raise ValueError("migration_context_must_not_be_repo_root")
    argv = [
        "zeabur",
        "deploy",
        "--create",
        "--name",
        service_name,
        "--project-id",
        project_id,
        "--environment-id",
        env_id,
        "-i=false",
        "--json",
    ]
    return {
        "cwd": ctx,
        "argv": argv,
        "environment_id": env_id,
        "P2_MIGRATION_SINGLE_DEPLOY_BOOTSTRAP": True,
        "P2_MIGRATION_BOOTSTRAP_DEPLOY_COUNT": 1,
        "P2_MIGRATION_CREATE_ENV_EXPLICIT": True,
        "uses_create_empty_cli": False,
        "second_deploy_planned": False,
        "implicit_first_environment_fallback": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def _oid24(text: str, *keys: str) -> str:
    for key in keys:
        match = re.search(rf'"{re.escape(key)}"\s*:\s*"([0-9a-f]{{24}})"', text, re.I)
        if match:
            return match.group(1)
    return ""


def extract_service_id_from_create_output(raw: str) -> str:
    text = raw or ""
    sid = _oid24(text, "service_id", "serviceId")
    if sid:
        return sid
    return _oid24(text, "_id")


def extract_create_deploy_ids(raw: str) -> dict[str, str]:
    """Parse sanitized create/deploy JSON fields (no secrets)."""
    text = raw or ""
    return {
        "service_id": extract_service_id_from_create_output(text),
        "project_id": _oid24(text, "project_id", "projectId"),
        "environment_id": _oid24(
            text,
            "environment_id",
            "environmentId",
            "env_id",
            "envId",
        ),
    }


def verify_create_environment_match(
    *,
    create_output: str,
    expected_environment_id: str,
) -> dict[str, Any]:
    expected = (expected_environment_id or "").strip()
    if not expected:
        raise ValueError("environment_id_missing")
    ids = extract_create_deploy_ids(create_output)
    returned = (ids.get("environment_id") or "").strip()
    match = bool(returned and returned == expected)
    return {
        "service_id": ids.get("service_id") or "",
        "project_id": ids.get("project_id") or "",
        "environment_id": returned,
        "expected_environment_id": expected,
        "P2_MIGRATION_CREATE_ENV_MATCH": match,
        "ok": match,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }


def sanitize_bootstrap_failure_diagnostics(
    *,
    create_deploy_exit: int | None,
    create_deploy_output: str,
    service_id: str | None,
    service_name: str,
    readiness_attempts: int,
    not_running_count: int,
    current_image_positive_proof_count: int,
) -> dict[str, Any]:
    tail = (create_deploy_output or "")[-400:]
    redacted = re.sub(r"[A-Za-z0-9_\-+/=]{40,}", "***REDACTED***", tail)
    redacted = re.sub(r"postgres(?:ql)?://\S+", "postgresql://***", redacted, flags=re.I)
    return {
        "create_deploy_exit": create_deploy_exit,
        "create_deploy_output_tail": redacted,
        "service_id_prefix": (service_id or "")[:6] or "missing",
        "service_name": service_name,
        "readiness_attempts": readiness_attempts,
        "not_running_count": not_running_count,
        "current_image_positive_proof_count": current_image_positive_proof_count,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
    }

#!/usr/bin/env python3
"""Verify Zeabur Stage 3 container strict-env (no runner start)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_ROOT = REPO_ROOT / "deploy" / "zeabur_stage3_demo_learning"
REPORT = REPO_ROOT / "data/external_alpha/reports/zeabur_stage3_container_verification.json"

SERVICE_NAME = "nexus-stage3-bybit-demo-learning"
SERVICE_ID = "6a3b81652fdef84a45a2a553"
ENV_ID = "69d559b6474db8a99d6dd6bf"
FORBIDDEN = {"BYBIT_M0_API_KEY", "BYBIT_M0_API_SECRET"}


def _run(args: List[str], timeout: int = 180) -> Tuple[int, str, str]:
    cmd = ["npx", "zeabur@latest", *args]
    if sys.platform == "win32":
        p = subprocess.run(" ".join(cmd), capture_output=True, text=True, timeout=timeout, shell=True)
    else:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def _parse_var_keys(raw: str) -> Dict[str, bool]:
    out = {
        "BYBIT_DEMO_API_KEY": False,
        "BYBIT_DEMO_API_SECRET": False,
        "BYBIT_M0_API_KEY": False,
        "BYBIT_M0_API_SECRET": False,
    }
    if not raw.strip():
        return out
    try:
        data = json.loads(raw)
        rows = []
        if isinstance(data, dict):
            rows = list(data.get("variables") or []) + list(data.get("readonlyVariables") or [])
        for row in rows:
            if isinstance(row, dict):
                key = str(row.get("key") or "")
                if key in out:
                    out[key] = True
    except json.JSONDecodeError:
        lower = raw.lower()
        out["BYBIT_DEMO_API_KEY"] = "bybit_demo_api_key" in lower
        out["BYBIT_DEMO_API_SECRET"] = "bybit_demo_api_secret" in lower
        out["BYBIT_M0_API_KEY"] = "bybit_m0_api_key" in lower
        out["BYBIT_M0_API_SECRET"] = "bybit_m0_api_secret" in lower
    return out


def verify() -> Dict[str, Any]:
    deploy_pkg = {
        "dockerfile_found": (DEPLOY_ROOT / "Dockerfile").is_file(),
        "procfile_found": (DEPLOY_ROOT / "Procfile").is_file(),
        "service_root": "deploy/zeabur_stage3_demo_learning",
    }

    _, svc_out, _ = _run(["service", "ls", "--project-id", "69d559b62696d526abde8cd9", "-i=false"])
    service_visible = SERVICE_NAME.lower() in svc_out.lower()

    _, dep_out, dep_err = _run(
        ["deployment", "get", "--service-id", SERVICE_ID, "--env-id", ENV_ID, "--json", "-i=false"]
    )
    deployment: Dict[str, Any] = {"raw": dep_out.strip()[:2000], "stderr": dep_err.strip()[:500]}
    if dep_out.strip():
        try:
            deployment["data"] = json.loads(dep_out)
        except json.JSONDecodeError:
            deployment["parse_error"] = True

    _, log_out, log_err = _run(
        ["deployment", "get", "--service-id", SERVICE_ID, "--env-id", ENV_ID, "-i=false"]
    )
    deployment["text_status"] = (log_out + log_err).strip()[:2000]

    _, var_out, _ = _run(["variable", "list", "--id", SERVICE_ID, "--env-id", ENV_ID, "--json", "-i=false"])
    creds = _parse_var_keys(var_out)
    zeabur_vars_set = creds["BYBIT_DEMO_API_KEY"] and creds["BYBIT_DEMO_API_SECRET"]

    _, vol_out, vol_err = _run(
        [
            "service",
            "exec",
            "--id",
            SERVICE_ID,
            "--env-id",
            ENV_ID,
            "--",
            "sh",
            "-c",
            "test -d /data && test -w /data && echo VOLUME_OK",
        ],
        timeout=120,
    )
    volume_attached = "VOLUME_OK" in vol_out
    container_exists = "CONTAINER_NOT_FOUND" not in (vol_out + vol_err)

    _, strict_out, strict_err = _run(
        [
            "service",
            "exec",
            "--id",
            SERVICE_ID,
            "--env-id",
            ENV_ID,
            "--",
            "python",
            "tools/research/check_bybit_demo_learning_env.py",
            "--strict-env",
            "--no-check-package",
            "--no-load-local-env",
        ],
        timeout=180,
    )
    strict_passed = False
    strict_errors: List[str] = []
    if "CONTAINER_NOT_FOUND" in strict_out + strict_err:
        container_exists = False
        strict_errors.append("container_not_found")
    else:
        container_exists = True
        try:
            payload = json.loads(strict_out.strip() or "{}")
            strict_passed = bool(payload.get("strict_env_passed"))
            strict_errors = list(payload.get("strict_env_errors") or [])
        except json.JSONDecodeError:
            strict_errors.append("strict_env_output_unparseable")
            if strict_out.strip():
                strict_errors.append(strict_out.strip()[:300])

    container_status = "running" if container_exists and strict_passed else (
        "not_found" if not container_exists else "running_strict_env_failed"
    )

    env_in_pkg = any(DEPLOY_ROOT.rglob(".env"))
    secret_in_pkg = bool(list(DEPLOY_ROOT.rglob("*.pem")) + list(DEPLOY_ROOT.rglob("*.key")))

    report = {
        "record_type": "zeabur_stage3_container_verification",
        "service_name": SERVICE_NAME,
        "service_id": SERVICE_ID,
        "env_id": ENV_ID,
        "service_visible_via_cli": service_visible,
        "container_exists": container_exists,
        "container_status": container_status,
        "volume_attached": volume_attached,
        "volume_mount_path": "/data",
        "nexus_data_dir": "/data",
        "zeabur_variables_set": zeabur_vars_set,
        "old_bybit_m0_vars_present_in_zeabur": any(creds[k] for k in FORBIDDEN),
        "new_bybit_demo_vars_present_in_zeabur": creds["BYBIT_DEMO_API_KEY"] and creds["BYBIT_DEMO_API_SECRET"],
        "container_strict_env_passed": strict_passed,
        "container_strict_env_errors": strict_errors,
        "deploy_package": deploy_pkg,
        "deployment": deployment,
        "volume_probe_stdout": vol_out.strip()[:200],
        "volume_probe_stderr": vol_err.strip()[:300],
        "strict_env_stderr": strict_err.strip()[:300],
        "production_service_touched": False,
        "runner_started": False,
        "order_sent": False,
        "env_file_in_deploy_package": env_in_pkg,
        "secret_in_deploy_package": secret_in_pkg,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    r = verify()
    print(
        json.dumps(
            {
                "container_exists": r["container_exists"],
                "container_strict_env_passed": r["container_strict_env_passed"],
                "volume_attached": r["volume_attached"],
                "container_status": r["container_status"],
            },
            indent=2,
        )
    )
    ok = r["container_exists"] and r["container_strict_env_passed"] and r["volume_attached"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

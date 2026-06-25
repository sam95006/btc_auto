#!/usr/bin/env python3
"""Setup Zeabur Stage 3 demo learning service (no runner start, no orders)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_ROOT = REPO_ROOT / "deploy" / "zeabur_stage3_demo_learning"
BTC_PROJECT_ID = "69d559b62696d526abde8cd9"
SERVICE_NAME = "nexus-stage3-bybit-demo-learning"
SERVICE_ID = "6a3b81652fdef84a45a2a553"
ENV_ID = "69d559b6474db8a99d6dd6bf"
REPORT_PATH = REPO_ROOT / "data/external_alpha/reports/zeabur_stage3_service_setup_report.json"

STAGE3_ENV_KEYS = [
    "RESEARCH_ONLY",
    "BYBIT_DEMO_LEARNING_MODE",
    "BYBIT_SHADOW_MODE",
    "PAPER_ONLY",
    "BYBIT_ORDER_ALLOWED",
    "BYBIT_ORDER_SCOPE",
    "BYBIT_MAINNET_ALLOWED",
    "BYBIT_M0_BASE_URL",
    "EXCHANGE_WRITE_ALLOWED",
    "EXCHANGE_WRITE_SCOPE",
    "REAL_MONEY",
    "LIVE_TRADING",
    "PRODUCTION_PROMOTION_ALLOWED",
    "ARM_ALLOWED",
    "MAX_MARGIN_USD",
    "MAX_LEVERAGE",
    "MAX_OPEN_POSITIONS",
    "REQUIRE_STOP_LOSS",
    "REQUIRE_MAX_HOLD",
    "REQUIRE_REFLECTION_ON_LOSS",
    "REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP",
    "NEXUS_DATA_DIR",
    "NEXUS_STAGE2_SHADOW_MODE",
    "NEXUS_RESEARCH_ONLY",
    "NEXUS_BYBIT_SHADOW_MODE",
    "NEXUS_PAPER_ONLY",
    "NEXUS_ZEABUR_DEPLOY_MODE",
    "NEXUS_BYBIT_ORDER_ALLOWED",
    "NEXUS_EXCHANGE_WRITE_ALLOWED",
    "NEXUS_ARM_ALLOWED",
    "NEXUS_LIVE_TRADING",
    "NEXUS_REAL_MONEY",
    "NEXUS_PRODUCTION_PROMOTION_ALLOWED",
    "NEXUS_ALWAYS_ON_TRADING",
    "NEXUS_BOOTSTRAP_TRADES",
    "NEXUS_EMBEDDED_WORKER",
    "ZEABUR_PRODUCTION_RUNNER_ALLOWED",
    "BYBIT_DEMO_API_KEY",
    "BYBIT_DEMO_API_SECRET",
]

FORBIDDEN_ZEABUR_KEYS = {"BYBIT_M0_API_KEY", "BYBIT_M0_API_SECRET"}


def _run_npx(args: List[str], *, cwd: Path | None = None, timeout: int = 300) -> Tuple[int, str, str]:
    cmd = ["npx", "zeabur@latest", *args]
    if sys.platform == "win32":
        proc = subprocess.run(
            " ".join(cmd),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
        )
    else:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    return proc.returncode, proc.stdout, proc.stderr


def _load_dotenv(path: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _write_zeabur_env_file(local: Dict[str, str]) -> Path:
    defaults = {
        "NEXUS_ZEABUR_DEPLOY_MODE": "research_demo_learning",
        "NEXUS_STAGE2_SHADOW_MODE": "0",
        "NEXUS_RESEARCH_ONLY": "1",
        "NEXUS_BYBIT_SHADOW_MODE": "0",
        "NEXUS_PAPER_ONLY": "0",
        "NEXUS_BYBIT_ORDER_ALLOWED": "1",
        "NEXUS_EXCHANGE_WRITE_ALLOWED": "1",
        "NEXUS_ARM_ALLOWED": "0",
        "NEXUS_LIVE_TRADING": "0",
        "NEXUS_REAL_MONEY": "0",
        "NEXUS_PRODUCTION_PROMOTION_ALLOWED": "0",
        "NEXUS_ALWAYS_ON_TRADING": "0",
        "NEXUS_BOOTSTRAP_TRADES": "0",
        "NEXUS_EMBEDDED_WORKER": "0",
        "ZEABUR_PRODUCTION_RUNNER_ALLOWED": "false",
        "NEXUS_DATA_DIR": "/data",
    }
    merged = {**defaults, **{k: local[k] for k in STAGE3_ENV_KEYS if k in local}}
    for bad in FORBIDDEN_ZEABUR_KEYS:
        merged.pop(bad, None)
    fd, name = tempfile.mkstemp(prefix="zeabur_stage3_", suffix=".env")
    os.close(fd)
    path = Path(name)
    lines = [f"{k}={merged[k]}\n" for k in sorted(merged.keys()) if merged.get(k) is not None]
    path.write_text("".join(lines), encoding="utf-8")
    return path


def _service_visible() -> Tuple[bool, str]:
    code, out, err = _run_npx(["service", "ls", "--project-id", BTC_PROJECT_ID, "-i=false"])
    text = out + err
    return SERVICE_NAME.lower() in text.lower(), text


def setup(*, deploy: bool = True, set_vars: bool = True, container_check: bool = True) -> Dict[str, Any]:
    local = _load_dotenv(REPO_ROOT / ".env")
    project_code, project_out, _ = _run_npx(["project", "get", "--id", BTC_PROJECT_ID, "--json", "-i=false"])
    project_confirmed = project_code == 0 and BTC_PROJECT_ID in project_out

    visible_before, list_raw = _service_visible()
    deploy_result: Dict[str, Any] = {"attempted": deploy, "exit_code": None, "stdout": "", "stderr": ""}
    service_created = visible_before

    if deploy and not visible_before:
        code, out, err = _run_npx(
            [
                "deploy",
                "--create",
                "--name",
                SERVICE_NAME,
                "--project-id",
                BTC_PROJECT_ID,
                "-i=false",
            ],
            cwd=DEPLOY_ROOT,
            timeout=600,
        )
        deploy_result.update({"exit_code": code, "stdout": out.strip(), "stderr": err.strip()})
        deploy_triggered = code == 0
    else:
        deploy_triggered = False
        if visible_before:
            deploy_result["note"] = "service_already_exists_skip_deploy"

    visible_after, _ = _service_visible()
    service_created = visible_after

    var_result: Dict[str, Any] = {"attempted": set_vars, "exit_code": None}
    zeabur_vars_ok = False
    old_m0_in_zeabur = False
    new_demo_in_zeabur = False
    temp_env: Path | None = None

    if set_vars and service_created:
        temp_env = _write_zeabur_env_file(local)
        code, out, err = _run_npx(
            [
                "variable",
                "env",
                "-f",
                str(temp_env),
                "--id",
                SERVICE_ID,
                "--env-id",
                ENV_ID,
                "-i=false",
            ],
            timeout=300,
        )
        var_result.update({"exit_code": code, "stdout_len": len(out), "stderr": err.strip()[:200]})
        zeabur_vars_ok = code == 0
        if temp_env.is_file():
            temp_env.unlink(missing_ok=True)

        vcode, vout, _ = _run_npx(["variable", "list", "--id", SERVICE_ID, "--env-id", ENV_ID, "--json", "-i=false"])
        var_result["list_exit_code"] = vcode
        if vout.strip():
            try:
                data = json.loads(vout)
                keys: List[str] = []
                rows = []
                if isinstance(data, dict):
                    rows = list(data.get("variables") or []) + list(data.get("readonlyVariables") or [])
                elif isinstance(data, list):
                    rows = data
                keys = [str(r.get("key") or r.get("name") or "") for r in rows if isinstance(r, dict)]
                old_m0_in_zeabur = any(k in FORBIDDEN_ZEABUR_KEYS for k in keys)
                new_demo_in_zeabur = "BYBIT_DEMO_API_KEY" in keys and "BYBIT_DEMO_API_SECRET" in keys
                var_result["keys_present"] = sorted(k for k in keys if k and "SECRET" not in k and "KEY" not in k)
                var_result["credential_keys_present"] = {
                    "BYBIT_DEMO_API_KEY": "BYBIT_DEMO_API_KEY" in keys,
                    "BYBIT_DEMO_API_SECRET": "BYBIT_DEMO_API_SECRET" in keys,
                    "BYBIT_M0_API_KEY": "BYBIT_M0_API_KEY" in keys,
                    "BYBIT_M0_API_SECRET": "BYBIT_M0_API_SECRET" in keys,
                }
            except json.JSONDecodeError:
                var_result["parse_error"] = True
                lower = vout.lower()
                old_m0_in_zeabur = "bybit_m0_api" in lower
                new_demo_in_zeabur = "bybit_demo_api_key" in lower and "bybit_demo_api_secret" in lower

    container_result: Dict[str, Any] = {"attempted": container_check, "passed": False, "errors": []}
    if container_check and service_created:
        code, out, err = _run_npx(
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
            timeout=300,
        )
        container_result["exit_code"] = code
        container_result["stdout"] = out.strip()[:2000]
        container_result["stderr"] = err.strip()[:500]
        try:
            payload = json.loads(out.strip() or "{}")
            container_result["passed"] = payload.get("strict_env_passed", False) and code == 0
            container_result["errors"] = payload.get("strict_env_errors") or []
        except json.JSONDecodeError:
            container_result["passed"] = code == 0
            container_result["errors"].append("container_not_found_needs_service_restart")

    vol_probe: Dict[str, Any] = {}
    if service_created:
        code, out, err = _run_npx(
            ["service", "exec", "--id", SERVICE_ID, "--env-id", ENV_ID, "--", "sh", "-c", "test -d /data && test -w /data && echo VOLUME_OK"],
            timeout=120,
        )
        vol_probe = {"exit_code": code, "stdout": out.strip(), "stderr": err.strip()[:200]}
    volume_attached = "VOLUME_OK" in vol_probe.get("stdout", "")

    report = {
        "record_type": "zeabur_stage3_service_setup_report",
        "service_name": SERVICE_NAME,
        "service_root": "deploy/zeabur_stage3_demo_learning",
        "zeabur_project_confirmed": project_confirmed,
        "service_created": service_created,
        "service_visible_via_cli": visible_after,
        "volume_attached": volume_attached,
        "volume_mount_path": "/data",
        "zeabur_variables_set": zeabur_vars_ok,
        "old_bybit_m0_vars_present_in_zeabur": old_m0_in_zeabur,
        "new_bybit_demo_vars_present_in_zeabur": new_demo_in_zeabur,
        "container_strict_env_passed": container_result.get("passed", False),
        "container_strict_env_errors": container_result.get("errors", []),
        "deploy_triggered": deploy_triggered,
        "production_service_touched": False,
        "runner_started": False,
        "order_sent": False,
        "deploy_result": deploy_result,
        "variable_result": var_result,
        "container_result": container_result,
        "volume_probe": vol_probe,
        "services_list_snippet": list_raw[:500],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-deploy", action="store_true")
    args = parser.parse_args()
    report = setup(deploy=not args.skip_deploy)
    print(
        json.dumps(
            {
                "service_visible_via_cli": report["service_visible_via_cli"],
                "zeabur_variables_set": report["zeabur_variables_set"],
                "container_strict_env_passed": report["container_strict_env_passed"],
                "volume_attached": report["volume_attached"],
            },
            indent=2,
        )
    )
    ok = (
        report["service_visible_via_cli"]
        and report["zeabur_variables_set"]
        and report["container_strict_env_passed"]
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

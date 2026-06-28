#!/usr/bin/env python3
"""Build clean Zeabur Stage 3 Bybit demo learning deploy package."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import (  # noqa: E402
    MANIFEST_JSON,
    SERVICE_NAME,
    utc_now_iso,
    write_json,
)

DEPLOY_ROOT = ROOT / "deploy" / "zeabur_stage3_demo_learning"

BASE_ALLOWLIST = [
    "tools/research/check_bybit_demo_learning_env.py",
    "tools/research/bybit_demo_learning_common.py",
    "tools/research/bybit_demo_client.py",
    "tools/research/run_bybit_demo_learning_runner.py",
    "tools/research/stage3_learning_loop.py",
    "tools/research/stage3_demo_order_session.py",
    "tools/research/stage3_operator_go.py",
    "tools/research/preflight_stage3_demo_order.py",
    "tools/research/validate_stage3_demo_learning_outputs.py",
    "tools/research/close_bybit_demo_open_position.py",
    "tools/research/read_stage3_background_status.py",
    "tools/research/export_stage3_demo_learning_bundle.py",
    "tools/research/preflight_stage3_24h_runner.py",
    "tools/research/read_stage3_24h_status.py",
    "tools/research/export_stage3_24h_learning_bundle.py",
    "tools/research/stage3_readonly_web_app.py",
    "tools/research/stage4_provider_chain.py",
    "tools/research/stage4_llm_client.py",
    "tools/research/stage4_rate_limit_gate.py",
    "tools/research/stage4_system_events.py",
    "tools/research/stage4_response_parser.py",
    "tools/research/stage4_ai_decision_agent.py",
    "tools/research/stage4_risk_supervisor.py",
    "tools/research/stage4_prompt_builder.py",
    "tools/research/stage4_decision_schema.py",
    "tools/research/stage4_market_context.py",
    "tools/research/stage4_context_summary.py",
    "tools/research/export_stage4_ai_decision_bundle.py",
    "tools/research/import_stage3_context_seed.py",
    "tools/research/check_stage3_context_seed.py",
    "tools/research/analyze_stage4_rate_limit_events.py",
    "tools/research/run_stage4_ai_decision_dry_run.py",
    "tools/research/check_stage4_llm_provider.py",
    "tools/research/validate_stage4_ai_decision_outputs.py",
    "tools/research/stage4_cloud_exec_wrapper.sh",
    "tools/research/__init__.py",
    "tools/__init__.py",
    "backend/__init__.py",
    "backend/monitoring/__init__.py",
    "backend/monitoring/stage3_status_service.py",
    "templates/nexus_command.html",
    "data/external_alpha/reports/research_stage3_bybit_demo_learning_readiness.json",
    "data/external_alpha/reports/stage3_demo_learning_runner_readiness.json",
    "data/external_alpha/reports/stage3_c3_background_supervisor_readiness.json",
    "data/external_alpha/reports/stage3_24h_runner_readiness.json",
    "data/external_alpha/reports/stage3_github_auto_24h_startup_safety_report.json",
    "docs/research_stage3_bybit_demo_learning_runner_plan.md",
]

BOOT_EVIDENCE = [
    "data/external_alpha/reports/p1_behavior_change_report.json",
    "data/external_alpha/reports/p2_performance_report.json",
    "data/external_alpha/reports/oos_walkforward_report.json",
    "data/external_alpha/reports/phase9_production_promotion_review.json",
]

SECRET_PATTERNS = (
    re.compile(r"(?i)BEGIN (RSA |EC )?PRIVATE KEY"),
    re.compile(r"(?i)(api[_-]?key|secret)\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}['\"]"),
)

SECRET_SCAN_SKIP = {
    "tools/research/check_bybit_demo_learning_env.py",
    "docs/research_stage3_bybit_demo_learning_runner_plan.md",
}

FORBIDDEN_FRAGMENTS = (
    "docs/evidence",
    "docs/promotion",
    ".env",
    "frontend/",
    "exports/",
    "logs/",
    "stage2_",
    "nexus-stage2",
)

ENTRYPOINT_SH = ""

DOCKERFILE = """FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    NEXUS_DATA_DIR=/data \\
    STAGE3_STARTUP_MODE=idle \\
    STAGE3_OUTPUT_DIR=/data/stage3_demo_learning \\
    RESEARCH_ONLY=true \\
    BYBIT_DEMO_LEARNING_MODE=true \\
    BYBIT_SHADOW_MODE=false \\
    PAPER_ONLY=false \\
    BYBIT_ORDER_ALLOWED=true \\
    BYBIT_ORDER_SCOPE=demo_or_testnet_only \\
    BYBIT_MAINNET_ALLOWED=false \\
    BYBIT_M0_BASE_URL=https://api-demo.bybit.com \\
    EXCHANGE_WRITE_ALLOWED=true \\
    EXCHANGE_WRITE_SCOPE=bybit_demo_or_testnet_only \\
    REAL_MONEY=false \\
    LIVE_TRADING=false \\
    PRODUCTION_PROMOTION_ALLOWED=false \\
    ARM_ALLOWED=false \\
    MAX_MARGIN_USD=20 \\
    MAX_LEVERAGE=3 \\
    MAX_OPEN_POSITIONS=1 \\
    REQUIRE_STOP_LOSS=true \\
    REQUIRE_MAX_HOLD=true \\
    REQUIRE_REFLECTION_ON_LOSS=true \\
    REQUIRE_PATCH_BEFORE_NEXT_SAME_SETUP=true \\
    ZEABUR_PRODUCTION_RUNNER_ALLOWED=false \\
    PORT=8080

WORKDIR /app
RUN mkdir -p /data/data/external_alpha/demo_learning /data/logs /data/exports /data/stage3_demo_learning

COPY . .
RUN pip install --no-cache-dir -r requirements.txt
RUN chmod +x entrypoint.sh run_stage3_demo_order_background.sh run_stage3_24h_demo_learning_background.sh
EXPOSE 8080
# STAGE3_STARTUP_MODE=idle: read-only Web UI; runner mode spawns 24h runner then same UI
CMD ["/bin/sh", "./entrypoint.sh"]
"""

PROCfile = "web: sh entrypoint.sh\n"

STAGE3_ENTRYPOINT_SH = """#!/bin/sh
set -e
set -u

cd /app 2>/dev/null || cd "$(dirname "$0")"

if [ -f STAGE3_DEPLOY_VERSION.json ]; then
  python -c "import json; d=json.load(open('STAGE3_DEPLOY_VERSION.json', encoding='utf-8')); print('STAGE3_DEPLOY_VERSION'); print('commit=%s' % d.get('commit', 'unknown')); print('contains_24h_runner=%s' % str(d.get('contains_24h_runner', False)).lower()); print('contains_web_ui=%s' % str(d.get('contains_web_ui', False)).lower())"
fi

python tools/research/check_bybit_demo_learning_env.py --strict-env --no-check-package --no-load-local-env

MODE="${STAGE3_STARTUP_MODE:-idle}"
echo "stage3 strict-env passed; STAGE3_STARTUP_MODE=${MODE}"

if [ "$MODE" = "runner" ]; then
  if [ "${OPERATOR_GO_STAGE3_24H_RUNNER:-false}" != "true" ]; then
    echo "OPERATOR_GO_STAGE3_24H_RUNNER required for STAGE3_STARTUP_MODE=runner"
    exit 1
  fi
  if ! python tools/research/preflight_stage3_24h_runner.py --no-load-local-env; then
    echo "preflight_stage3_24h_runner failed"
    exit 1
  fi
  sh /app/run_stage3_24h_demo_learning_background.sh
  echo "24h demo learning runner spawned; starting read-only web UI"
fi

if [ "$MODE" = "idle" ]; then
  echo "Stage 3 idle web mode: starting read-only UI"
  if [ "${STAGE4_DRY_RUN_ONLY:-false}" = "true" ] && [ "${STAGE4_CLOUD_DRY_RUN_MINUTES:-0}" != "0" ]; then
    STAGE4_OUT="${STAGE4_OUTPUT_DIR:-/data/stage4_ai_decisions_42_10m}"
    mkdir -p "$STAGE4_OUT"
    if [ "${STAGE4_REQUIRE_REAL_LLM:-false}" = "true" ]; then
      if ! python tools/research/run_stage4_ai_decision_dry_run.py \
        --preflight-only \
        --use-real-llm \
        --output-dir "$STAGE4_OUT" \
        >> "$STAGE4_OUT/stage4_cloud_dry_run.log" 2>&1; then
        echo "Stage 4 cloud dry-run blocked: real LLM required but Groq key missing or provider unavailable"
      else
        echo "Stage 4 cloud dry-run: ${STAGE4_CLOUD_DRY_RUN_MINUTES}m -> $STAGE4_OUT (background, no orders)"
        python tools/research/run_stage4_ai_decision_dry_run.py \
          --duration-minutes "${STAGE4_CLOUD_DRY_RUN_MINUTES}" \
          --poll-interval-seconds "${STAGE4_POLL_INTERVAL_SECONDS:-120}" \
          --symbols ETHUSDT,BTCUSDT \
          --mode dry-run \
          --use-real-llm \
          --output-dir "$STAGE4_OUT" \
          >> "$STAGE4_OUT/stage4_cloud_dry_run.log" 2>&1 &
      fi
    else
      echo "Stage 4 cloud dry-run: ${STAGE4_CLOUD_DRY_RUN_MINUTES}m -> $STAGE4_OUT (background, no orders)"
      python tools/research/run_stage4_ai_decision_dry_run.py \
        --duration-minutes "${STAGE4_CLOUD_DRY_RUN_MINUTES}" \
        --poll-interval-seconds 60 \
        --symbols ETHUSDT,BTCUSDT \
        --mode dry-run \
        --use-real-llm \
        --output-dir "$STAGE4_OUT" \
        >> "$STAGE4_OUT/stage4_cloud_dry_run.log" 2>&1 &
    fi
  fi
fi

if [ "$MODE" != "idle" ] && [ "$MODE" != "runner" ]; then
  echo "unknown STAGE3_STARTUP_MODE=${MODE}"
  exit 1
fi

exec python tools/research/stage3_readonly_web_app.py
"""

REQUIREMENTS = """flask>=3.0,<4
gunicorn>=22.0,<24
"""
RUNTIME = "python-3.11.0\n"
STAGE3_BRANCH = "stage3-demo-learning"
VERSION_JSON_NAME = "STAGE3_DEPLOY_VERSION.json"

ZEABURIGNORE = """__pycache__/
**/__pycache__/
.pytest_cache/
.env
.env.*
*.key
*.pem
*.secret
*.db
trading.db
logs/
exports/
*.zip
data/external_alpha/stage3_demo_learning/
data/external_alpha/stage3_demo_learning/**
"""


def _git_value(args: List[str]) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _write_deploy_version() -> Dict[str, Any]:
    payload = {
        "branch": STAGE3_BRANCH,
        "commit": _git_value(["rev-parse", "HEAD"]),
        "deploy_package": "deploy/zeabur_stage3_demo_learning",
        "startup_mode_expected": "idle",
        "contains_24h_runner": True,
        "contains_web_ui": True,
        "contains_stage4_dry_run": True,
        "created_at_utc": utc_now_iso(),
    }
    write_json(DEPLOY_ROOT / VERSION_JSON_NAME, payload)
    return payload


def _copy(rel: str) -> None:
    src = ROOT / rel
    dst = DEPLOY_ROOT / rel
    if not src.is_file():
        raise FileNotFoundError(rel)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(rel_dir: str) -> List[str]:
    src_root = ROOT / rel_dir
    if not src_root.is_dir():
        raise FileNotFoundError(rel_dir)
    copied: List[str] = []
    for path in src_root.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        _copy(rel)
        copied.append(rel)
    return copied


def _scan_secrets(root: Path) -> List[str]:
    hits: List[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel in SECRET_SCAN_SKIP:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(rel)
                break
    return sorted(set(hits))


def _contains_forbidden(files: List[str]) -> List[str]:
    found: List[str] = []
    for frag in FORBIDDEN_FRAGMENTS:
        if any(frag in f for f in files):
            found.append(frag)
    return found


def build_package() -> Dict[str, Any]:
    script_dir = ROOT / "deploy" / "zeabur_stage3_demo_learning"
    bg_script_path = script_dir / "run_stage3_demo_order_background.sh"
    h24_script_path = script_dir / "run_stage3_24h_demo_learning_background.sh"
    entrypoint_path = script_dir / "entrypoint.sh"
    bg_script = bg_script_path.read_text(encoding="utf-8") if bg_script_path.is_file() else ""
    h24_script = h24_script_path.read_text(encoding="utf-8") if h24_script_path.is_file() else ""
    entrypoint_script = STAGE3_ENTRYPOINT_SH
    if entrypoint_path.is_file():
        entrypoint_script = entrypoint_path.read_text(encoding="utf-8")

    if DEPLOY_ROOT.is_dir():
        try:
            shutil.rmtree(DEPLOY_ROOT)
        except OSError:
            for path in sorted(DEPLOY_ROOT.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink(missing_ok=True)
                elif path.is_dir():
                    try:
                        path.rmdir()
                    except OSError:
                        pass
            try:
                DEPLOY_ROOT.rmdir()
            except OSError:
                pass
    DEPLOY_ROOT.mkdir(parents=True, exist_ok=True)

    allowlist = sorted(set(BASE_ALLOWLIST + BOOT_EVIDENCE + [
        "Procfile", "Dockerfile", "entrypoint.sh", "requirements.txt", "runtime.txt", ".zeaburignore",
    ]))
    missing: List[str] = []
    copied: List[str] = []
    for rel in allowlist:
        if rel in {
            "Procfile",
            "Dockerfile",
            "entrypoint.sh",
            "requirements.txt",
            "runtime.txt",
            ".zeaburignore",
            "tools/__init__.py",
            "backend/__init__.py",
            "backend/monitoring/__init__.py",
        }:
            continue
        try:
            _copy(rel)
            copied.append(rel)
        except FileNotFoundError:
            missing.append(rel)

    try:
        static_files = _copy_tree("static/nexus")
        copied.extend(static_files)
    except FileNotFoundError:
        missing.append("static/nexus/**")

    tools_init = DEPLOY_ROOT / "tools" / "__init__.py"
    tools_init.parent.mkdir(parents=True, exist_ok=True)
    if not tools_init.is_file():
        tools_init.write_text("# tools package (Stage 3 demo learning deploy)\n", encoding="utf-8")
    copied.append("tools/__init__.py")

    backend_init = DEPLOY_ROOT / "backend" / "__init__.py"
    backend_init.parent.mkdir(parents=True, exist_ok=True)
    if not backend_init.is_file():
        backend_init.write_text('"""NEXUS backend package."""\n', encoding="utf-8")
    monitoring_init = DEPLOY_ROOT / "backend" / "monitoring" / "__init__.py"
    monitoring_init.parent.mkdir(parents=True, exist_ok=True)
    if not monitoring_init.is_file():
        monitoring_init.write_text('"""Monitoring helpers."""\n', encoding="utf-8")
    copied.extend(["backend/__init__.py", "backend/monitoring/__init__.py"])

    (DEPLOY_ROOT / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    (DEPLOY_ROOT / "Procfile").write_text(PROCfile, encoding="utf-8")
    (DEPLOY_ROOT / "entrypoint.sh").write_bytes(
        (entrypoint_script or "#!/bin/sh\nexec sleep infinity\n").replace("\r\n", "\n").encode("utf-8")
    )
    (DEPLOY_ROOT / "requirements.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (DEPLOY_ROOT / "runtime.txt").write_text(RUNTIME, encoding="utf-8")
    (DEPLOY_ROOT / ".zeaburignore").write_text(ZEABURIGNORE, encoding="utf-8")
    copied.extend(
        ["Procfile", "Dockerfile", "entrypoint.sh", "requirements.txt", "runtime.txt", ".zeaburignore"]
    )

    if bg_script:
        normalized = bg_script.replace("\r\n", "\n").replace("\r", "\n")
        (DEPLOY_ROOT / "run_stage3_demo_order_background.sh").write_bytes(normalized.encode("utf-8"))
        copied.append("run_stage3_demo_order_background.sh")
    if h24_script:
        normalized24 = h24_script.replace("\r\n", "\n").replace("\r", "\n")
        (DEPLOY_ROOT / "run_stage3_24h_demo_learning_background.sh").write_bytes(normalized24.encode("utf-8"))
        copied.append("run_stage3_24h_demo_learning_background.sh")

    wrapper_src = ROOT / "tools/research/stage4_cloud_exec_wrapper.sh"
    if wrapper_src.is_file():
        wrapper = wrapper_src.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        (DEPLOY_ROOT / "tools/research/stage4_cloud_exec_wrapper.sh").write_bytes(wrapper.encode("utf-8"))
        (DEPLOY_ROOT / "tools/research/stage4_cloud_exec_wrapper.sh").chmod(0o755)
        copied.append("tools/research/stage4_cloud_exec_wrapper.sh")

    deploy_version = _write_deploy_version()
    copied.append(VERSION_JSON_NAME)

    package_files = sorted(
        str(p.relative_to(DEPLOY_ROOT)).replace("\\", "/")
        for p in DEPLOY_ROOT.rglob("*")
        if p.is_file()
    )
    secret_hits = _scan_secrets(DEPLOY_ROOT)
    forbidden_hits = _contains_forbidden(package_files)
    env_in_package = any(".env" in f for f in package_files)

    manifest: Dict[str, Any] = {
        "record_type": "zeabur_stage3_demo_learning_deploy_package_manifest",
        "schema_version": "1.0",
        "generated_at_utc": utc_now_iso(),
        "service_name": SERVICE_NAME,
        "deploy_package_path": "deploy/zeabur_stage3_demo_learning/",
        "allowlist_files": allowlist,
        "package_files": package_files,
        "package_file_count": len(package_files),
        "missing_allowlist_files": missing,
        "secret_files_detected": secret_hits,
        "env_file_in_deploy_package": env_in_package,
        "forbidden_fragments_detected": forbidden_hits,
        "package_ready": not missing and not secret_hits and not env_in_package and not forbidden_hits,
        "deploy_version": deploy_version,
        "deploy_triggered": False,
        "runner_started": False,
        "production_service_touched": False,
        "research_only": True,
        "bybit_demo_learning_mode": True,
        "bybit_mainnet_allowed": False,
        "real_money": False,
        "notes": [
            "Secrets via Zeabur Variables: BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET only.",
            "Legacy BYBIT_M0_API_KEY / BYBIT_M0_API_SECRET must be absent.",
            "Boot: strict-env then STAGE3_STARTUP_MODE=idle (read-only Web UI) or runner with OPERATOR_GO_STAGE3_24H_RUNNER.",
            "Do not touch btc-auto production service.",
        ],
    }
    write_json(MANIFEST_JSON, manifest)
    return manifest


def main() -> int:
    manifest = build_package()
    print(json.dumps({"package_ready": manifest["package_ready"], "package_file_count": manifest["package_file_count"]}, indent=2))
    return 0 if manifest["package_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build clean Zeabur Stage 3 Bybit demo learning deploy package."""
from __future__ import annotations

import json
import re
import shutil
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
    "tools/research/__init__.py",
    "tools/__init__.py",
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
    "backend/",
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
    ZEABUR_PRODUCTION_RUNNER_ALLOWED=false

WORKDIR /app
RUN mkdir -p /data/data/external_alpha/demo_learning /data/logs /data/exports

COPY . .
RUN chmod +x entrypoint.sh run_stage3_demo_order_background.sh run_stage3_24h_demo_learning_background.sh
# STAGE3_STARTUP_MODE=idle by default; set runner + OPERATOR_GO on Zeabur for 24h
CMD ["/bin/sh", "./entrypoint.sh"]
"""

PROCfile = "worker: sh entrypoint.sh\n"

REQUIREMENTS = "# Stage 3 demo learning — stdlib for env gate; runner deps TBD\n"
RUNTIME = "python-3.11.0\n"
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


def _copy(rel: str) -> None:
    src = ROOT / rel
    dst = DEPLOY_ROOT / rel
    if not src.is_file():
        raise FileNotFoundError(rel)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


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
    bg_script_path = DEPLOY_ROOT / "run_stage3_demo_order_background.sh"
    bg_script = bg_script_path.read_text(encoding="utf-8") if bg_script_path.is_file() else ""
    h24_script_path = DEPLOY_ROOT / "run_stage3_24h_demo_learning_background.sh"
    h24_script = h24_script_path.read_text(encoding="utf-8") if h24_script_path.is_file() else ""
    entrypoint_path = DEPLOY_ROOT / "entrypoint.sh"
    entrypoint_script = entrypoint_path.read_text(encoding="utf-8") if entrypoint_path.is_file() else ""

    if DEPLOY_ROOT.is_dir():
        try:
            shutil.rmtree(DEPLOY_ROOT)
        except PermissionError:
            for p in DEPLOY_ROOT.rglob("*"):
                if p.is_file():
                    p.unlink(missing_ok=True)
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
        }:
            continue
        try:
            _copy(rel)
            copied.append(rel)
        except FileNotFoundError:
            missing.append(rel)

    tools_init = DEPLOY_ROOT / "tools" / "__init__.py"
    tools_init.parent.mkdir(parents=True, exist_ok=True)
    if not tools_init.is_file():
        tools_init.write_text("# tools package (Stage 3 demo learning deploy)\n", encoding="utf-8")
    copied.append("tools/__init__.py")

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
            "Boot: strict-env then STAGE3_STARTUP_MODE=idle (default) or runner with OPERATOR_GO_STAGE3_24H_RUNNER.",
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

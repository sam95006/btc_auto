#!/usr/bin/env python3
"""Stage 3 GitHub deploy readiness — secret scan and git safety checks."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402

REPORT_PATH = ROOT / "data/external_alpha/reports/stage3_github_deploy_readiness.json"
DEPLOY_ROOT = ROOT / "deploy/zeabur_stage3_demo_learning"
ZEABUR_ROOT = "deploy/zeabur_stage3_demo_learning"
ENTRYPOINT = DEPLOY_ROOT / "entrypoint.sh"
VERSION_JSON = DEPLOY_ROOT / "STAGE3_DEPLOY_VERSION.json"
H24_SCRIPT = DEPLOY_ROOT / "run_stage3_24h_demo_learning_background.sh"
STAGE3_BRANCH = "stage3-demo-learning"

FORBIDDEN_GIT_PATTERNS = (
    ".env",
    ".env.",
    "*.key",
    "*.pem",
    "*.secret",
    "trading.db",
    "*.db",
    "logs/",
    "exports/",
    "data/external_alpha/stage3_demo_learning/",
    "/data/",
)

SAFE_GIT_PREFIXES = (
    "tools/research/",
    f"{ZEABUR_ROOT}/",
    "docs/research_stage3_",
)

SAFE_GIT_GLOBS = (
    "data/external_alpha/reports/*readiness*.json",
    "data/external_alpha/reports/*preflight*.json",
    "data/external_alpha/reports/*github_deploy_readiness*.json",
)

SECRET_KEY_PATTERNS = (
    "BYBIT_DEMO_API_KEY",
    "BYBIT_DEMO_API_SECRET",
    "BYBIT_M0_API_KEY",
    "BYBIT_M0_API_SECRET",
    "BINANCE_.*SECRET",
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "LINE_CHANNEL_ACCESS_TOKEN",
)

BINANCE_SECRET_RE = re.compile(r"(?im)^\s*(BINANCE_[A-Z0-9_]*SECRET[A-Z0-9_]*)\s*=\s*(.+?)\s*$")
GROQ_RE = re.compile(r"(?im)^\s*(GROQ_API_KEY[A-Z0-9_]*)\s*=\s*(.+?)\s*$")

PLACEHOLDER_MARKERS = (
    "你的_",
    "your_",
    "changeme",
    "replace_me",
    "placeholder",
    "<",
    ">",
    "xxx",
    "todo",
)


def _run(cmd: List[str], *, cwd: Path | None = None) -> Tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _git_tracked_files() -> List[str]:
    code, out = _run(["git", "ls-files"])
    if code != 0:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def _git_check_ignore(path: str) -> bool:
    code, _ = _run(["git", "check-ignore", "-q", path])
    return code == 0


def _is_placeholder(value: str) -> bool:
    val = value.strip().strip('"').strip("'")
    if not val:
        return True
    low = val.lower()
    return any(m in low for m in PLACEHOLDER_MARKERS)


def _looks_like_secret(value: str) -> bool:
    val = value.strip().strip('"').strip("'")
    if _is_placeholder(val):
        return False
    if val.startswith("#"):
        return False
    return len(val) >= 8


def scan_text_secrets(text: str, rel: str) -> List[str]:
    findings: List[str] = []
    line_patterns = [
        re.compile(r"(?im)^\s*(BYBIT_DEMO_API_KEY)\s*=\s*(.+?)\s*$"),
        re.compile(r"(?im)^\s*(BYBIT_DEMO_API_SECRET)\s*=\s*(.+?)\s*$"),
        re.compile(r"(?im)^\s*(BYBIT_M0_API_KEY)\s*=\s*(.+?)\s*$"),
        re.compile(r"(?im)^\s*(BYBIT_M0_API_SECRET)\s*=\s*(.+?)\s*$"),
        re.compile(r"(?im)^\s*(CEREBRAS_API_KEY)\s*=\s*(.+?)\s*$"),
        re.compile(r"(?im)^\s*(LINE_CHANNEL_ACCESS_TOKEN)\s*=\s*(.+?)\s*$"),
        BINANCE_SECRET_RE,
        GROQ_RE,
    ]
    for line in text.splitlines():
        if "re.compile" in line or "SECRET_KEY_PATTERNS" in line:
            continue
        for pattern in line_patterns:
            match = pattern.search(line)
            if not match:
                continue
            key, val = match.group(1), match.group(2)
            if _looks_like_secret(val):
                findings.append(f"{rel}:{key}=<redacted_len_{len(val.strip())}>")
    return findings


def scan_paths(paths: List[Path]) -> List[str]:
    findings: List[str] = []
    for path in paths:
        if not path.is_file():
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel.endswith((".png", ".jpg", ".jpeg", ".gif", ".zip", ".db", ".pyc")):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        findings.extend(scan_text_secrets(text, rel))
    return sorted(set(findings))


def _collect_scan_targets() -> List[Path]:
    targets: Set[Path] = set()
    if DEPLOY_ROOT.is_dir():
        for p in DEPLOY_ROOT.rglob("*"):
            if p.is_file():
                targets.add(p)
    for p in (ROOT / "tools/research").glob("*.py"):
        name = p.name
        if any(
            name.startswith(prefix)
            for prefix in (
                "stage3_",
                "bybit_demo_",
                "run_bybit_demo_",
                "preflight_stage3_",
                "validate_stage3_",
                "read_stage3_",
                "export_stage3_",
                "close_bybit_demo_",
                "check_bybit_demo_",
                "check_stage3_",
                "build_zeabur_stage3_",
                "setup_zeabur_stage3_",
                "verify_zeabur_stage3_",
                "migrate_stage3_",
            )
        ):
            targets.add(p)
    for p in (ROOT / "docs").glob("research_stage3_*.md"):
        targets.add(p)
    reports = ROOT / "data/external_alpha/reports"
    if reports.is_dir():
        for pattern in (
            "research_stage3_*readiness*.json",
            "stage3_*readiness*.json",
            "stage3_*preflight*.json",
            "stage3_*github_deploy_readiness*.json",
        ):
            for p in reports.glob(pattern):
                targets.add(p)
    return sorted(targets)


def _forbidden_tracked(tracked: List[str]) -> List[str]:
    forbidden: List[str] = []
    for rel in tracked:
        norm = rel.replace("\\", "/")
        if norm == ".env" or (norm.startswith(".env.") and norm != ".env.example"):
            forbidden.append(rel)
        elif norm.endswith((".key", ".pem", ".secret", ".db")) or norm == "trading.db":
            forbidden.append(rel)
        elif norm.startswith("logs/") or norm.startswith("exports/"):
            forbidden.append(rel)
        elif "stage3_demo_learning" in norm and "reports" not in norm:
            if "/stage3_demo_learning/" in norm or norm.endswith("stage3_demo_learning"):
                forbidden.append(rel)
        elif norm.startswith("data/") and not any(
            glob_match(norm, g) for g in SAFE_GIT_GLOBS
        ):
            if "external_alpha/reports" not in norm:
                forbidden.append(rel)
    return sorted(set(forbidden))


def glob_match(path: str, pattern: str) -> bool:
    from fnmatch import fnmatch

    return fnmatch(path, pattern.replace("**/", ""))


def _is_runtime_stage3_artifact(rel: str) -> bool:
    norm = rel.replace("\\", "/")
    if norm.startswith(f"{ZEABUR_ROOT}/"):
        return False
    if "reports" in norm:
        return False
    return "/stage3_demo_learning/" in norm or norm.endswith("/stage3_demo_learning")


def _safe_files_to_add() -> List[str]:
    safe: List[str] = []
    if DEPLOY_ROOT.is_dir():
        for p in DEPLOY_ROOT.rglob("*"):
            if p.is_file():
                safe.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    for p in (ROOT / "tools/research").glob("*.py"):
        name = p.name
        if any(
            name.startswith(prefix)
            for prefix in (
                "stage3_",
                "bybit_demo_",
                "run_bybit_demo_",
                "preflight_stage3_",
                "validate_stage3_",
                "read_stage3_",
                "export_stage3_",
                "close_bybit_demo_",
                "check_bybit_demo_",
                "check_stage3_",
                "build_zeabur_stage3_",
                "setup_zeabur_stage3_",
                "verify_zeabur_stage3_",
                "migrate_stage3_",
            )
        ):
            safe.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    for p in (ROOT / "docs").glob("research_stage3_*.md"):
        safe.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    reports = ROOT / "data/external_alpha/reports"
    if reports.is_dir():
        for pattern in (
            "research_stage3_*readiness*.json",
            "stage3_*readiness*.json",
            "stage3_*preflight*.json",
            "stage3_*github_deploy_readiness*.json",
        ):
            for p in reports.glob(pattern):
                safe.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return sorted(set(safe))


def _git_head() -> str:
    code, out = _run(["git", "rev-parse", "HEAD"])
    return out.strip() if code == 0 else ""


def _deploy_version_checks() -> Dict[str, Any]:
    git_head = _git_head()
    has_version_file = VERSION_JSON.is_file()
    version_commit = ""
    version_branch = ""
    if has_version_file:
        try:
            data = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
            version_commit = str(data.get("commit") or "").strip()
            version_branch = str(data.get("branch") or "").strip()
        except json.JSONDecodeError:
            has_version_file = False
    has_24h_script = H24_SCRIPT.is_file()
    entrypoint_text = ENTRYPOINT.read_text(encoding="utf-8", errors="ignore") if ENTRYPOINT.is_file() else ""
    runner_mode_supported = '[ "$MODE" = "runner" ]' in entrypoint_text or "STAGE3_STARTUP_MODE=runner" in entrypoint_text
    entrypoint_btc_auto_safe = "btc-auto" not in entrypoint_text.lower() and "btc_auto" not in entrypoint_text.lower()
    deploy_version_commit_match = bool(
        version_commit
        and git_head
        and (
            version_commit == git_head
            or version_commit == _git_value(["rev-parse", f"{git_head}^"])
        )
    )
    deploy_version_branch_match = version_branch == STAGE3_BRANCH
    prints_deploy_version = "STAGE3_DEPLOY_VERSION" in entrypoint_text
    return {
        "deploy_version_file_present": has_version_file,
        "deploy_version_commit": version_commit,
        "deploy_version_branch": version_branch,
        "github_latest_commit": git_head,
        "deploy_version_commit_match": deploy_version_commit_match,
        "deploy_version_branch_match": deploy_version_branch_match,
        "deploy_package_has_24h_script": has_24h_script,
        "entrypoint_runner_mode_supported": runner_mode_supported,
        "entrypoint_btc_auto_safe": entrypoint_btc_auto_safe,
        "entrypoint_prints_deploy_version": prints_deploy_version,
    }


def _entrypoint_flags() -> Tuple[bool, bool]:
    if not ENTRYPOINT.is_file():
        return False, False
    text = ENTRYPOINT.read_text(encoding="utf-8", errors="ignore")
    starts_runner = any(
        token in text
        for token in (
            "run_stage3_24h_demo_learning_background.sh",
            "STAGE3_STARTUP_MODE=runner",
            "preflight_stage3_24h_runner.py",
        )
    )
    idle = "sleep infinity" in text or 'STAGE3_STARTUP_MODE=idle' in text or 'STAGE3_STARTUP_MODE:-idle' in text
    return starts_runner, idle


def _gitignore_has(required: List[str]) -> bool:
    gi = ROOT / ".gitignore"
    if not gi.is_file():
        return False
    text = gi.read_text(encoding="utf-8", errors="ignore")
    return all(line in text or line.rstrip("/") in text for line in required)


def _zeaburignore_has(required: List[str]) -> bool:
    zi = DEPLOY_ROOT / ".zeaburignore"
    if not zi.is_file():
        return False
    text = zi.read_text(encoding="utf-8", errors="ignore")
    return all(line in text or line.rstrip("/") in text for line in required)


def run_check(*, rebuild: bool = True) -> Dict[str, Any]:
    deploy_package_ready = False
    if rebuild:
        from tools.research.build_zeabur_stage3_demo_learning_deploy_package import build_package

        manifest = build_package()
        deploy_package_ready = bool(manifest.get("package_ready"))
    elif DEPLOY_ROOT.is_dir():
        deploy_package_ready = any(DEPLOY_ROOT.iterdir())

    secret_findings = scan_paths(_collect_scan_targets())
    tracked = _git_tracked_files()
    forbidden_tracked = _forbidden_tracked(tracked)

    env_tracked = ".env" in tracked or any(
        t.startswith(".env.") and t not in {".env.example"} for t in tracked
    )
    secret_file_tracked = any(
        t.endswith((".key", ".pem", ".secret")) for t in tracked
    )
    data_artifacts_tracked = any(_is_runtime_stage3_artifact(t) for t in tracked)

    starts_runner, idle_keepalive = _entrypoint_flags()
    version_checks = _deploy_version_checks()

    gitignore_updated = _gitignore_has(
        [".env", ".env.*", "*.key", "*.pem", "*.secret", "stage3_demo_learning"]
    )
    zeaburignore_updated = _zeaburignore_has(
        [".env", ".env.*", "*.key", "*.pem", "*.secret", "logs/", "exports/"]
    )

    secret_scan_passed = not secret_findings
    deploy_version_ready = (
        version_checks["deploy_version_file_present"]
        and version_checks["deploy_version_commit_match"]
        and version_checks["deploy_package_has_24h_script"]
        and version_checks["entrypoint_runner_mode_supported"]
        and version_checks["entrypoint_btc_auto_safe"]
        and version_checks["entrypoint_prints_deploy_version"]
    )
    github_ready = (
        secret_scan_passed
        and not env_tracked
        and not secret_file_tracked
        and not data_artifacts_tracked
        and deploy_package_ready
        and deploy_version_ready
        and starts_runner
        and idle_keepalive
        and not forbidden_tracked
        and _git_check_ignore(".env")
    )

    report = {
        "record_type": "stage3_github_deploy_readiness",
        "generated_at_utc": utc_now_iso(),
        "github_ready": github_ready,
        "secret_scan_passed": secret_scan_passed,
        "secret_scan_findings": secret_findings,
        "env_file_tracked": env_tracked,
        "secret_file_tracked": secret_file_tracked,
        "data_artifacts_tracked": data_artifacts_tracked,
        "deploy_package_ready": deploy_package_ready,
        "deploy_package_path": ZEABUR_ROOT,
        "zeabur_root_directory": ZEABUR_ROOT,
        "zeabur_branch_recommended": "stage3-demo-learning",
        "entrypoint_starts_runner": starts_runner,
        "entrypoint_idle_keepalive": idle_keepalive,
        "deploy_version_ready": deploy_version_ready,
        **version_checks,
        "gitignore_updated": gitignore_updated,
        "zeaburignore_updated": zeaburignore_updated,
        "env_gitignored": _git_check_ignore(".env"),
        "safe_files_to_git_add": _safe_files_to_add(),
        "forbidden_files_detected": forbidden_tracked,
        "production_service_touched": False,
        "btc_auto_touched": False,
        "runner_started_24h": False,
        "notes": [
            "Do not git add .env or runtime artifacts under data/external_alpha/stage3_demo_learning/.",
            "Zeabur GitHub deploy: branch stage3-demo-learning, root deploy/zeabur_stage3_demo_learning.",
            "Entrypoint: STAGE3_STARTUP_MODE=idle (default) or runner with OPERATOR_GO_STAGE3_24H_RUNNER.",
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(REPORT_PATH, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 3 GitHub deploy readiness check")
    parser.add_argument("--no-rebuild", action="store_true")
    args = parser.parse_args()
    report = run_check(rebuild=not args.no_rebuild)
    print(json.dumps(report, indent=2))
    return 0 if report["github_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

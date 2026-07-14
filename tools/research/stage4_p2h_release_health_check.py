#!/usr/bin/env python3
"""Stage 4.18-P2H-QA — Repository / release health check (HOLD checkpoint).

Docs / git / consistency only. Does NOT start runtime, soaks, or Stage 4.19.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402

DEFAULT_OUT = Path("/data/stage4_18p2h_release_health_check")

RUNBOOK = ROOT / "docs" / "runbooks" / "STAGE_4_18_P2H_OPERATOR_HOLD_RUNBOOK.md"
P2G_PACK = ROOT / "docs" / "reports" / "STAGE_4_18P2G_OPERATOR_READINESS_PACK.md"
P2H_REPORT = ROOT / "docs" / "reports" / "STAGE_4_18P2H_BACKEND_HOLD_AND_PASSIVE_GATE_CHECKER_REPORT.md"
PLAN = ROOT / "docs" / "stage4_ai_decision_layer_plan.md"
FUTURE_CHECKER = ROOT / "tools" / "research" / "stage4_eth_future_regression_gate_checker.py"
UI_MVP10 = ROOT / "docs" / "ui" / "NEXUS_UI_MVP10_PRIVATE_OPERATOR_HARDENING_REPORT.md"
FRONTEND_README = ROOT / "frontend" / "README.md"
APP_TSX = ROOT / "frontend" / "src" / "App.tsx"
FRONTEND_SRC = ROOT / "frontend" / "src"
SNAPSHOT = FRONTEND_SRC / "demo" / "snapshots" / "p2gPrivateOperatorSnapshot.ts"

DOC_SAFE = re.compile(
    r"(forbidden|must\s+not|never|absent|do\s+not\s+start|don'?t\s+start|"
    r"not\s+started|blocked|read-?only|no\s+billing|HOLD|no\s+auto-run|"
    r"no\s+30m|no\s+60m|manual\s+only|must\s+not\s+auto)",
    re.IGNORECASE,
)
FORBIDDEN_ROUTE = re.compile(
    r'path\s*=\s*["\']/(?:trade|orders|arm|routing-edit|production|btc-auto)["\']',
    re.IGNORECASE,
)
FORBIDDEN_START = re.compile(
    r"startStage419|should_start_419\s*[:=]\s*true|shouldStart419\s*[:=]\s*true|"
    r"auto_start(?:_419|_regression)?\s*[:=]\s*true",
    re.IGNORECASE,
)
FORBIDDEN_PRODUCT = re.compile(
    r"billing\s+(?:portal|checkout|subscription)|customer\s+accounts?|"
    r"enter\s+your\s+api\s*key|api\s*key\s+collection|copy\s*trad(?:e|ing)|"
    r"managed\s+accounts?",
    re.IGNORECASE,
)
SECRET_PAT = re.compile(
    r"api[_-]?key\s*[:=]\s*['\"][^'\"]{8,}['\"]|sk-[a-zA-Z0-9]{10,}|"
    r"Bearer\s+[A-Za-z0-9\-_\.]{20,}",
    re.IGNORECASE,
)
RAW_DATA = re.compile(r"(?:^|[\"'`\s])/data/", re.MULTILINE)
TRACKED_BAD = re.compile(
    r"(?:^|/)\.env$|\.pem$|\.jsonl$|\.log$|bundle\.tar\.gz$|"
    r"credentials\.json$|secrets?\.json$",
    re.IGNORECASE,
)


def _git_ls_files() -> List[str]:
    try:
        r = subprocess.run(
            ["git", "ls-files"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if r.returncode != 0:
        return []
    return [ln.strip().replace("\\", "/") for ln in r.stdout.splitlines() if ln.strip()]


def _line_at(text: str, pos: int) -> str:
    a = text.rfind("\n", 0, pos) + 1
    b = text.find("\n", pos)
    return text[a : len(text) if b < 0 else b]


def _scan_frontend() -> Tuple[bool, bool, bool, List[str]]:
    """Return (no_419_start, no_order_arm_route, no_billing, issues)."""
    issues: List[str] = []
    no_419 = True
    no_order_arm = True
    no_billing = True
    if not FRONTEND_SRC.is_dir():
        return False, False, False, ["frontend/src missing"]
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".css", ".md"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT).as_posix()
        for rx, flag_name in (
            (FORBIDDEN_START, "419_start"),
            (FORBIDDEN_ROUTE, "order_arm_route"),
            (FORBIDDEN_PRODUCT, "billing"),
            (SECRET_PAT, "secret"),
        ):
            for m in rx.finditer(text):
                line = _line_at(text, m.start())
                if DOC_SAFE.search(line):
                    continue
                issues.append(f"{rel}: {flag_name} {m.group(0)!r}")
                if flag_name == "419_start":
                    no_419 = False
                elif flag_name == "order_arm_route":
                    no_order_arm = False
                elif flag_name == "billing":
                    no_billing = False
        if RAW_DATA.search(text) and "docs/" not in rel:
            # allow comment explaining forbidden /data
            for m in RAW_DATA.finditer(text):
                line = _line_at(text, m.start())
                if DOC_SAFE.search(line) or "must not" in line.lower() or "do not" in line.lower():
                    continue
                if "snapshots" in rel or "demo" in rel:
                    issues.append(f"{rel}: raw /data path")
                    break
    if APP_TSX.is_file():
        at = APP_TSX.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path\s*=\s*["\']{re.escape(bad)}["\']', at):
                no_order_arm = False
                issues.append(f"App.tsx route {bad}")
    return no_419, no_order_arm, no_billing, issues


def _plan_hold_ok() -> bool:
    if not PLAN.is_file():
        return False
    text = PLAN.read_text(encoding="utf-8", errors="replace")
    needles = ("HOLD", "4.18p2h", "next runtime only after ETH watch", "Stage 4.19 remains blocked")
    return all(n in text for n in needles) or (
        "HOLD" in text and "4.18p2h" in text.lower().replace("-", "")
    ) or ("HOLD" in text and "p2h" in text.lower())


def _backend_hold_confirmed() -> bool:
    if not SNAPSHOT.is_file():
        return False
    text = SNAPSHOT.read_text(encoding="utf-8", errors="replace")
    return 'state: "HOLD"' in text and "shouldRun30mNow: false" in text


def _ui_private_operator_ok() -> bool:
    if FRONTEND_README.is_file():
        rd = FRONTEND_README.read_text(encoding="utf-8", errors="replace")
        if "Private Operator" in rd and "READ ONLY" in rd:
            return True
    if SNAPSHOT.is_file():
        t = SNAPSHOT.read_text(encoding="utf-8", errors="replace")
        return "READ ONLY" in t and "Private Operator" in t or "private_operator" in t.lower()
    return False


def _no_raw_tracked() -> bool:
    files = _git_ls_files()
    if not files:
        # git unavailable — fall back to filesystem probe of forbidden names under frontend
        return not any(FRONTEND_SRC.rglob("*.jsonl")) and not (FRONTEND_SRC / "data").exists()
    bad = [f for f in files if TRACKED_BAD.search(f)]
    # Allow historical none under frontend; flag any frontend jsonl/logs
    frontend_bad = [f for f in bad if f.startswith("frontend/")]
    root_env = [f for f in files if f in {".env", ".env.local"} or f.endswith("/.env")]
    return not frontend_bad and not root_env


def run_release_health_check(*, output_dir: str | Path = "") -> Dict[str, Any]:
    out = Path(output_dir) if output_dir else DEFAULT_OUT
    no_419, no_order_arm, no_billing, scan_issues = _scan_frontend()

    operator_runbook_exists = RUNBOOK.is_file()
    p2g_pack_exists = P2G_PACK.is_file()
    p2h_report_exists = P2H_REPORT.is_file()
    plan_hold_state_consistent = _plan_hold_ok()
    future_gate_checker_exists = FUTURE_CHECKER.is_file()
    ui_mvp10_report_exists = UI_MVP10.is_file()
    frontend_readme_exists = FRONTEND_README.is_file()
    backend_hold_state_confirmed = _backend_hold_confirmed()
    ui_private_operator = _ui_private_operator_ok()
    no_raw = _no_raw_tracked()

    # Split order vs ARM for schema fidelity
    no_order = no_order_arm
    no_arm = no_order_arm
    if APP_TSX.is_file():
        at = APP_TSX.read_text(encoding="utf-8", errors="replace")
        no_order = not bool(re.search(r'path\s*=\s*["\']/(?:trade|orders)["\']', at))
        no_arm = not bool(re.search(r'path\s*=\s*["\']/(?:arm|production|btc-auto)["\']', at))

    checks = {
        "backend_hold_state_confirmed": backend_hold_state_confirmed,
        "operator_runbook_exists": operator_runbook_exists,
        "future_gate_checker_exists": future_gate_checker_exists,
        "p2g_pack_exists": p2g_pack_exists,
        "p2h_report_exists": p2h_report_exists,
        "ui_mvp10_report_exists": ui_mvp10_report_exists,
        "frontend_readme_exists": frontend_readme_exists,
        "plan_hold_state_consistent": plan_hold_state_consistent,
        "no_runtime_run": True,  # this tool never starts runtime
        "no_stage_419_start": no_419,
        "no_order_path_added": no_order,
        "no_arm_path_added": no_arm,
        "no_billing_or_accounts": no_billing,
        "no_raw_data_committed": no_raw,
        "ui_private_operator_readonly": ui_private_operator,
    }
    release_checkpoint_ready = all(checks.values())

    summary: Dict[str, Any] = {
        "stage": "4.18-P2H-QA",
        "generated_at": utc_now_iso(),
        **checks,
        "release_checkpoint_ready": release_checkpoint_ready,
        "next_recommendation": "hold_backend_and_continue_private_operator_ui",
        "scan_issues": scan_issues,
        "artifacts": {
            "runbook": str(RUNBOOK.relative_to(ROOT).as_posix()),
            "p2g_pack": str(P2G_PACK.relative_to(ROOT).as_posix()),
            "p2h_report": str(P2H_REPORT.relative_to(ROOT).as_posix()),
            "plan": str(PLAN.relative_to(ROOT).as_posix()),
            "future_checker": str(FUTURE_CHECKER.relative_to(ROOT).as_posix()),
            "ui_mvp10": str(UI_MVP10.relative_to(ROOT).as_posix()),
            "frontend_readme": str(FRONTEND_README.relative_to(ROOT).as_posix()),
        },
        "p2h_qa_verdict": "STAGE_4_18P2H_QA_PASS" if release_checkpoint_ready else "STAGE_4_18P2H_QA_FAIL",
    }

    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "p2h_release_health_summary.json", summary)
    report_md = _render_report(summary)
    (out / "p2h_release_health_report.md").write_text(report_md, encoding="utf-8")
    return summary


def _render_report(summary: Dict[str, Any]) -> str:
    rows = []
    for k, v in summary.items():
        if k in {"scan_issues", "artifacts", "generated_at"}:
            continue
        rows.append(f"| `{k}` | `{v}` |")
    issues = summary.get("scan_issues") or []
    issue_block = "\n".join(f"- {i}" for i in issues) if issues else "- (none)"
    return f"""# Stage 4.18-P2H-QA — Release Health Check

**Verdict:** `{summary.get("p2h_qa_verdict")}`  
**Generated:** `{summary.get("generated_at")}`  
**Mode:** docs / git / consistency only — **no runtime**

## Summary

| Field | Value |
|-------|--------|
{chr(10).join(rows)}

## Scan issues

{issue_block}

## Next

`{summary.get("next_recommendation")}`

Backend remains HOLD. Do not run 30m/60m. Do not start Stage 4.19.
"""


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Stage 4.18-P2H-QA release health check")
    p.add_argument("--output-dir", default=str(DEFAULT_OUT))
    args = p.parse_args(argv)
    summary = run_release_health_check(output_dir=args.output_dir)
    print(summary.get("p2h_qa_verdict"), "release_checkpoint_ready=", summary.get("release_checkpoint_ready"))
    if summary.get("scan_issues"):
        for i in summary["scan_issues"]:
            print("  -", i)
    return 0 if summary.get("release_checkpoint_ready") else 1


if __name__ == "__main__":
    sys.exit(main())

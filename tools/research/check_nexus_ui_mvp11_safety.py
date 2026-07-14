#!/usr/bin/env python3
"""NEXUS UI MVP-11 Report / Runbook Viewer safety scanner.

Runnable as: python tools/research/check_nexus_ui_mvp11_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
REPORT_INDEX = FRONTEND_SRC / "demo" / "reportIndex.ts"
REPORT_VIEWER = FRONTEND_SRC / "components" / "PrivateReportViewerCard.tsx"
RUNBOOK_VIEWER = FRONTEND_SRC / "components" / "OperatorRunbookCard.tsx"
GATE_CARD = FRONTEND_SRC / "components" / "GateChecklistCard.tsx"
README = ROOT / "frontend" / "README.md"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP11_REPORT_RUNBOOK_VIEWER_REPORT.md"
FORBIDDEN_DATA_DIR = FRONTEND_SRC / "data"

FORBIDDEN_ROUTE_PATTERNS = [
    r"/trade\b",
    r"/orders\b",
    r"/arm\b",
    r"/routing-edit\b",
    r"/production\b",
    r"/btc-auto\b",
]
FORBIDDEN_STRINGS = [
    r"placeOrder",
    r"submitOrder",
    r"enableArm",
    r"order_allowed\s*[:=]\s*true",
    r"orderAllowed\s*[:=]\s*true",
    r"should_start_419\s*[:=]\s*true",
    r"shouldStart419\s*[:=]\s*true",
    r"startStage419",
    r"start\s*stage\s*4\.?19",
    r"copy\s*trad(?:e|ing)",
    r"managed\s+accounts?",
    r"customer\s+accounts?",
    r"billing\s+(?:portal|checkout|subscription|invoice|payment)",
    r"api\s*key\s+collection",
    r"enter\s+your\s+api\s*key",
]
SECRET_PATTERNS = [
    r"api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]",
    r"sk-[a-zA-Z0-9]{10,}",
    r"Bearer\s+[A-Za-z0-9\-_\.]{20,}",
]
RAW_DATA_PATH = re.compile(r"(?:^|[\"'`\s])/data/", re.MULTILINE)
DOC_ALLOW = re.compile(
    r"(forbidden|must\s+not|never|absent|do\s+not\s+start|don'?t\s+start|"
    r"not\s+started|blocked|read-?only|no\s+billing|HOLD|no\s+auto-run|"
    r"no\s+30m|no\s+60m|manual\s+only|no\s+/data|metadata\s+only)",
    re.IGNORECASE,
)


def iter_files() -> list[Path]:
    return sorted(
        p
        for p in FRONTEND_SRC.rglob("*")
        if p.suffix in {".ts", ".tsx", ".css", ".js"} and p.is_file()
    )


def _line_at(text: str, pos: int) -> str:
    a = text.rfind("\n", 0, pos) + 1
    b = text.find("\n", pos)
    return text[a : len(text) if b < 0 else b]


def _doc(line: str, nearby: str = "") -> bool:
    return bool(DOC_ALLOW.search(f"{line}\n{nearby}"))


def scan(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()
    issues: list[str] = []
    for pat in FORBIDDEN_ROUTE_PATTERNS + FORBIDDEN_STRINGS + SECRET_PATTERNS:
        for m in re.finditer(pat, text, flags=re.I):
            line = _line_at(text, m.start())
            nearby = text[max(0, m.start() - 100) : m.start() + 60]
            if _doc(line, nearby):
                continue
            issues.append(f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: forbidden {pat!r}")
    for m in RAW_DATA_PATH.finditer(text):
        line = _line_at(text, m.start())
        if _doc(line) or "docs/" in line:
            continue
        issues.append(f"{rel}: raw /data path")
    return issues


def policy(files: list[Path]) -> list[str]:
    issues: list[str] = []
    if FORBIDDEN_DATA_DIR.exists() and any(FORBIDDEN_DATA_DIR.rglob("*")):
        issues.append("frontend/src/data/ must not be used")
    for req in (REPORT_INDEX, REPORT_VIEWER, RUNBOOK_VIEWER, GATE_CARD, README, REPORT_HINT):
        if not req.is_file():
            issues.append(f"missing {req.relative_to(ROOT).as_posix()}")
    if REPORT_INDEX.is_file():
        ri = REPORT_INDEX.read_text(encoding="utf-8", errors="replace")
        for n in (
            "4.18-P2D",
            "4.18-P2H",
            "4.18-P2H-QA",
            "STAGE_4_18_P2H_OPERATOR_HOLD_RUNBOOK",
            "SHORT_REGRESSION_CHECKLIST",
            "SAFETY_INVARIANTS_CHECKLIST",
            "PRIVATE_OPERATOR_REPORTS",
            "PRIVATE_OPERATOR_RUNBOOKS",
        ):
            if n not in ri:
                issues.append(f"reportIndex missing: {n}")
        if RAW_DATA_PATH.search(ri):
            issues.append("reportIndex has /data path")
    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "PrivateReportViewerCard",
        "OperatorRunbookCard",
        "GateChecklistCard",
        "Private Report Viewer",
        "Operator Runbook Viewer",
        "READ ONLY",
        "NOT INVESTMENT ADVICE",
    ):
        if needle not in blob:
            issues.append(f"frontend missing: {needle}")
    evidence = FRONTEND_SRC / "pages" / "EvidencePage.tsx"
    overview = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
    paper = FRONTEND_SRC / "pages" / "PaperLabPage.tsx"
    risk = FRONTEND_SRC / "pages" / "RiskEvidencePage.tsx"
    shadow = FRONTEND_SRC / "pages" / "ProviderShadowPage.tsx"
    app = FRONTEND_SRC / "App.tsx"
    if evidence.is_file():
        et = evidence.read_text(encoding="utf-8", errors="replace")
        for n in ("PrivateReportViewerCard", "OperatorRunbookCard"):
            if n not in et:
                issues.append(f"EvidencePage missing: {n}")
    if overview.is_file() and "GateChecklistCard" not in overview.read_text(encoding="utf-8", errors="replace"):
        issues.append("OverviewPage missing GateChecklistCard")
    if paper.is_file() and "SHORT_REGRESSION_CHECKLIST" not in paper.read_text(
        encoding="utf-8", errors="replace"
    ):
        issues.append("PaperLabPage missing SHORT_REGRESSION_CHECKLIST")
    if risk.is_file() and "SAFETY_INVARIANTS_CHECKLIST" not in risk.read_text(
        encoding="utf-8", errors="replace"
    ):
        issues.append("RiskEvidencePage missing SAFETY_INVARIANTS_CHECKLIST")
    if shadow.is_file() and "ROUTING_POLICY_CHECKLIST" not in shadow.read_text(
        encoding="utf-8", errors="replace"
    ):
        issues.append("ProviderShadowPage missing ROUTING_POLICY_CHECKLIST")
    if README.is_file():
        rd = README.read_text(encoding="utf-8", errors="replace")
        for n in ("Report Viewer", "Runbook Viewer", "READ ONLY"):
            if n not in rd:
                issues.append(f"README missing: {n}")
    if app.is_file():
        at = app.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', at):
                issues.append(f"App.tsx route {bad}")
    return issues


def main() -> int:
    print("NEXUS UI MVP-11 Report / Runbook Viewer safety check")
    if not FRONTEND_SRC.is_dir():
        print("FAIL: frontend/src missing")
        return 1
    files = iter_files()
    issues: list[str] = []
    for f in files:
        issues.extend(scan(f))
    issues.extend(policy(files))
    uniq = list(dict.fromkeys(issues))
    if uniq:
        print(f"FAIL: {len(uniq)} issue(s)")
        for i in uniq:
            print(f"  - {i}")
        return 1
    print(
        f"PASS: scanned {len(files)} files; report/runbook viewers + gate checklist; "
        "no trade/ARM/billing/4.19-start"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

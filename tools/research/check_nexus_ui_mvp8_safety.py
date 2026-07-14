#!/usr/bin/env python3
"""NEXUS UI MVP-8 P2F Gate + Report Index safety scanner.

Runnable as: python tools/research/check_nexus_ui_mvp8_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SNAPSHOT_DIR = FRONTEND_SRC / "demo" / "snapshots"
SNAPSHOT_FILE = SNAPSHOT_DIR / "p2fPrivateOperatorSnapshot.ts"
ADAPTER = FRONTEND_SRC / "demo" / "nexusDataAdapter.ts"
SNAPSHOT_TYPES = FRONTEND_SRC / "types" / "nexusSnapshot.ts"
GATE_CARD = FRONTEND_SRC / "components" / "WatchReappearanceGateCard.tsx"
INDEX_CARD = FRONTEND_SRC / "components" / "ReportIndexCard.tsx"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP8_P2F_GATE_AND_REPORT_INDEX_REPORT.md"
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
    r"guaranteed\s+profit",
    r"must\s+buy",
    r"must\s+sell",
    r"placeOrder",
    r"submitOrder",
    r"enableArm",
    r"arm_allowed\s*[:=]\s*true",
    r"order_allowed\s*[:=]\s*true",
    r"orderAllowed\s*[:=]\s*true",
    r"POST\s+/orders",
    r"POST\s+/trade",
    r"POST\s+/arm",
    r"routing.?edit(?:or)?",
    r"copy\s*trad(?:e|ing)",
    r"managed\s+accounts?",
    r"customer\s+accounts?",
    r"collect(?:ing)?\s+api\s*keys?",
    r"api\s*key\s+collection",
    r"enter\s+your\s+api\s*key",
    r"billing\s+(?:portal|checkout|subscription|invoice|payment)",
    r"stripe\s+checkout",
    r"payment\s+method",
    r"start\s*stage\s*4\.?19",
    r"startStage419",
    r"should_start_419\s*[:=]\s*true",
    r"shouldStart419\s*[:=]\s*true",
]

SECRET_PATTERNS = [
    r"api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]",
    r"secret\s*[:=]\s*['\"][^'\"]+['\"]",
    r"BYBIT[_A-Z]*\s*[:=]\s*['\"][^'\"]+['\"]",
    r"NEXUS_[A-Z_]*KEY\s*[:=]\s*['\"][^'\"]+['\"]",
    r"sk-[a-zA-Z0-9]{10,}",
    r"Bearer\s+[A-Za-z0-9\-_\.]{20,}",
]

RAW_DATA_PATH = re.compile(r"(?:^|[\"'`\s])/data/", re.MULTILINE)
BILLING_PATTERN = re.compile(r"\bbilling\b", re.IGNORECASE)
DOC_ALLOW = re.compile(
    r"(forbidden|must\s+not|never|absent|explicitly|"
    r"no\s+billing|no\s+routing|no\s+arm|no\s+order|"
    r"not\s+implemented|future\s+only|document(?:ing|ation)?|"
    r"read-?only|out\s+of\s+scope|blocked|do_not_run|no\s+60m|no\s+30m|"
    r"do\s+not\s+start|don'?t\s+start|must\s+not\s+start|not\s+started)",
    re.IGNORECASE,
)

REQUIRED_SNAPSHOT_MARKERS = [
    "SANITIZED SNAPSHOT",
    "READ ONLY",
    "NOT INVESTMENT ADVICE",
    "4.18-P2F",
    "STAGE_4_18P2F_PASS",
    "private_operator_snapshot",
    "regressionReadiness: false",
    "doNotRunRegressionNow: true",
    "operatorApprovedShortRegressionMayBeJustified: false",
    "hasEthWatchOrValidWatch: false",
    "shouldRun60m: false",
    "waitHelperRobustnessStatus: \"PASS\"",
    "stage419Readiness: false",
    "shouldStart419: false",
    "wait_for_eth_watch_conditions_reappear_no_60m",
    "watchReappearanceGateStatus",
    "reportIndex",
]

TEXT_GLOBS = ("*.ts", "*.tsx", "*.css", "*.json", "*.html", "*.mjs", "*.js")


def iter_source_files() -> list[Path]:
    if not FRONTEND_SRC.is_dir():
        return []
    files: list[Path] = []
    for pattern in TEXT_GLOBS:
        files.extend(FRONTEND_SRC.rglob(pattern))
    return sorted({p for p in files if p.is_file()})


def _line_at(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end < 0:
        line_end = len(text)
    return text[line_start:line_end]


def _is_documenting(line: str, nearby: str = "") -> bool:
    return bool(DOC_ALLOW.search(f"{line}\n{nearby}"))


def scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()
    issues: list[str] = []
    for pat in FORBIDDEN_ROUTE_PATTERNS + FORBIDDEN_STRINGS + SECRET_PATTERNS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            line = _line_at(text, m.start())
            nearby = text[max(0, m.start() - 120) : m.start() + 80]
            if _is_documenting(line, nearby):
                continue
            lineno = text.count("\n", 0, m.start()) + 1
            issues.append(f"{rel}:{lineno}: forbidden {pat!r} -> {line.strip()!r}")
    for m in BILLING_PATTERN.finditer(text):
        line = _line_at(text, m.start())
        nearby = text[max(0, m.start() - 120) : m.start() + 80]
        if _is_documenting(line, nearby) or re.search(r"no\s+billing", line, re.I):
            continue
        lineno = text.count("\n", 0, m.start()) + 1
        issues.append(f"{rel}:{lineno}: billing surface -> {line.strip()!r}")
    return issues


def check_mvp8_policy(files: list[Path]) -> list[str]:
    issues: list[str] = []
    if FORBIDDEN_DATA_DIR.exists():
        bad = [p for p in FORBIDDEN_DATA_DIR.rglob("*") if p.is_file()]
        if bad:
            issues.append("frontend/src/data/ must not be used for snapshots")

    if not SNAPSHOT_FILE.is_file():
        issues.append("missing p2fPrivateOperatorSnapshot.ts")
        return issues

    text = SNAPSHOT_FILE.read_text(encoding="utf-8", errors="replace")
    for marker in REQUIRED_SNAPSHOT_MARKERS:
        if marker not in text:
            issues.append(f"p2f snapshot missing marker: {marker}")
    if RAW_DATA_PATH.search(text):
        issues.append("snapshot must not contain /data raw paths")

    for required in (ADAPTER, SNAPSHOT_TYPES, GATE_CARD, INDEX_CARD):
        if not required.is_file():
            issues.append(f"missing: {required.relative_to(ROOT).as_posix()}")

    if ADAPTER.is_file():
        at = ADAPTER.read_text(encoding="utf-8", errors="replace")
        if "p2fPrivateOperatorSnapshot" not in at:
            issues.append("adapter missing p2fPrivateOperatorSnapshot")
        if not re.search(
            r"ACTIVE_PRIVATE_OPERATOR_SNAPSHOT[^=]*=\s*p2fPrivateOperatorSnapshot", at
        ):
            issues.append("adapter ACTIVE snapshot must default to p2f")
        for getter in (
            "getWatchReappearanceGateStatus",
            "getReportIndex",
            "getRegressionReadinessStatus",
        ):
            if getter not in at:
                issues.append(f"adapter missing {getter}")

    if GATE_CARD.is_file():
        gt = GATE_CARD.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "WatchReappearanceGateStatus",
            "do_not_run_regression_now",
            "has_eth_watch_or_valid_watch",
            "should_run_60m",
            "wait_helper_robustness",
            "PASS",
        ):
            if needle not in gt:
                issues.append(f"WatchReappearanceGateCard missing: {needle}")

    if INDEX_CARD.is_file():
        it = INDEX_CARD.read_text(encoding="utf-8", errors="replace")
        for needle in ("ReportIndexItem", "reportPath", "oneLineConclusion", "Next action"):
            if needle not in it:
                issues.append(f"ReportIndexCard missing: {needle}")

    frontend_blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in files
        if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "STAGE_4_18P2F_PASS",
        "do_not_run_regression_now",
        "regression readiness=false",
        "WatchReappearanceGateCard",
        "ReportIndexCard",
        "4.18-P2F",
        "Private Operator",
        "NOT INVESTMENT ADVICE",
    ):
        if needle not in frontend_blob and needle.lower() not in frontend_blob.lower():
            if needle == "regression readiness=false":
                if "regressionReadiness: false" in frontend_blob or "readiness=false" in frontend_blob:
                    continue
            issues.append(f"frontend missing: {needle}")

    overview = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
    risk = FRONTEND_SRC / "pages" / "RiskEvidencePage.tsx"
    paper = FRONTEND_SRC / "pages" / "PaperLabPage.tsx"
    evidence = FRONTEND_SRC / "pages" / "EvidencePage.tsx"
    shadow = FRONTEND_SRC / "pages" / "ProviderShadowPage.tsx"
    membership = FRONTEND_SRC / "pages" / "MembershipPage.tsx"
    app = FRONTEND_SRC / "App.tsx"

    if overview.is_file():
        ot = overview.read_text(encoding="utf-8", errors="replace")
        for needle in ("P2F", "WatchReappearanceGateCard", "regression readiness=false"):
            if needle not in ot:
                issues.append(f"OverviewPage missing: {needle}")

    if risk.is_file():
        rt = risk.read_text(encoding="utf-8", errors="replace")
        for needle in ("WatchReappearanceGateCard", "no 30m", "no 60m", "Stage 4.19"):
            if needle not in rt:
                issues.append(f"RiskEvidencePage missing: {needle}")

    if paper.is_file():
        pt = paper.read_text(encoding="utf-8", errors="replace")
        for needle in ("Next condition before regression", "WatchReappearanceGateCard"):
            if needle not in pt:
                issues.append(f"PaperLabPage missing: {needle}")

    if evidence.is_file():
        et = evidence.read_text(encoding="utf-8", errors="replace")
        for needle in ("ReportIndexCard", "getReportIndex", "P2D", "P2F"):
            if needle not in et:
                issues.append(f"EvidencePage missing: {needle}")

    if shadow.is_file() and "p2fSummary" not in shadow.read_text(encoding="utf-8", errors="replace"):
        issues.append("ProviderShadowPage missing: p2fSummary")

    if membership.is_file():
        mt = membership.read_text(encoding="utf-8", errors="replace")
        for needle in ("Future only", "No billing", "customer SaaS not implemented"):
            if needle not in mt:
                issues.append(f"MembershipPage missing: {needle}")

    if app.is_file():
        at = app.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', at):
                issues.append(f"App.tsx forbidden route: {bad}")

    if not REPORT_HINT.is_file():
        issues.append("missing MVP-8 report")

    if "READ ONLY" not in frontend_blob and "READ-ONLY" not in frontend_blob:
        issues.append("READ ONLY missing")

    return issues


def main() -> int:
    print("NEXUS UI MVP-8 P2F Gate + Report Index safety check")
    if not FRONTEND_SRC.is_dir():
        print("FAIL: frontend/src not found")
        return 1
    files = iter_source_files()
    issues: list[str] = []
    for path in files:
        issues.extend(scan_file(path))
    issues.extend(check_mvp8_policy(files))
    unique = list(dict.fromkeys(issues))
    if unique:
        print(f"FAIL: {len(unique)} issue(s)")
        for i in unique:
            print(f"  - {i}")
        return 1
    print(
        f"PASS: scanned {len(files)} files; P2F snapshot OK; "
        "WatchReappearanceGateCard + ReportIndexCard OK; "
        "do_not_run_now / no 60m / Stage 4.19 blocked displayed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

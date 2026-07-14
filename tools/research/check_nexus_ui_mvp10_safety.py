#!/usr/bin/env python3
"""NEXUS UI MVP-10 Private Operator hardening safety scanner.

Runnable as: python tools/research/check_nexus_ui_mvp10_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SNAPSHOT_FILE = FRONTEND_SRC / "demo" / "snapshots" / "p2gPrivateOperatorSnapshot.ts"
ADAPTER = FRONTEND_SRC / "demo" / "nexusDataAdapter.ts"
HOLD_BANNER = FRONTEND_SRC / "components" / "OperatorHoldBanner.tsx"
GATE_CARD = FRONTEND_SRC / "components" / "OperatorGateChecklistCard.tsx"
REPORT_CARD = FRONTEND_SRC / "components" / "ReportIndexCard.tsx"
README = ROOT / "frontend" / "README.md"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP10_PRIVATE_OPERATOR_HARDENING_REPORT.md"
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
    r"no\s+30m|no\s+60m|manual\s+only|wait-for-condition|experiment\s+only)",
    re.IGNORECASE,
)

REQUIRED_SNAPSHOT = [
    "SANITIZED SNAPSHOT",
    "READ ONLY",
    "NOT INVESTMENT ADVICE",
    "STAGE_4_18P2H_PASS",
    'state: "HOLD"',
    "ETH watch conditions not present",
    "shouldRun30mNow: false",
    "shouldRun60m: false",
    "shouldStart419: false",
    "4.18-P2D",
    "4.18-P2D-R1",
    "4.18-P2E",
    "4.18-P2F",
    "4.18-P2G",
    "4.18-P2H",
    "btcPriorGraduationEvidenceExists: true",
    "latestBtcRegressionGraduation: 0",
    "nextShortRegressionAllowedNow: false",
]


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
    return issues


def policy(files: list[Path]) -> list[str]:
    issues: list[str] = []
    if FORBIDDEN_DATA_DIR.exists() and any(FORBIDDEN_DATA_DIR.rglob("*")):
        issues.append("frontend/src/data/ must not be used")
    if not SNAPSHOT_FILE.is_file():
        issues.append("missing p2gPrivateOperatorSnapshot.ts")
        return issues
    text = SNAPSHOT_FILE.read_text(encoding="utf-8", errors="replace")
    for m in REQUIRED_SNAPSHOT:
        if m not in text:
            issues.append(f"snapshot missing: {m}")
    if RAW_DATA_PATH.search(text):
        issues.append("snapshot has /data path")
    for req in (ADAPTER, HOLD_BANNER, GATE_CARD, REPORT_CARD, README, REPORT_HINT):
        if not req.is_file():
            issues.append(f"missing {req.relative_to(ROOT).as_posix()}")
    if ADAPTER.is_file():
        at = ADAPTER.read_text(encoding="utf-8", errors="replace")
        if "p2gPrivateOperatorSnapshot" not in at:
            issues.append("adapter missing p2g")
        if not re.search(
            r"ACTIVE_PRIVATE_OPERATOR_SNAPSHOT[^=]*=\s*p2gPrivateOperatorSnapshot", at
        ):
            issues.append("adapter must prefer p2g")
    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "OperatorHoldBanner",
        "OperatorGateChecklistCard",
        "Backend State: HOLD",
        "wait-for-condition",
        "no auto-run",
        "30m now",
        "Stage 4.19",
        "blocked",
        "P2H",
        "no permanent routing change",
        "routing auto change",
        "BTC prior graduation evidence",
        "next short regression allowed now",
        "no order",
        "no mock",
        "no ARM",
        "no production",
        "no btc-auto",
        "READ ONLY",
        "NOT INVESTMENT ADVICE",
    ):
        if needle not in blob and needle.lower() not in blob.lower():
            issues.append(f"frontend missing: {needle}")
    overview = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
    risk = FRONTEND_SRC / "pages" / "RiskEvidencePage.tsx"
    paper = FRONTEND_SRC / "pages" / "PaperLabPage.tsx"
    evidence = FRONTEND_SRC / "pages" / "EvidencePage.tsx"
    shadow = FRONTEND_SRC / "pages" / "ProviderShadowPage.tsx"
    app = FRONTEND_SRC / "App.tsx"
    if overview.is_file():
        ot = overview.read_text(encoding="utf-8", errors="replace")
        for n in ("OperatorHoldBanner", "HOLD", "30m now: false", "Stage 4.19: blocked"):
            if n not in ot:
                issues.append(f"OverviewPage missing: {n}")
    if risk.is_file():
        rt = risk.read_text(encoding="utf-8", errors="replace")
        for n in ("no order", "no mock", "no ARM", "no production", "no btc-auto", "no Stage 4.19"):
            if n not in rt:
                issues.append(f"RiskEvidencePage missing: {n}")
    if paper.is_file():
        pt = paper.read_text(encoding="utf-8", errors="replace")
        for n in (
            "BTC prior graduation evidence",
            "latest BTC regression graduation",
            "ETH prompt repair done",
            "ETH runtime validation",
            "next short regression allowed now",
        ):
            if n not in pt:
                issues.append(f"PaperLabPage missing: {n}")
    if evidence.is_file():
        et = evidence.read_text(encoding="utf-8", errors="replace")
        for n in ("ReportIndexCard", "P2D", "P2D-R1", "P2E", "P2F", "P2G", "P2H"):
            if n not in et:
                issues.append(f"EvidencePage missing: {n}")
    if REPORT_CARD.is_file():
        rc = REPORT_CARD.read_text(encoding="utf-8", errors="replace")
        for n in ("P2D", "P2D-R1", "P2E", "P2F", "P2G", "P2H"):
            if n not in rc:
                issues.append(f"ReportIndexCard missing: {n}")
    if shadow.is_file():
        st = shadow.read_text(encoding="utf-8", errors="replace")
        for n in ("no permanent routing change", "experiment only", "routing auto change"):
            if n not in st:
                issues.append(f"ProviderShadowPage missing: {n}")
    if README.is_file():
        rd = README.read_text(encoding="utf-8", errors="replace")
        for n in ("Private Operator", "READ ONLY", "npm run dev", "NOT INVESTMENT ADVICE"):
            if n not in rd:
                issues.append(f"frontend README missing: {n}")
    if app.is_file():
        at = app.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', at):
                issues.append(f"App.tsx route {bad}")
    return issues


def main() -> int:
    print("NEXUS UI MVP-10 Private Operator hardening safety check")
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
        f"PASS: scanned {len(files)} files; HOLD / wait-for-condition / P2H index / "
        "no trade/ARM/billing/4.19-start"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

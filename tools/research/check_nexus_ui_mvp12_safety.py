#!/usr/bin/env python3
"""NEXUS UI MVP-12 P2H-QA Release Health Badge safety scanner.

Runnable as: python tools/research/check_nexus_ui_mvp12_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
RELEASE_HEALTH = FRONTEND_SRC / "demo" / "releaseHealth.ts"
CHECKPOINT_CARD = FRONTEND_SRC / "components" / "CheckpointHealthCard.tsx"
README = ROOT / "frontend" / "README.md"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP12_RELEASE_HEALTH_BADGE_REPORT.md"
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
    r"no\s+30m|no\s+60m|manual\s+only|no\s+/data|checkpoint)",
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
    for req in (RELEASE_HEALTH, CHECKPOINT_CARD, README, REPORT_HINT):
        if not req.is_file():
            issues.append(f"missing {req.relative_to(ROOT).as_posix()}")
    if RELEASE_HEALTH.is_file():
        rh = RELEASE_HEALTH.read_text(encoding="utf-8", errors="replace")
        for n in (
            'latestReleaseCheckpoint: "P2H-QA"',
            "releaseCheckpointReady: true",
            "backendHoldStateConfirmed: true",
            "uiPrivateOperatorReadonly: true",
            "noStage419Start: true",
            "noOrderPathAdded: true",
            "noArmPathAdded: true",
            "noBillingOrAccounts: true",
            "noRawDataCommitted: true",
        ):
            if n not in rh:
                issues.append(f"releaseHealth missing: {n}")
        if RAW_DATA_PATH.search(rh):
            issues.append("releaseHealth has /data path")
    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "CheckpointHealthCard",
        "ReleaseHealthBadge",
        "Release checkpoint ready",
        "Backend HOLD confirmed",
        "No Stage 4.19 start",
        "no auto-run",
        "P2H-QA health PASS",
        "READ ONLY",
        "NOT INVESTMENT ADVICE",
    ):
        if needle not in blob:
            issues.append(f"frontend missing: {needle}")
    overview = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
    evidence = FRONTEND_SRC / "pages" / "EvidencePage.tsx"
    risk = FRONTEND_SRC / "pages" / "RiskEvidencePage.tsx"
    app = FRONTEND_SRC / "App.tsx"
    if overview.is_file():
        ot = overview.read_text(encoding="utf-8", errors="replace")
        if "CheckpointHealthCard" not in ot:
            issues.append("OverviewPage missing CheckpointHealthCard")
    if evidence.is_file():
        et = evidence.read_text(encoding="utf-8", errors="replace")
        for n in ("ReleaseHealthBadge", "showP2hQaHealthBadge"):
            if n not in et:
                issues.append(f"EvidencePage missing: {n}")
    if risk.is_file():
        rt = risk.read_text(encoding="utf-8", errors="replace")
        for n in ("CheckpointHealthCard", "Safety invariants PASS"):
            if n not in rt:
                issues.append(f"RiskEvidencePage missing: {n}")
    if README.is_file():
        rd = README.read_text(encoding="utf-8", errors="replace")
        for n in ("Release Health", "P2H-QA", "READ ONLY"):
            if n not in rd:
                issues.append(f"README missing: {n}")
    if app.is_file():
        at = app.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', at):
                issues.append(f"App.tsx route {bad}")
    return issues


def main() -> int:
    print("NEXUS UI MVP-12 Release Health Badge safety check")
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
        f"PASS: scanned {len(files)} files; P2H-QA health badge + HOLD checkpoint; "
        "no trade/ARM/billing/4.19-start"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

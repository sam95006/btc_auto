#!/usr/bin/env python3
"""NEXUS UI MVP-16 Static Excerpt Search / Filter + Checklist Links safety scanner.

Runnable as: python tools/research/check_nexus_ui_mvp16_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
DOC_SUMMARIES = FRONTEND_SRC / "demo" / "docSummaries.ts"
FILTER_BAR = FRONTEND_SRC / "components" / "DocSummaryFilterBar.tsx"
CHECKLIST_LINKS = FRONTEND_SRC / "components" / "ChecklistReferenceLinks.tsx"
UNRESOLVED = FRONTEND_SRC / "components" / "UnresolvedGateCard.tsx"
README = ROOT / "frontend" / "README.md"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP16_STATIC_EXCERPT_SEARCH_FILTER_REPORT.md"
FORBIDDEN_DATA_DIR = FRONTEND_SRC / "data"

CONTROL_FORBIDDEN = [
    r"\bStart Stage 4\.?19\b",
    r"\bRun 30m\b",
    r"\bRun 60m\b",
    r"startStage419",
    r"shouldStart419\s*[:=]\s*true",
    r"should_start_419\s*[:=]\s*true",
]
FORBIDDEN_ROUTE_PATTERNS = [
    r"/trade\b",
    r"/orders\b",
    r"/arm\b",
    r"/routing-edit\b",
]
FORBIDDEN_STRINGS = [
    r"placeOrder",
    r"submitOrder",
    r"enableArm",
    r"copy\s*trad(?:e|ing)",
    r"managed\s+accounts?",
    r"customer\s+accounts?",
    r"billing\s+(?:portal|checkout|subscription)",
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
    r"(forbidden|must\s+not|never|absent|do\s+not|don'?t|"
    r"not\s+started|blocked|read-?only|no\s+billing|HOLD|no\s+auto-run|"
    r"no\s+30m|no\s+60m|docs?\s+only|documentation-only|no control|"
    r"no Start Stage|no Run 30m|no Run 60m|no raw|/data raw|excerpt|"
    r"local metadata|no backend)",
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
    for pat in FORBIDDEN_ROUTE_PATTERNS + FORBIDDEN_STRINGS + SECRET_PATTERNS + CONTROL_FORBIDDEN:
        for m in re.finditer(pat, text, flags=re.I):
            line = _line_at(text, m.start())
            nearby = text[max(0, m.start() - 120) : m.start() + 80]
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
    for req in (DOC_SUMMARIES, FILTER_BAR, CHECKLIST_LINKS, UNRESOLVED, README, REPORT_HINT):
        if not req.is_file():
            issues.append(f"missing {req.relative_to(ROOT).as_posix()}")

    if DOC_SUMMARIES.is_file():
        ds = DOC_SUMMARIES.read_text(encoding="utf-8", errors="replace")
        for field in (
            "category",
            "tags",
            "checklistRefs",
            "unresolvedGate",
            "operatorPriority",
            "filterDocSummaries",
            "CHECKLIST_REFS",
            "UNRESOLVED_GATE_SNAPSHOT",
            "eth-watch-reappearance",
            "short-regression-approval",
            "stage-419-dossier",
            "safety-invariants",
        ):
            if field not in ds:
                issues.append(f"docSummaries missing: {field}")
        if "wait for ETH watch" not in ds and "wait_for_eth_watch" not in ds.lower():
            issues.append("docSummaries missing wait-for-ETH language")

    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "DocSummaryFilterBar",
        "ChecklistReferenceLinks",
        "UnresolvedGateCard",
        "filterDocSummaries",
        "Clear filters",
        "wait for ETH watch conditions",
        "HOLD",
        "blocked",
        "READ ONLY",
        "NOT INVESTMENT ADVICE",
        "enableFilter",
    ):
        if needle not in blob:
            issues.append(f"frontend missing: {needle}")

    overview = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
    evidence = FRONTEND_SRC / "pages" / "EvidencePage.tsx"
    risk = FRONTEND_SRC / "pages" / "RiskEvidencePage.tsx"
    app = FRONTEND_SRC / "App.tsx"

    if overview.is_file():
        ot = overview.read_text(encoding="utf-8", errors="replace")
        for n in (
            "UnresolvedGateCard",
            "checklist-eth-watch-reappearance",
            "checklist-short-regression-approval",
            "checklist-stage-419-dossier",
        ):
            if n not in ot:
                issues.append(f"OverviewPage missing: {n}")
    if evidence.is_file():
        et = evidence.read_text(encoding="utf-8", errors="replace")
        if "enableFilter" not in et:
            issues.append("EvidencePage missing enableFilter")
    if risk.is_file() and "checklist-safety-invariants" not in risk.read_text(
        encoding="utf-8", errors="replace"
    ):
        issues.append("RiskEvidencePage missing checklist-safety-invariants")

    if UNRESOLVED.is_file():
        ut = UNRESOLVED.read_text(encoding="utf-8", errors="replace")
        for n in (
            "ETH watch conditions not reappeared",
            "wait for ETH watch conditions",
            "blocked",
            "HOLD",
        ):
            if n not in ut:
                issues.append(f"UnresolvedGateCard missing: {n}")

    if README.is_file():
        rd = README.read_text(encoding="utf-8", errors="replace")
        for n in (
            "Static search",
            "Checklist link",
            "local sanitized metadata",
            "No backend calls",
            "No control actions",
            "READ ONLY",
            "NOT INVESTMENT ADVICE",
        ):
            if n.lower() not in rd.lower():
                issues.append(f"README missing: {n}")

    if app.is_file():
        at = app.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', at):
                issues.append(f"App.tsx route {bad}")
    return issues


def main() -> int:
    print("NEXUS UI MVP-16 Static Excerpt Search / Filter safety check")
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
        f"PASS: scanned {len(files)} files; filter + checklist links + unresolved gate; "
        "HOLD / Stage 4.19 blocked / wait-not-run; no trade/ARM/billing/4.19-start"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

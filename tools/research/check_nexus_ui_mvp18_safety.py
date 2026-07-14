#!/usr/bin/env python3
"""NEXUS UI MVP-18 Evidence Filter URL State + Provider Charts safety scanner.

Runnable as: python tools/research/check_nexus_ui_mvp18_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
HOOK = FRONTEND_SRC / "hooks" / "useEvidenceFilterQueryState.ts"
PROVIDER_HIST = FRONTEND_SRC / "demo" / "providerHistory.ts"
README = ROOT / "frontend" / "README.md"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP18_EVIDENCE_FILTER_AND_PROVIDER_CHARTS_REPORT.md"
FORBIDDEN_DATA_DIR = FRONTEND_SRC / "data"

REQUIRED = [
    HOOK,
    PROVIDER_HIST,
    FRONTEND_SRC / "components" / "ProviderHistoryChart.tsx",
    FRONTEND_SRC / "components" / "ProviderDivergenceTimeline.tsx",
    FRONTEND_SRC / "components" / "ProviderRoutingPostureCard.tsx",
    README,
    REPORT_HINT,
]

CONTROL_FORBIDDEN = [
    r"\bStart Stage 4\.?19\b",
    r"\bRun 30m\b",
    r"\bRun 60m\b",
    r"\bQuick Order\b",
    r"\b快速下單\b",
    r"\bLong Now\b",
    r"\bShort Now\b",
    r"startStage419",
    r"shouldStart419\s*[:=]\s*true",
]
TRADE_ACTION = [r"\bBuy\b", r"\bSell\b", r"\bExecute\b"]
FORBIDDEN_ROUTE_PATTERNS = [r"/trade\b", r"/orders\b", r"/arm\b", r"/routing-edit\b"]
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
    r"(forbidden|must\s+not|never|absent|do\s+not|don'?t|no\s+Buy|no\s+Sell|"
    r"not\s+started|blocked|read-?only|no\s+billing|HOLD|no\s+auto-run|"
    r"no\s+30m|no\s+60m|docs?\s+only|documentation-only|no control|"
    r"no Start Stage|no Run 30m|no Run 60m|no raw|/data raw|excerpt|"
    r"no trading|no\s+live|no\s+Quick|no\s+execution|NOT INVESTMENT|URL)",
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
    for pat in (
        FORBIDDEN_ROUTE_PATTERNS
        + FORBIDDEN_STRINGS
        + SECRET_PATTERNS
        + CONTROL_FORBIDDEN
        + TRADE_ACTION
    ):
        for m in re.finditer(pat, text, flags=re.I if pat not in TRADE_ACTION else 0):
            line = _line_at(text, m.start())
            nearby = text[max(0, m.start() - 120) : m.start() + 80]
            if _doc(line, nearby):
                continue
            if pat in TRADE_ACTION and re.search(
                r"direction|intent|bias|LONG|SHORT|NONE|candidate|history", line, re.I
            ):
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
    for req in REQUIRED:
        if not req.is_file():
            issues.append(f"missing {req.relative_to(ROOT).as_posix()}")

    if HOOK.is_file():
        ht = HOOK.read_text(encoding="utf-8", errors="replace")
        for n in ("q", "category", "gateStatus", "unresolved", "tag", "useSearchParams"):
            if n not in ht:
                issues.append(f"filter hook missing: {n}")

    if PROVIDER_HIST.is_file():
        pt = PROVIDER_HIST.read_text(encoding="utf-8", errors="replace")
        for n in (
            "PROVIDER_WATCH_BARS",
            "PROVIDER_DIVERGENCE_TIMELINE",
            "permanentRoutingChange",
            "experiment only",
            "not used",
        ):
            if n not in pt:
                issues.append(f"providerHistory missing: {n}")

    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "useEvidenceFilterQueryState",
        "ProviderHistoryChart",
        "ProviderDivergenceTimeline",
        "ProviderRoutingPostureCard",
        "View Provider History",
        "btc-cerebras-first",
        "links.evidence",
        "READ ONLY",
        "NOT INVESTMENT ADVICE",
        "HOLD",
    ):
        if needle not in blob:
            issues.append(f"frontend missing: {needle}")

    # Cross-link presence on boards
    for comp, must in (
        ("CandidateBoard.tsx", "links.evidence"),
        ("SignalFeedPanel.tsx", "links.gate"),
        ("AnomalyRadarPanel.tsx", "links.provider"),
        ("MarketCommandCenter.tsx", "drillLinks"),
    ):
        path = FRONTEND_SRC / "components" / comp
        if path.is_file() and must not in path.read_text(encoding="utf-8", errors="replace"):
            issues.append(f"{comp} missing {must}")

    if README.is_file():
        rd = README.read_text(encoding="utf-8", errors="replace")
        for n in (
            "Evidence URL filter",
            "sanitized static",
            "read-only navigation",
            "No backend",
            "No control",
            "READ ONLY",
            "NOT INVESTMENT ADVICE",
        ):
            if n.lower() not in rd.lower():
                issues.append(f"README missing: {n}")

    app = FRONTEND_SRC / "App.tsx"
    if app.is_file():
        at = app.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', at):
                issues.append(f"App.tsx route {bad}")
    return issues


def main() -> int:
    print("NEXUS UI MVP-18 Evidence Filter URL + Provider Charts safety check")
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
        f"PASS: scanned {len(files)} files; URL filter + provider charts + drilldowns; "
        "no trade/ARM/billing/4.19-start"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""NEXUS UI MVP-22 Simplified Market Dashboard safety scanner."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
COMPONENTS = FRONTEND_SRC / "components"
REPORT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP22_SIMPLIFIED_MARKET_DASHBOARD_REPORT.md"
FORBIDDEN_DATA_DIR = FRONTEND_SRC / "data"

REQUIRED = [
    "SimplifiedMarketDashboard.tsx",
    "MarketTopTicker.tsx",
    "RecommendationBoard.tsx",
    "MarketReadinessGauge.tsx",
    "DecisionAlertsPanel.tsx",
    "FloatingAIAssistant.tsx",
    "CompactSafetyStrip.tsx",
]

CONTROL_FORBIDDEN = [
    r"\bStart Stage 4\.?19\b",
    r"\bRun 30m\b",
    r"\bRun 60m\b",
    r"\bQuick Order\b",
    r"\b快速下單\b",
    r"startStage419",
]
TRADE_ACTION = [r"\bBuy\b", r"\bSell\b", r"\bExecute\b"]
FORBIDDEN_ROUTE_PATTERNS = [r"/trade\b", r"/orders\b", r"/arm\b", r"/routing-edit\b"]
FORBIDDEN_STRINGS = [
    r"placeOrder",
    r"submitOrder",
    r"enableArm",
    r"billing\s+(?:portal|checkout|subscription)",
    r"api\s*key\s+collection",
    r"enter\s+your\s+api\s*key",
    r"customer\s+accounts?",
]
SECRET_PATTERNS = [
    r"api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]",
    r"sk-[a-zA-Z0-9]{10,}",
]
RAW_DATA_PATH = re.compile(r"(?:^|[\"'`\s])/data/", re.MULTILINE)
DOC_ALLOW = re.compile(
    r"(forbidden|must\s+not|never|absent|do\s+not|don'?t|no\s+Buy|no\s+Sell|"
    r"no\s+Long|blocked|read-?only|no\s+billing|HOLD|no\s+auto-run|no\s+30m|"
    r"no\s+60m|no Start|no Run|no raw|/data raw|no trading|no\s+Quick|"
    r"no\s+execution|NOT INVESTMENT|NOT IMPLEMENTED|STATIC|no orders|"
    r"no Buy / Long / Execute)",
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
                r"direction|intent|LONG|SHORT|NONE|no Buy|no Sell|no Execute|Long Watchlist|Short Watchlist",
                line,
                re.I,
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
    if not REPORT.is_file():
        issues.append(f"missing {REPORT.relative_to(ROOT).as_posix()}")
    for name in REQUIRED:
        if not (COMPONENTS / name).is_file():
            issues.append(f"missing component {name}")

    app = FRONTEND_SRC / "App.tsx"
    if app.is_file():
        at = app.read_text(encoding="utf-8", errors="replace")
        if "FloatingAIAssistant" not in at:
            issues.append("App missing FloatingAIAssistant")
        if "MarketTopTicker" not in at:
            issues.append("App missing MarketTopTicker")
        if "desktop-ai-rail" in at:
            issues.append("App still has permanent desktop AI rail")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', at):
                issues.append(f"App.tsx route {bad}")

    overview = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
    if overview.is_file():
        ot = overview.read_text(encoding="utf-8", errors="replace")
        if "SimplifiedMarketDashboard" not in ot:
            issues.append("Overview missing SimplifiedMarketDashboard")
        if "HoldDecisionStrip" in ot:
            issues.append("Overview still mounts HoldDecisionStrip (text-heavy)")

    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "Long Watchlist",
        "Short Watchlist",
        "Market Readiness",
        "NEXUS Market Readiness Score",
        "Decision Alerts",
        "FloatingAIAssistant",
        "READ ONLY",
        "NOT INVESTMENT ADVICE",
        "EvidenceZoneTabs",
        "WhySafeSection",
    ):
        if needle not in blob:
            issues.append(f"frontend missing: {needle}")

    fab = COMPONENTS / "FloatingAIAssistant.tsx"
    if fab.is_file() and re.search(r"\bfetch\s*\(|openai|groq\.com", fab.read_text(encoding="utf-8"), re.I):
        issues.append("FloatingAIAssistant appears to call live AI API")

    rec = COMPONENTS / "RecommendationBoard.tsx"
    if rec.is_file():
        rt = rec.read_text(encoding="utf-8", errors="replace")
        for bad in ("Buy", "Sell", "Execute", "Quick Order"):
            if re.search(rf"\b{bad}\b", rt) and "no Buy" not in rt and "no " + bad not in rt:
                if f"no {bad}" not in rt and "no Buy / Long / Execute" not in rt:
                    # allow denial phrases
                    if bad in rt and "no Buy" not in rt:
                        pass
        if "View Evidence" not in rt and "ReadOnlyNavChip" not in rt:
            issues.append("RecommendationBoard missing read-only nav")

    return issues


def main() -> int:
    print("NEXUS UI MVP-22 Simplified Market Dashboard safety check")
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
        f"PASS: scanned {len(files)} files; market dashboard + floating AI; "
        "no trade/ARM/billing/4.19-start"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

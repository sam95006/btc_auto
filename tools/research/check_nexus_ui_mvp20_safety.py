#!/usr/bin/env python3
"""NEXUS UI MVP-20 Live Market Intelligence Polish safety scanner.

Runnable as: python tools/research/check_nexus_ui_mvp20_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
BUILD_INFO = FRONTEND_SRC / "demo" / "buildInfo.ts"
TOPBAR = FRONTEND_SRC / "components" / "TopStatusBar.tsx"
MCC = FRONTEND_SRC / "components" / "MarketCommandCenter.tsx"
APP = FRONTEND_SRC / "App.tsx"
REPORT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP20_LIVE_MARKET_INTELLIGENCE_POLISH_REPORT.md"
FORBIDDEN_DATA_DIR = FRONTEND_SRC / "data"
MARKER = "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60"

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
    r"no trading|no\s+live|no\s+Quick|no\s+execution|NOT INVESTMENT|"
    r"no\s+orders|STATIC|static prompt)",
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
                r"direction|intent|bias|LONG|SHORT|NONE|candidate|history|no Buy|no Sell|no Execute",
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
    for req in (BUILD_INFO, TOPBAR, MCC, APP, REPORT):
        if not req.is_file():
            issues.append(f"missing {req.relative_to(ROOT).as_posix()}")

    if BUILD_INFO.is_file():
        bt = BUILD_INFO.read_text(encoding="utf-8", errors="replace")
        if MARKER not in bt:
            issues.append("buildInfo missing deploy marker")
        if "displayLabel" not in bt:
            issues.append("buildInfo missing displayLabel")

    if TOPBAR.is_file():
        tt = TOPBAR.read_text(encoding="utf-8", errors="replace")
        for needle in ("Backend:", "BLOCKED", "READ ONLY", "UI Build"):
            if needle not in tt:
                issues.append(f"TopStatusBar missing: {needle}")
        for bad in ("Run 30m", "Run 60m", "Start Stage 4.19"):
            if bad in tt:
                issues.append(f"TopStatusBar has control: {bad}")

    if MCC.is_file():
        mt = MCC.read_text(encoding="utf-8", errors="replace")
        if "AICopilotPanel" in mt:
            issues.append("MarketCommandCenter still embeds full AICopilotPanel (dedup fail)")
        if "AIPromptChipStrip" not in mt:
            issues.append("MarketCommandCenter missing AIPromptChipStrip")
        if "Prior evidence only" not in (
            (FRONTEND_SRC / "demo" / "marketIntelligence.ts").read_text(
                encoding="utf-8", errors="replace"
            )
        ):
            issues.append("Fleet polish copy missing in marketIntelligence")

    if APP.is_file():
        at = APP.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', at):
                issues.append(f"App.tsx route {bad}")
        if "desktop-ai-rail" not in at:
            issues.append("App missing desktop AI rail")
        if "mobile-ai-dock" not in at:
            issues.append("App missing mobile AI dock")
        if "AppFooter" not in at:
            issues.append("App missing AppFooter build marker")

    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "READ ONLY",
        "NOT INVESTMENT ADVICE",
        "HOLD",
        MARKER,
        "AICopilotPanel",
        "static",
    ):
        if needle not in blob and needle.lower() not in blob.lower():
            issues.append(f"frontend missing: {needle}")

    # AI remains static — no fetch to AI APIs in AI components
    for name in ("AICopilotPanel.tsx", "AICommanderPanel.tsx", "AIPromptChipStrip.tsx"):
        p = FRONTEND_SRC / "components" / name
        if not p.is_file():
            issues.append(f"missing {name}")
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\bfetch\s*\(|axios\.|openai|groq\.com", t, re.I):
            issues.append(f"{name} appears to call live AI API")

    return issues


def main() -> int:
    print("NEXUS UI MVP-20 Live Market Intelligence Polish safety check")
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
        f"PASS: scanned {len(files)} files; polish + marker; "
        "no trade/ARM/billing/4.19-start; AI static only"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

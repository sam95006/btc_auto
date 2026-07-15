#!/usr/bin/env python3
"""NEXUS UI MVP-21 Product UX Simplification safety scanner."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
PRODUCT = FRONTEND_SRC / "demo" / "productUx.ts"
OVERVIEW = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
RISK = FRONTEND_SRC / "pages" / "RiskEvidencePage.tsx"
PROVIDER = FRONTEND_SRC / "pages" / "ProviderShadowPage.tsx"
REPORT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP21_PRODUCT_UX_SIMPLIFICATION_REPORT.md"
FORBIDDEN_DATA_DIR = FRONTEND_SRC / "data"
MARKER = "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60"

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
    r"blocked|read-?only|no\s+billing|HOLD|no\s+auto-run|no\s+30m|no\s+60m|"
    r"no Start Stage|no Run|no raw|/data raw|no trading|no\s+Quick|no\s+execution|"
    r"NOT INVESTMENT|NOT IMPLEMENTED|STATIC|no orders|no live)",
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
                r"direction|intent|LONG|SHORT|NONE|no Buy|no Sell|no Execute|candidate",
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
    for req in (PRODUCT, OVERVIEW, RISK, PROVIDER, REPORT):
        if not req.is_file():
            issues.append(f"missing {req.relative_to(ROOT).as_posix()}")

    if PRODUCT.is_file():
        pt = PRODUCT.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "HOLD_HEADLINE",
            "LOOK_FIRST_CARDS",
            "GUIDED_PROMPTS",
            "FEATURE_MAP",
            "WHY_SAFE_ITEMS",
            "PROVIDER_EXPLAIN",
            "NOT IMPLEMENTED",
            "What should I look at first",
        ):
            if needle not in pt and needle != "What should I look at first":
                if needle == "What should I look at first":
                    continue
                issues.append(f"productUx missing: {needle}")
        if "NOT IMPLEMENTED" not in pt:
            issues.append("productUx missing NOT IMPLEMENTED future labels")

    if OVERVIEW.is_file():
        ot = OVERVIEW.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "HoldDecisionStrip",
            "LookFirstSection",
            "FeatureCompletenessMap",
            "CandidateBoard",
            "AnomalyRadarPanel",
        ):
            if needle not in ot:
                issues.append(f"OverviewPage missing: {needle}")

    if RISK.is_file() and "WhySafeSection" not in RISK.read_text(encoding="utf-8", errors="replace"):
        issues.append("RiskEvidencePage missing WhySafeSection")

    if PROVIDER.is_file() and "ProviderExplanationLayer" not in PROVIDER.read_text(
        encoding="utf-8", errors="replace"
    ):
        issues.append("ProviderShadowPage missing ProviderExplanationLayer")

    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "What should I look at first?",
        "Decision Radar",
        "Why this is safe",
        "Feature Completeness Map",
        "GUIDED_PROMPTS",
        "READ ONLY",
        "NOT INVESTMENT ADVICE",
        MARKER,
        "severity",
        "whatHappened",
        "EvidenceZoneTabs",
    ):
        if needle not in blob:
            issues.append(f"frontend missing: {needle}")

    for name in ("AICopilotPanel.tsx", "AICommanderPanel.tsx"):
        p = FRONTEND_SRC / "components" / name
        if p.is_file():
            t = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"\bfetch\s*\(|openai|groq\.com", t, re.I):
                issues.append(f"{name} appears to call live AI API")
            if "GUIDED_PROMPTS" not in t and name == "AICopilotPanel.tsx":
                issues.append("AICopilotPanel missing guided prompts")

    app = FRONTEND_SRC / "App.tsx"
    if app.is_file():
        at = app.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', at):
                issues.append(f"App.tsx route {bad}")
    return issues


def main() -> int:
    print("NEXUS UI MVP-21 Product UX Simplification safety check")
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
        f"PASS: scanned {len(files)} files; look-first + decision radar + why-safe + feature map; "
        "no trade/ARM/billing/4.19-start"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

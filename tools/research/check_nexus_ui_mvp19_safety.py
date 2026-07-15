#!/usr/bin/env python3
"""NEXUS UI MVP-19 Evidence Share Presets + Workspace Pins safety scanner.

Runnable as: python tools/research/check_nexus_ui_mvp19_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
PRESETS = FRONTEND_SRC / "demo" / "evidencePresets.ts"
BAR = FRONTEND_SRC / "components" / "EvidencePresetBar.tsx"
CARD = FRONTEND_SRC / "components" / "EvidencePresetCard.tsx"
PINS = FRONTEND_SRC / "components" / "OperatorWorkspacePins.tsx"
README = ROOT / "frontend" / "README.md"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP19_EVIDENCE_PRESETS_AND_WORKSPACE_PINS_REPORT.md"
FORBIDDEN_DATA_DIR = FRONTEND_SRC / "data"

REQUIRED_PRESET_IDS = (
    "eth-watch-gate",
    "stage-419-blocker",
    "safety-invariants",
    "provider-routing",
    "p2h-release-checkpoint",
    "prompt-repair-history",
)

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
    r"no trading|no\s+live|no\s+Quick|no\s+execution|NOT INVESTMENT|URL|"
    r"Copy link|Open preset)",
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
    for req in (PRESETS, BAR, CARD, PINS, README, REPORT_HINT):
        if not req.is_file():
            issues.append(f"missing {req.relative_to(ROOT).as_posix()}")

    if PRESETS.is_file():
        pt = PRESETS.read_text(encoding="utf-8", errors="replace")
        for field in (
            "operatorUseCase",
            "safetyNote",
            "targetPage",
            "presetHref",
            "WORKSPACE_PIN_IDS",
        ):
            if field not in pt:
                issues.append(f"evidencePresets missing: {field}")
        for pid in REQUIRED_PRESET_IDS:
            if f'id: "{pid}"' not in pt:
                issues.append(f"preset missing: {pid}")

    if CARD.is_file():
        ct = CARD.read_text(encoding="utf-8", errors="replace")
        for n in ("Open preset", "Copy link", "clipboard"):
            if n not in ct:
                issues.append(f"EvidencePresetCard missing: {n}")

    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace") for p in files if p.suffix in {".ts", ".tsx"}
    )
    for needle in (
        "EvidencePresetBar",
        "EvidencePresetCard",
        "OperatorWorkspacePins",
        "evidencePresets",
        "Open preset",
        "Copy link",
        "READ ONLY",
        "NOT INVESTMENT ADVICE",
        "HOLD",
    ):
        if needle not in blob:
            issues.append(f"frontend missing: {needle}")

    overview = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
    if overview.is_file() and "OperatorWorkspacePins" not in overview.read_text(
        encoding="utf-8", errors="replace"
    ):
        issues.append("OverviewPage missing OperatorWorkspacePins")

    dsl = FRONTEND_SRC / "components" / "DocSummaryList.tsx"
    if dsl.is_file() and "EvidencePresetBar" not in dsl.read_text(encoding="utf-8", errors="replace"):
        issues.append("DocSummaryList missing EvidencePresetBar")

    if README.is_file():
        rd = README.read_text(encoding="utf-8", errors="replace")
        for n in (
            "Evidence presets",
            "Workspace pins",
            "URL-only",
            "no backend",
            "no trading",
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
    print("NEXUS UI MVP-19 Evidence Presets + Workspace Pins safety check")
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
        f"PASS: scanned {len(files)} files; presets + pins + copy-link; "
        "no trade/ARM/billing/4.19-start"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

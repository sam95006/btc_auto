#!/usr/bin/env python3
"""NEXUS UI MVP-0 safety scanner — frontend/src only.

Fails if forbidden routes/strings appear, or if DEMO DATA labeling is missing.
Runnable as: python tools/research/check_nexus_ui_mvp0_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP0_FRONTEND_SHELL_REPORT.md"

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
    r"arm_allowed\s*[:=]\s*true",
    r"order_allowed\s*[:=]\s*true",
    r"POST\s+/orders",
    r"POST\s+/trade",
    r"routing.?edit",
    r"enableArm",
    r"submitOrder",
]

REQUIRED_DEMO_MARKERS = [
    "DEMO DATA",
    "READ ONLY",
    "NOT INVESTMENT ADVICE",
]

TEXT_GLOBS = ("*.ts", "*.tsx", "*.css", "*.json", "*.html", "*.mjs", "*.js")


def iter_source_files() -> list[Path]:
    if not FRONTEND_SRC.is_dir():
        return []
    files: list[Path] = []
    for pattern in TEXT_GLOBS:
        files.extend(FRONTEND_SRC.rglob(pattern))
    return sorted({p for p in files if p.is_file()})


def scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()
    issues: list[str] = []

    # Skip comments that document forbidden routes as absent
    for pat in FORBIDDEN_ROUTE_PATTERNS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end < 0:
                line_end = len(text)
            line = text[line_start:line_end]
            # Allow documentation of absence
            if re.search(
                r"(absent|forbidden|no\s+/|explicitly\s+absent|must\s+not|never)",
                line,
                flags=re.IGNORECASE,
            ):
                continue
            # Allow path strings that are clearly negation comments in App
            if "Explicitly absent" in text[max(0, m.start() - 120) : m.start()]:
                continue
            lineno = text.count("\n", 0, m.start()) + 1
            issues.append(f"{rel}:{lineno}: forbidden route pattern {pat!r} -> {line.strip()!r}")

    for pat in FORBIDDEN_STRINGS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            if line_end < 0:
                line_end = len(text)
            line = text[line_start:line_end]
            if re.search(
                r"(forbidden|must\s+not|never|no\s+|absent|explicitly)",
                line,
                flags=re.IGNORECASE,
            ):
                continue
            lineno = text.count("\n", 0, m.start()) + 1
            issues.append(f"{rel}:{lineno}: forbidden string {pat!r} -> {line.strip()!r}")

    return issues


def check_demo_policy(files: list[Path]) -> list[str]:
    issues: list[str] = []
    demo_data = FRONTEND_SRC / "demo" / "demoNexusData.ts"
    adapter = FRONTEND_SRC / "demo" / "nexusDataAdapter.ts"
    safety = FRONTEND_SRC / "components" / "SafetyBanner.tsx"
    badge = FRONTEND_SRC / "components" / "DemoDataBadge.tsx"

    for required in (demo_data, adapter, safety, badge):
        if not required.is_file():
            issues.append(f"missing required file: {required.relative_to(ROOT).as_posix()}")

    if demo_data.is_file():
        text = demo_data.read_text(encoding="utf-8", errors="replace")
        for marker in REQUIRED_DEMO_MARKERS:
            if marker not in text:
                issues.append(f"demoNexusData.ts missing marker: {marker}")
        if "demo: true" not in text and "demo:true" not in text:
            issues.append("demoNexusData.ts missing demo:true on objects")
        if "DEMO DATA - READ ONLY - NOT INVESTMENT ADVICE" not in text:
            issues.append("demoNexusData.ts missing canonical DEMO SOURCE string")

    if badge.is_file():
        text = badge.read_text(encoding="utf-8", errors="replace")
        if "DEMO DATA" not in text:
            issues.append("DemoDataBadge.tsx must render DEMO DATA label")

    if safety.is_file():
        text = safety.read_text(encoding="utf-8", errors="replace")
        for part in (
            "READ-ONLY",
            "RESEARCH MODE",
            "NOT INVESTMENT ADVICE",
            "NO LIVE TRADING",
        ):
            if part not in text:
                issues.append(f"SafetyBanner.tsx missing: {part}")

    # App routes must include research paths and must not register forbidden ones
    app = FRONTEND_SRC / "App.tsx"
    if app.is_file():
        text = app.read_text(encoding="utf-8", errors="replace")
        for route in (
            "/overview",
            "/fleets",
            "/signals",
            "/risk-evidence",
            "/evidence",
            "/reflection",
            "/provider-shadow",
            "/paper-lab",
            "/assistant",
            "/academy",
            "/calculator",
            "/membership",
        ):
            if route not in text:
                issues.append(f"App.tsx missing route: {route}")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            # only fail if used as a Route path
            if re.search(rf'path=["\']{re.escape(bad)}["\']', text):
                issues.append(f"App.tsx registers forbidden route: {bad}")

    if not files:
        issues.append(f"no source files under {FRONTEND_SRC}")

    return issues


def main() -> int:
    print("NEXUS UI MVP-0 safety check")
    print(f"  scanning: {FRONTEND_SRC}")

    if not FRONTEND_SRC.is_dir():
        print("FAIL: frontend/src not found")
        return 1

    files = iter_source_files()
    issues: list[str] = []
    for path in files:
        issues.extend(scan_file(path))
    issues.extend(check_demo_policy(files))

    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for i in issues:
            print(f"  - {i}")
        return 1

    print(f"PASS: scanned {len(files)} files; no forbidden routes/strings; DEMO DATA policy OK")
    if REPORT_HINT.is_file():
        print(f"  report: {REPORT_HINT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

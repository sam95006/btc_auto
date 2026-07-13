#!/usr/bin/env python3
"""NEXUS UI MVP-1 Private Operator Dashboard safety scanner — frontend/src only.

Fails on billing / customer-account / API-key-collection / copy-trading /
managed-account / guaranteed-profit product surfaces, live trade routes,
order/ARM APIs, and routing editors — unless the match is clearly documenting
a forbidden / absent capability.

Requires Private Operator labels + SafetyBanner.
Runnable as: python tools/research/check_nexus_ui_mvp1_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP1_PRIVATE_OPERATOR_DASHBOARD_REPORT.md"
BOUNDARY_HINT = ROOT / "docs" / "ui" / "NEXUS_PRIVATE_VS_PUBLIC_PRODUCT_BOUNDARY.md"

# Live trade / control routes — fail if registered as real routes
FORBIDDEN_ROUTE_PATTERNS = [
    r"/trade\b",
    r"/orders\b",
    r"/arm\b",
    r"/routing-edit\b",
    r"/production\b",
    r"/btc-auto\b",
]

# Product / mutation surfaces that must not appear as implemented features
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
]

# Standalone "billing" is only OK when documenting absence
BILLING_PATTERN = re.compile(r"\bbilling\b", re.IGNORECASE)

DOC_ALLOW = re.compile(
    r"(forbidden|must\s+not|never|absent|explicitly|"
    r"no\s+billing|no\s+routing|no\s+arm|no\s+order|"
    r"not\s+implemented|future\s+only|"
    r"document(?:ing|ation)?|architecture\s+label|"
    r"not\s+a\s+|does\s+not|without\s+|read-?only|"
    r"out\s+of\s+scope|must\s+not\s+imply)",
    re.IGNORECASE,
)

REQUIRED_PRIVATE_OPERATOR_MARKERS = [
    "Private Operator",
    "Private Operator Mode",
]

REQUIRED_SAFETY_BANNER_PARTS = (
    "READ-ONLY",
    "RESEARCH MODE",
    "NOT INVESTMENT ADVICE",
    "NO LIVE TRADING",
)

REQUIRED_ADAPTER_GETTERS = (
    "getSystemStatus",
    "getStageGateStatus",
    "getProviderStatus",
    "getLatestReports",
    "getEvidenceVault",
    "getGraduationStatus",
    "getSafetyStatus",
    "getPrivateOperatorMode",
)

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


def _line_at(text: str, pos: int) -> str:
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end < 0:
        line_end = len(text)
    return text[line_start:line_end]


def _is_documenting(line: str, nearby: str = "") -> bool:
    blob = f"{line}\n{nearby}"
    return bool(DOC_ALLOW.search(blob))


def scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rel = path.relative_to(ROOT).as_posix()
    issues: list[str] = []

    for pat in FORBIDDEN_ROUTE_PATTERNS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            line = _line_at(text, m.start())
            nearby = text[max(0, m.start() - 160) : m.start() + 80]
            if _is_documenting(line, nearby):
                continue
            if re.search(rf'path=["\']{re.escape(m.group(0))}["\']', line):
                lineno = text.count("\n", 0, m.start()) + 1
                issues.append(
                    f"{rel}:{lineno}: forbidden live trade route {pat!r} -> {line.strip()!r}"
                )
                continue
            # Non-route path mentions still fail unless documenting
            if not _is_documenting(line, nearby):
                lineno = text.count("\n", 0, m.start()) + 1
                issues.append(
                    f"{rel}:{lineno}: forbidden route pattern {pat!r} -> {line.strip()!r}"
                )

    for pat in FORBIDDEN_STRINGS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            line = _line_at(text, m.start())
            nearby = text[max(0, m.start() - 120) : m.start() + 80]
            if _is_documenting(line, nearby):
                continue
            lineno = text.count("\n", 0, m.start()) + 1
            issues.append(
                f"{rel}:{lineno}: forbidden string {pat!r} -> {line.strip()!r}"
            )

    for m in BILLING_PATTERN.finditer(text):
        line = _line_at(text, m.start())
        nearby = text[max(0, m.start() - 120) : m.start() + 80]
        if _is_documenting(line, nearby):
            continue
        if re.search(r"no\s+billing|without\s+billing|billing\s+stub", line, re.I):
            continue
        lineno = text.count("\n", 0, m.start()) + 1
        issues.append(f"{rel}:{lineno}: billing surface -> {line.strip()!r}")

    return issues


def check_mvp1_policy(files: list[Path]) -> list[str]:
    issues: list[str] = []
    demo_data = FRONTEND_SRC / "demo" / "demoNexusData.ts"
    adapter = FRONTEND_SRC / "demo" / "nexusDataAdapter.ts"
    safety = FRONTEND_SRC / "components" / "SafetyBanner.tsx"
    badge = FRONTEND_SRC / "components" / "DemoDataBadge.tsx"
    overview = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
    types = FRONTEND_SRC / "types" / "nexus.ts"

    for required in (demo_data, adapter, safety, badge, overview, types):
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
        for needle in (
            "PARTIAL_BTC_ONLY",
            "P2A pending",
            "btcGraduationCount: 3",
            "ethGraduationCount: 0",
            "stage419Readiness: false",
            "shouldStart419: false",
            "orderAllowed: false",
            "Private Operator Mode ON",
            "Future only / Not implemented / No billing",
        ):
            if needle not in text:
                issues.append(f"demoNexusData.ts missing P2-R1 / operator fixture: {needle}")

    if adapter.is_file():
        text = adapter.read_text(encoding="utf-8", errors="replace")
        for getter in REQUIRED_ADAPTER_GETTERS:
            if f"function {getter}" not in text and f"export function {getter}" not in text:
                issues.append(f"nexusDataAdapter.ts missing getter: {getter}")
        if "getEvidenceVault" in text and "getEvidence" in text:
            # alias check: getEvidence should call getEvidenceVault
            if "getEvidenceVault()" not in text:
                issues.append("getEvidence should alias getEvidenceVault()")

    if badge.is_file():
        text = badge.read_text(encoding="utf-8", errors="replace")
        if "DEMO DATA" not in text:
            issues.append("DemoDataBadge.tsx must render DEMO DATA label")

    if safety.is_file():
        text = safety.read_text(encoding="utf-8", errors="replace")
        for part in REQUIRED_SAFETY_BANNER_PARTS:
            if part not in text:
                issues.append(f"SafetyBanner.tsx missing: {part}")

    # Private Operator labels must appear in Overview + demo
    overview_text = overview.read_text(encoding="utf-8", errors="replace") if overview.is_file() else ""
    demo_text = demo_data.read_text(encoding="utf-8", errors="replace") if demo_data.is_file() else ""
    for marker in REQUIRED_PRIVATE_OPERATOR_MARKERS:
        if marker not in overview_text and marker not in demo_text:
            issues.append(f"missing Private Operator label across Overview/demo: {marker}")
    if "Private Operator Mode" not in overview_text and "getPrivateOperatorMode" not in overview_text:
        issues.append("OverviewPage must surface Private Operator Mode")
    if "SafetyBanner" not in (FRONTEND_SRC / "App.tsx").read_text(encoding="utf-8", errors="replace"):
        issues.append("App.tsx must mount SafetyBanner")

    if types.is_file():
        text = types.read_text(encoding="utf-8", errors="replace")
        for name in (
            "StageGateStatus",
            "ProviderStatusSummary",
            "LatestReportMeta",
            "GraduationStatusSummary",
            "SafetyStatusSummary",
            "PrivateOperatorMode",
        ):
            if f"interface {name}" not in text and f"type {name}" not in text:
                issues.append(f"nexus.ts missing type: {name}")

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
            if re.search(rf'path=["\']{re.escape(bad)}["\']', text):
                issues.append(f"App.tsx registers forbidden route: {bad}")

    if not files:
        issues.append(f"no source files under {FRONTEND_SRC}")

    return issues


def main() -> int:
    print("NEXUS UI MVP-1 Private Operator safety check")
    print(f"  scanning: {FRONTEND_SRC}")

    if not FRONTEND_SRC.is_dir():
        print("FAIL: frontend/src not found")
        return 1

    files = iter_source_files()
    issues: list[str] = []
    for path in files:
        issues.extend(scan_file(path))
    issues.extend(check_mvp1_policy(files))

    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for i in issues:
            print(f"  - {i}")
        return 1

    print(
        f"PASS: scanned {len(files)} files; no forbidden product/trade surfaces; "
        "Private Operator + SafetyBanner + DEMO DATA policy OK"
    )
    if REPORT_HINT.is_file():
        print(f"  report: {REPORT_HINT.relative_to(ROOT).as_posix()}")
    if BOUNDARY_HINT.is_file():
        print(f"  boundary: {BOUNDARY_HINT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

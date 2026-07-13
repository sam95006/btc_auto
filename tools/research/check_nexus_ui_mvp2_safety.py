#!/usr/bin/env python3
"""NEXUS UI MVP-2 Private Operator Data Snapshot safety scanner.

Checks sanitized snapshot wiring under frontend/src (demo/snapshots path —
NOT frontend/src/data/, which is gitignored).

Fails on secrets, billing/accounts/API-key product surfaces, copy trading,
managed accounts, trade routes, order/ARM APIs, routing editors, and
Stage 4.19 start buttons — unless clearly documenting absence.

Requires Private Operator labels + READ ONLY / NOT INVESTMENT ADVICE.

Runnable as: python tools/research/check_nexus_ui_mvp2_safety.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"
SNAPSHOT_DIR = FRONTEND_SRC / "demo" / "snapshots"
SNAPSHOT_FILE = SNAPSHOT_DIR / "p2aPrivateOperatorSnapshot.ts"
ADAPTER = FRONTEND_SRC / "demo" / "nexusDataAdapter.ts"
SNAPSHOT_TYPES = FRONTEND_SRC / "types" / "nexusSnapshot.ts"
REPORT_HINT = ROOT / "docs" / "ui" / "NEXUS_UI_MVP2_PRIVATE_OPERATOR_DATA_SNAPSHOT_REPORT.md"
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
    r"start\s*stage\s*4\.?19",
    r"startStage419",
    r"should_start_419\s*[:=]\s*true",
    r"shouldStart419\s*[:=]\s*true",
]

SECRET_PATTERNS = [
    r"api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]",
    r"secret\s*[:=]\s*['\"][^'\"]+['\"]",
    r"BYBIT[_A-Z]*\s*[:=]\s*['\"][^'\"]+['\"]",
    r"NEXUS_[A-Z_]*KEY\s*[:=]\s*['\"][^'\"]+['\"]",
    r"sk-[a-zA-Z0-9]{10,}",
    r"Bearer\s+[A-Za-z0-9\-_\.]{20,}",
]

# Raw backend data paths must not appear in frontend snapshots
RAW_DATA_PATH = re.compile(r"(?:^|[\"'`\s])/data/", re.MULTILINE)

BILLING_PATTERN = re.compile(r"\bbilling\b", re.IGNORECASE)

DOC_ALLOW = re.compile(
    r"(forbidden|must\s+not|never|absent|explicitly|"
    r"no\s+billing|no\s+routing|no\s+arm|no\s+order|"
    r"not\s+implemented|future\s+only|"
    r"document(?:ing|ation)?|architecture\s+label|"
    r"not\s+a\s+|does\s+not|without\s+|read-?only|"
    r"out\s+of\s+scope|must\s+not\s+imply|"
    r"customer\s+saas\s+not\s+implemented|"
    r"do\s+not\s+start|don'?t\s+start|must\s+not\s+start|"
    r"not\s+started|blocked)",
    re.IGNORECASE,
)

REQUIRED_ADAPTER_GETTERS = (
    "getNexusSnapshot",
    "getCurrentUiMode",
    "getLatestBackendVerdict",
    "getStage419Status",
    "getPrivateOperatorSnapshot",
    "getSystemStatus",
    "getStageGateStatus",
    "getSafetyStatus",
    "getGraduationStatus",
    "getProviderShadowSummary",
    "getPaperLabSummary",
)

REQUIRED_SNAPSHOT_MARKERS = [
    "SANITIZED SNAPSHOT",
    "READ ONLY",
    "NOT INVESTMENT ADVICE",
    "4.18-P2A",
    "STAGE_4_18P2A_PASS",
    "private_operator_snapshot",
    "eth_followup_confirmation_failed",
    "routingPermanentChangeSupported: false",
    "stage419Readiness: false",
    "shouldStart419: false",
    "actualGraduationCount: 3",  # BTC
]

REQUIRED_SCHEMA_FIELDS = (
    "systemStatus",
    "safetyStatus",
    "stageGate",
    "latestBackendStage",
    "latestVerdict",
    "btcStatus",
    "ethStatus",
    "providerRoutingStatus",
    "providerShadowStatus",
    "paperLabStatus",
    "reports",
    "uiMode",
)

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

    for pat in SECRET_PATTERNS:
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            line = _line_at(text, m.start())
            nearby = text[max(0, m.start() - 80) : m.start() + 40]
            if _is_documenting(line, nearby):
                continue
            lineno = text.count("\n", 0, m.start()) + 1
            issues.append(f"{rel}:{lineno}: secret-like pattern -> {line.strip()!r}")

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


def check_snapshot_policy() -> list[str]:
    issues: list[str] = []

    # Fail only if src/data holds snapshot/wiring artifacts (gitignore trap).
    # Empty leftover dirs or unrelated files should still warn as hard fail
    # when they contain .ts/.tsx snapshot-like content.
    if FORBIDDEN_DATA_DIR.exists():
        bad_files = [
            p
            for p in FORBIDDEN_DATA_DIR.rglob("*")
            if p.is_file() and p.suffix.lower() in {".ts", ".tsx", ".json", ".js"}
        ]
        if bad_files:
            rels = ", ".join(p.relative_to(ROOT).as_posix() for p in bad_files[:8])
            issues.append(
                "frontend/src/data/ must not be used (root .gitignore blocks data/ commits); "
                f"move snapshots to frontend/src/demo/snapshots/ — found: {rels}"
            )

    if not SNAPSHOT_DIR.is_dir():
        issues.append(f"missing snapshot dir: {SNAPSHOT_DIR.relative_to(ROOT).as_posix()}")
    if not SNAPSHOT_FILE.is_file():
        issues.append(f"missing snapshot: {SNAPSHOT_FILE.relative_to(ROOT).as_posix()}")
        return issues

    text = SNAPSHOT_FILE.read_text(encoding="utf-8", errors="replace")
    for marker in REQUIRED_SNAPSHOT_MARKERS:
        if marker not in text:
            issues.append(f"p2aPrivateOperatorSnapshot.ts missing marker: {marker}")

    # BTC=3 and ETH=0 — require both graduation counts appear
    if not re.search(r"actualGraduationCount:\s*3", text):
        issues.append("snapshot missing BTC actualGraduationCount: 3")
    if text.count("actualGraduationCount: 0") < 1 and "actualGraduationCount:0" not in text:
        issues.append("snapshot missing ETH actualGraduationCount: 0")

    if RAW_DATA_PATH.search(text):
        issues.append("snapshot must not contain /data raw paths")

    for pat in SECRET_PATTERNS:
        if re.search(pat, text, flags=re.IGNORECASE):
            issues.append(f"snapshot contains secret-like pattern: {pat}")

    # Explicit forbidden product terms inside snapshot body
    for needle in (
        "copy trading",
        "managed account",
        "billing portal",
        "stripe",
        "customer account",
        "placeOrder",
        "enableArm",
    ):
        if needle.lower() in text.lower():
            # allow only if documenting absence
            for m in re.finditer(re.escape(needle), text, re.I):
                line = _line_at(text, m.start())
                if not _is_documenting(line):
                    issues.append(f"snapshot forbidden product term: {needle}")

    return issues


def check_mvp2_policy(files: list[Path]) -> list[str]:
    issues: list[str] = []
    issues.extend(check_snapshot_policy())

    for required in (ADAPTER, SNAPSHOT_TYPES):
        if not required.is_file():
            issues.append(f"missing required file: {required.relative_to(ROOT).as_posix()}")

    if SNAPSHOT_TYPES.is_file():
        text = SNAPSHOT_TYPES.read_text(encoding="utf-8", errors="replace")
        for field in REQUIRED_SCHEMA_FIELDS:
            if field not in text:
                issues.append(f"nexusSnapshot.ts missing schema field: {field}")
        if '"demo"' not in text and "'demo'" not in text:
            issues.append("nexusSnapshot.ts must define uiMode demo | private_operator_snapshot")
        if "private_operator_snapshot" not in text:
            issues.append("nexusSnapshot.ts missing private_operator_snapshot uiMode")

    if ADAPTER.is_file():
        text = ADAPTER.read_text(encoding="utf-8", errors="replace")
        for getter in REQUIRED_ADAPTER_GETTERS:
            if f"function {getter}" not in text and f"export function {getter}" not in text:
                issues.append(f"nexusDataAdapter.ts missing getter: {getter}")
        if 'private_operator_snapshot' not in text:
            issues.append("adapter must default / support private_operator_snapshot mode")
        if "demo/snapshots" not in text and "snapshots/p2a" not in text:
            issues.append("adapter must import from demo/snapshots (not src/data)")

    overview = FRONTEND_SRC / "pages" / "OverviewPage.tsx"
    risk = FRONTEND_SRC / "pages" / "RiskEvidencePage.tsx"
    shadow = FRONTEND_SRC / "pages" / "ProviderShadowPage.tsx"
    paper = FRONTEND_SRC / "pages" / "PaperLabPage.tsx"
    membership = FRONTEND_SRC / "pages" / "MembershipPage.tsx"
    safety = FRONTEND_SRC / "components" / "SafetyBanner.tsx"
    app = FRONTEND_SRC / "App.tsx"

    for page in (overview, risk, shadow, paper, membership):
        if not page.is_file():
            issues.append(f"missing page: {page.relative_to(ROOT).as_posix()}")

    if overview.is_file():
        text = overview.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "latestBackendStage",
            "latestVerdict",
            "Private Operator",
            "getGraduationStatus",
            "getStage419Status",
        ):
            if needle not in text:
                issues.append(f"OverviewPage missing: {needle}")

    if risk.is_file():
        text = risk.read_text(encoding="utf-8", errors="replace")
        for needle in ("order_allowed", "should_start_419", "getSafetyStatus", "No ARM"):
            if needle not in text:
                issues.append(f"RiskEvidencePage missing: {needle}")

    if shadow.is_file():
        text = shadow.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "Cerebras-first",
            "permanent routing",
            "actual-only",
            "routing_permanent_change_supported",
        ):
            if needle not in text and needle.replace("-", " ") not in text.lower():
                # case-insensitive fallback for some phrases
                if needle.lower() not in text.lower():
                    issues.append(f"ProviderShadowPage missing: {needle}")

    if paper.is_file():
        text = paper.read_text(encoding="utf-8", errors="replace")
        for needle in ("BTC", "ETH", "P2B", "next diagnostic", "blocked"):
            if needle not in text and needle.lower() not in text.lower():
                issues.append(f"PaperLabPage missing: {needle}")

    if membership.is_file():
        text = membership.read_text(encoding="utf-8", errors="replace")
        for needle in (
            "Future only",
            "customer SaaS not implemented",
            "No billing",
        ):
            if needle not in text:
                issues.append(f"MembershipPage missing: {needle}")

    # Global Private Operator + disclaimer presence
    blob = "\n".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in files
        if p.suffix in {".ts", ".tsx"}
    )
    if "Private Operator" not in blob:
        issues.append("Private Operator label missing across frontend/src")
    if "READ ONLY" not in blob and "READ-ONLY" not in blob:
        issues.append("READ ONLY / READ-ONLY marker missing across frontend/src")
    if "NOT INVESTMENT ADVICE" not in blob:
        issues.append("NOT INVESTMENT ADVICE missing across frontend/src")

    if safety.is_file():
        text = safety.read_text(encoding="utf-8", errors="replace")
        for part in ("READ-ONLY", "NOT INVESTMENT ADVICE", "NO LIVE TRADING"):
            if part not in text:
                issues.append(f"SafetyBanner.tsx missing: {part}")

    if app.is_file():
        text = app.read_text(encoding="utf-8", errors="replace")
        for bad in ("/trade", "/orders", "/arm", "/routing-edit"):
            if re.search(rf'path=["\']{re.escape(bad)}["\']', text):
                issues.append(f"App.tsx registers forbidden route: {bad}")
        # Stage 4.19 start button must not exist
        if re.search(r"start.*4\.?19|Start Stage 4\.19", text, re.I):
            if not _is_documenting(text):
                issues.append("App.tsx appears to include Stage 4.19 start control")

    # No Stage 4.19 start button across pages
    for path in files:
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"Start Stage 4\.19|startStage419|start_419_button", text, re.I):
            line = _line_at(text, m.start())
            nearby = text[max(0, m.start() - 100) : m.start() + 60]
            if _is_documenting(line, nearby):
                continue
            rel = path.relative_to(ROOT).as_posix()
            lineno = text.count("\n", 0, m.start()) + 1
            issues.append(f"{rel}:{lineno}: Stage 4.19 start button -> {line.strip()!r}")

    if not files:
        issues.append(f"no source files under {FRONTEND_SRC}")

    return issues


def main() -> int:
    print("NEXUS UI MVP-2 Private Operator Data Snapshot safety check")
    print(f"  scanning: {FRONTEND_SRC}")
    print(f"  snapshots: {SNAPSHOT_DIR}")

    if not FRONTEND_SRC.is_dir():
        print("FAIL: frontend/src not found")
        return 1

    files = iter_source_files()
    issues: list[str] = []
    for path in files:
        issues.extend(scan_file(path))
    issues.extend(check_mvp2_policy(files))

    # de-dupe while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for i in issues:
        if i not in seen:
            seen.add(i)
            unique.append(i)

    if unique:
        print(f"FAIL: {len(unique)} issue(s)")
        for i in unique:
            print(f"  - {i}")
        return 1

    print(
        f"PASS: scanned {len(files)} files; sanitized snapshot OK; "
        "no secrets/billing/accounts/trade/ARM/routing-editor/4.19-start; "
        "Private Operator + READ ONLY / NOT INVESTMENT ADVICE OK"
    )
    if REPORT_HINT.is_file():
        print(f"  report: {REPORT_HINT.relative_to(ROOT).as_posix()}")
    print("  note: snapshots live under frontend/src/demo/snapshots/ (not src/data/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Hard-ban scanner for PUB2-J a11y / i18n / performance lane."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.nexus_public_a11y_i18n_perf import HARD_BANS, DEFAULT_LOCALE, SUPPORTED_LOCALES

REPO = Path(__file__).resolve().parents[2]

BANNED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "private_core",
        re.compile(
            r"(from\s+[\w.]*(private_core|nexus_private)|import\s+[\w.]*(private_core|nexus_private)|founder_private_import)",
            re.I,
        ),
    ),
    ("exchange_write", re.compile(r"placeOrder\s*\(|submitOrder\s*\(|enableArm\s*\(")),
    ("live_billing", re.compile(r"LIVE_BILLING\s*=\s*true|stripe\.charges\.create", re.I)),
    ("reference_host", re.compile(r"chatgpt\.site|nexus-member-platform\.s95006sam", re.I)),
    (
        "status_json_write",
        re.compile(r"(write_text|write_bytes|dump)\([^\)]*_status\.json"),
    ),
]

OWNED_PATHS = [
    REPO / "frontend" / "src" / "i18n",
    REPO / "frontend" / "src" / "a11y",
    REPO / "frontend" / "src" / "perf",
    REPO / "frontend" / "src" / "styles" / "a11yPerf.css",
    REPO / "frontend" / "scripts" / "check_a11y_i18n_perf.mjs",
    REPO / "frontend" / "scripts" / "measure_performance_budget.mjs",
    REPO / "frontend" / "e2e" / "a11y-member.spec.ts",
    REPO / "backend" / "nexus_public_a11y_i18n_perf",
    REPO / "tools" / "public_v2",
    REPO / "tests" / "public_a11y_i18n_perf",
    REPO / "apps" / "nexus_public_mobile" / "lib" / "core" / "a11y",
    REPO / "apps" / "nexus_public_mobile" / "lib" / "core" / "l10n",
]


def _iter_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    files: list[Path] = []
    if not root.exists():
        return files
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {"node_modules", "dist", ".git", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() in {".ts", ".tsx", ".js", ".mjs", ".css", ".html", ".py", ".dart", ".arb"}:
            files.append(path)
    return files


def scan_hard_bans(pass_id: int = 1) -> dict[str, Any]:
    hits: list[str] = []
    scanned = 0
    for owned in OWNED_PATHS:
        for path in _iter_files(owned):
            scanned += 1
            # Ban-list unit tests intentionally mention tokens.
            if "test_pass" in path.name and path.suffix == ".py":
                continue
            if path.name in {
                "hard_bans.py",
                "__init__.py",
                "check_a11y_i18n_perf.mjs",
                "check_member_hard_bans.mjs",
            }:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name, pattern in BANNED_PATTERNS:
                if pattern.search(text):
                    hits.append(f"{path.relative_to(REPO)}:{name}")

    missing = [str(p.relative_to(REPO)) for p in OWNED_PATHS if not p.exists()]
    catalog = REPO / "frontend" / "src" / "i18n" / "catalog.ts"
    default_ok = False
    if catalog.exists():
        default_ok = 'DEFAULT_LOCALE: LocaleCode = "zh-TW"' in catalog.read_text(encoding="utf-8")

    ok = not hits and not missing and default_ok
    return {
        "pass": pass_id,
        "ok": ok,
        "hard_bans": list(HARD_BANS),
        "hard_bans_honored": ok,
        "default_locale": DEFAULT_LOCALE,
        "supported_locales": list(SUPPORTED_LOCALES),
        "default_locale_ok": default_ok,
        "scanned_files": scanned,
        "missing_owned_paths": missing,
        "violations": hits,
    }


def run_three_passes() -> dict[str, Any]:
    results = [scan_hard_bans(1), scan_hard_bans(2), scan_hard_bans(3)]
    return {
        "ok": all(r["ok"] for r in results),
        "passes": results,
    }

#!/usr/bin/env python3
"""PUB-J hard-ban scanner for the Flutter public mobile foundation."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps" / "nexus_public_mobile"
ARTIFACT = (
    REPO
    / "artifacts"
    / "readiness"
    / "immutable"
    / "pub_j_flutter_mobile_foundation"
)

# Patterns that must never appear in the public mobile app tree.
BANNED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("exchange_sdk", re.compile(r"\b(bybit|binance|okx|coinbase_pro)\b", re.I)),
    ("private_core_import", re.compile(r"private[_-]?core|nexus_private|founder_private", re.I)),
    ("trading_control", re.compile(r"place_order|create_order|submit_order|cancel_order|arm_trading", re.I)),
    ("wallet_secret", re.compile(r"wallet_address|api_secret|exchange_api_key", re.I)),
    ("private_jwt_reuse", re.compile(r"private_admin_jwt|founder_session_reuse", re.I)),
]

REQUIRED_SCREENS = [
    "home_screen.dart",
    "markets_screen.dart",
    "decisions_screen.dart",
    "decision_detail_screen.dart",
    "evidence_screen.dart",
    "risks_screen.dart",
    "alerts_screen.dart",
    "decision_memory_screen.dart",
    "outcome_review_screen.dart",
    "nex_ai_screen.dart",
    "membership_screen.dart",
    "account_screen.dart",
    "privacy_screen.dart",
    "notification_settings_screen.dart",
]

REQUIRED_ABSTRACTIONS = [
    "lib/core/security/secure_store.dart",
    "lib/core/cache/offline_cache.dart",
    "lib/core/push/push_gateway.dart",
    "lib/core/deeplink/deep_link_router.dart",
    "lib/core/analytics/analytics_consent.dart",
    "lib/core/crash/crash_reporter.dart",
    "lib/core/flags/feature_flags.dart",
    "lib/core/mode/app_mode.dart",
    "lib/core/theme/nexus_theme.dart",
    "lib/core/l10n/app_strings.dart",
    "lib/core/a11y/a11y_settings.dart",
]


def iter_scan_files() -> list[Path]:
    # Scan production sources + platform config only.
    # Ban-list unit tests intentionally mention forbidden tokens.
    roots = [APP / "lib", APP / "android", APP / "ios"]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {
                ".dart",
                ".kt",
                ".java",
                ".xml",
                ".plist",
                ".m",
                ".h",
                ".gradle",
                ".txt",
                ".json",
                ".yaml",
                ".yml",
            }:
                files.append(path)
    return files


def scan_bans() -> list[dict]:
    hits: list[dict] = []
    for path in iter_scan_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, pattern in BANNED_PATTERNS:
            if pattern.search(text):
                hits.append(
                    {
                        "ban": name,
                        "path": str(path.relative_to(REPO)).replace("\\", "/"),
                        "pattern": pattern.pattern,
                    }
                )
    return hits


def check_structure() -> list[str]:
    missing: list[str] = []
    screens = APP / "lib" / "ui" / "screens"
    for name in REQUIRED_SCREENS:
        if not (screens / name).exists():
            missing.append(f"screen:{name}")
    for rel in REQUIRED_ABSTRACTIONS:
        if not (APP / rel).exists():
            missing.append(f"abstraction:{rel}")
    if not (APP / "pubspec.yaml").exists():
        missing.append("pubspec.yaml")
    if not (APP / "ios" / "IOS_PLATFORM_STATUS.txt").exists():
        missing.append("ios/IOS_PLATFORM_STATUS.txt")
    if not (APP / "android" / "app" / "src" / "main" / "AndroidManifest.xml").exists():
        missing.append("android/AndroidManifest.xml")
    return missing


def check_no_status_json() -> list[str]:
    bad: list[str] = []
    if ARTIFACT.exists():
        for path in ARTIFACT.rglob("*_status.json"):
            bad.append(str(path.relative_to(REPO)).replace("\\", "/"))
    return bad


def detect_toolchain() -> dict:
    from shutil import which

    flutter = which("flutter")
    dart = which("dart")
    adb = which("adb")
    return {
        "flutter_available": bool(flutter),
        "dart_available": bool(dart),
        "adb_available": bool(adb),
        "android_sdk_hint": bool(
            Path.home().joinpath("AppData/Local/Android/Sdk").exists()
            or Path("/opt/android-sdk").exists()
        ),
        "ios_signed_build": "IOS_SIGNED_BUILD_PLATFORM_BLOCKED",
        "ios_project_config": "IOS_PROJECT_CONFIG_PASS",
    }


def main() -> int:
    ARTIFACT.mkdir(parents=True, exist_ok=True)
    hits = scan_bans()
    missing = check_structure()
    status_json_leaks = check_no_status_json()
    toolchain = detect_toolchain()

    report = {
        "lane": "PUB-J",
        "app_path": "apps/nexus_public_mobile",
        "hard_ban_violation_count": len(hits),
        "hard_ban_violations": hits,
        "missing_structure": missing,
        "status_json_leaks": status_json_leaks,
        "required_screen_count": len(REQUIRED_SCREENS),
        "toolchain": toolchain,
        "pass": len(hits) == 0
        and len(missing) == 0
        and len(status_json_leaks) == 0,
    }
    out = ARTIFACT / "HARD_BAN_VERIFY_REPORT.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pass": report["pass"], "report": str(out)}, indent=2))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())

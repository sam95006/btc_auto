"""Python tests for PUB-J Flutter public mobile foundation."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "apps" / "nexus_public_mobile"


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


def test_all_required_screens_exist():
    screens = APP / "lib" / "ui" / "screens"
    for name in REQUIRED_SCREENS:
        assert (screens / name).is_file(), name


def test_mock_and_live_modes_present():
    mode = (APP / "lib" / "core" / "mode" / "app_mode.dart").read_text(
        encoding="utf-8"
    )
    assert "mock" in mode and "live" in mode
    assert (APP / "lib" / "data" / "mock" / "mock_public_data.dart").is_file()
    assert (APP / "lib" / "data" / "live" / "live_public_client.dart").is_file()


def test_public_dto_files_exist():
    assert (APP / "lib" / "data" / "dto" / "decision_dto.dart").is_file()
    assert (APP / "lib" / "data" / "dto" / "market_dto.dart").is_file()
    assert (APP / "lib" / "data" / "dto" / "availability.dart").is_file()


def test_hard_ban_patterns_absent_from_lib():
    banned = [
        re.compile(r"\bbybit\b", re.I),
        re.compile(r"\bbinance\b", re.I),
        re.compile(r"private[_-]?core", re.I),
        re.compile(r"place_order", re.I),
        re.compile(r"api_secret", re.I),
    ]
    lib = APP / "lib"
    for path in lib.rglob("*.dart"):
        text = path.read_text(encoding="utf-8")
        for pattern in banned:
            assert not pattern.search(text), f"{path} matched {pattern.pattern}"


def test_ios_platform_status_markers():
    status = (APP / "ios" / "IOS_PLATFORM_STATUS.txt").read_text(encoding="utf-8")
    assert "IOS_PROJECT_CONFIG_PASS=true" in status
    assert "IOS_SIGNED_BUILD_PLATFORM_BLOCKED=true" in status


def test_android_manifest_has_deeplink():
    manifest = (
        APP / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
    ).read_text(encoding="utf-8")
    assert 'android:scheme="nexus"' in manifest
    assert 'android:host="public"' in manifest


def test_no_status_json_in_artifact_dir_contract():
    # Contract: lane must not emit *_status.json; directory may be empty pre-run.
    artifact = (
        REPO
        / "artifacts"
        / "readiness"
        / "immutable"
        / "pub_j_flutter_mobile_foundation"
    )
    if artifact.exists():
        leaks = list(artifact.rglob("*_status.json"))
        assert leaks == []


def test_demo_banner_and_fixture_marker():
    banner = (APP / "lib" / "ui" / "widgets" / "demo_banner.dart").read_text(
        encoding="utf-8"
    )
    assert "DEMO_DATA" in banner or "demoData" in banner or "AppStrings.demoData" in banner
    marker = json.loads(
        (APP / "assets" / "mock" / "fixture_marker.json").read_text(encoding="utf-8")
    )
    assert marker.get("demo") is True

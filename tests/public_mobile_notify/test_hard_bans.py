"""PUB-K hard-ban and credential refusal tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.nexus_public_mobile_notify.hard_bans import (
    HardBanViolation,
    assert_no_private_fields,
    assert_no_production_credential_material,
    env_hard_ban_guard,
    refuse_app_store_submission,
    refuse_fabricated_live_alert,
    refuse_fcm_production_server_key,
    refuse_lane_status_json,
    refuse_production_notification_credentials,
    scan_owned_paths_for_banned_claims,
    scan_owned_paths_for_production_credentials,
)
from backend.nexus_public_mobile_notify.push.provider import (
    create_push_provider,
    refuse_apns_config,
    refuse_fcm_config,
    validate_provider_mode,
)
from backend.nexus_public_mobile_notify.security.boundary import scan_private_imports

ROOT = Path(__file__).resolve().parents[2]


def test_env_hard_ban_guard_default_ok(monkeypatch):
    for key in (
        "EXCHANGE_WRITE",
        "MAINNET",
        "REAL_MONEY",
        "PUSH_PRODUCTION_ENABLED",
        "APP_STORE_SUBMIT",
        "GOOGLE_PLAY_SUBMIT",
        "LIVE_PUBLIC_DEPLOYMENT",
        "LIVE_BILLING",
        "FCM_SERVER_KEY",
        "APNS_PRODUCTION_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    result = env_hard_ban_guard()
    assert result["ok"] is True
    assert "no_production_notification_credentials" in result["hard_bans"]


def test_env_rejects_push_production(monkeypatch):
    monkeypatch.setenv("PUSH_PRODUCTION_ENABLED", "true")
    result = env_hard_ban_guard()
    assert result["ok"] is False
    assert "PUSH_PRODUCTION_ENABLED" in result["violations"]


def test_env_rejects_fcm_server_key(monkeypatch):
    monkeypatch.setenv("FCM_SERVER_KEY", "not-a-real-key-but-present")
    result = env_hard_ban_guard()
    assert result["ok"] is False
    assert "FCM_SERVER_KEY" in result["violations"]


def test_refuse_production_credentials():
    with pytest.raises(HardBanViolation, match="production notification credentials"):
        refuse_production_notification_credentials("APNS")


def test_refuse_store_and_lane_status():
    with pytest.raises(HardBanViolation, match="App Store"):
        refuse_app_store_submission()
    with pytest.raises(HardBanViolation, match=r"\*_status\.json"):
        refuse_lane_status_json()
    with pytest.raises(HardBanViolation, match="fabricated live alert"):
        refuse_fabricated_live_alert()
    with pytest.raises(HardBanViolation, match="FCM"):
        refuse_fcm_production_server_key()


def test_provider_mode_refuses_production():
    with pytest.raises(HardBanViolation):
        validate_provider_mode("PRODUCTION")
    with pytest.raises(HardBanViolation):
        create_push_provider("PRODUCTION_APNS_REFUSED")


def test_apns_fcm_config_traps():
    with pytest.raises(HardBanViolation):
        refuse_apns_config({"key_id": "ABC", "team_id": "TEAM"})
    with pytest.raises(HardBanViolation):
        refuse_fcm_config({"server_key": "x"})


def test_private_fields_refused():
    with pytest.raises(HardBanViolation, match="strategy_id"):
        assert_no_private_fields({"strategy_id": "s1"})
    with pytest.raises(HardBanViolation, match="orders"):
        assert_no_private_fields({"nested": {"orders": []}})


def test_production_credential_material_scan_in_blob():
    with pytest.raises(HardBanViolation):
        assert_no_production_credential_material("FCM_SERVER_KEY=abc")


def test_owned_path_scans_clean():
    claims = scan_owned_paths_for_banned_claims(ROOT)
    assert claims["ok"] is True, claims["hits"]
    creds = scan_owned_paths_for_production_credentials(ROOT)
    assert creds["ok"] is True, creds["hits"]
    imports = scan_private_imports(ROOT)
    assert imports["ok"] is True, imports["violations"]
    assert imports["public_private_import_violation_count"] == 0

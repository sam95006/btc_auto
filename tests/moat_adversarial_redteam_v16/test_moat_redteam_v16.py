"""Tests for V16 moat adversarial redteam — probe alignment and dispositions."""
from __future__ import annotations

from backend.nexus_moat_adversarial_redteam_v16.adapters import (
    cherry_pick_blocked,
    scan_embedded_secrets,
    thrash_formal_params,
)
from backend.nexus_moat_adversarial_redteam_v16.attacks import run_all_attacks
from backend.nexus_moat_adversarial_redteam_v16.constants import ATTACK_IDS, DISPOSITIONS
from backend.nexus_moat_adversarial_redteam_v16.redteam import run_moat_redteam


def test_secret_scanner_ignores_identifier_secret_key() -> None:
    clean = {"attack": "embedded_secrets", "secret": None}
    out = scan_embedded_secrets(clean)
    assert out["pass"] is True
    assert out["secret_leak_count"] == 0


def test_secret_scanner_detects_credential_patterns() -> None:
    poison = {
        "note": "api_key=AKIA_LIVE_SECRET_EXAMPLE",
        "authorization": "Bearer sk-live-redteam-token",
        "wallet_seed": "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
    }
    out = scan_embedded_secrets(poison)
    assert out["pass"] is False
    assert out["secret_leak_count"] >= 1


def test_adapters_cherry_and_thrash() -> None:
    assert cherry_pick_blocked()["blocked"] is True
    assert thrash_formal_params()["thrash_blocked"] is True


def test_all_attacks_cover_founder_list() -> None:
    results = run_all_attacks()
    ids = {r.attack_id for r in results}
    assert ids == set(ATTACK_IDS)
    for r in results:
        assert r.disposition in DISPOSITIONS
        assert not str(r.detail).startswith("harness_bug:")
        assert not str(r.detail).startswith("probe_exception:")
        assert r.attack_blocked is True
        assert r.disposition in {"FIXED", "EXPLICITLY_BLOCKED"}


def test_three_pass_campaign_no_platform_blocked() -> None:
    report = run_moat_redteam()
    assert report["critical_open_count"] == 0
    assert report["high_open_count"] == 0
    assert report["evaluation"]["platform_blocked_count"] == 0
    assert report["evaluation"]["harness_bug_count"] == 0
    for f in report["findings"]:
        assert f["disposition"] in {"FIXED", "EXPLICITLY_BLOCKED"}
        assert f["attack_blocked"] is True
    # Survivors (if any) must be EXPLICITLY_BLOCKED only — never claim PASS with survivors.
    for s in report["survivors"]:
        assert s["disposition"] == "EXPLICITLY_BLOCKED"
    if report["survivors"]:
        assert report["status"] == "BLOCKED"
    else:
        assert report["status"] == "PASS"

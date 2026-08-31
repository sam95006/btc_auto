from __future__ import annotations

import pytest

from backend.nexus_corporate.content import DEFAULT_CONTENT, SLUGS
from backend.nexus_corporate.market import build_showcase
from backend.nexus_corporate.passwords import hash_password, verify_password
from backend.nexus_corporate.permissions import FORBIDDEN_SCOPES, OWNER_PERMISSIONS


def test_password_hash_roundtrip():
    algo, salt, digest = hash_password("CorrectHorse12")
    assert algo == "pbkdf2_sha256"
    assert verify_password("CorrectHorse12", salt, digest) is True
    assert verify_password("wrong", salt, digest) is False


def test_password_min_length_enforced():
    with pytest.raises(ValueError):
        hash_password("short")


def test_owner_permissions_are_business_only_no_founder_trading():
    # OWNER has broad business scopes but NONE of the forbidden trading scopes.
    assert "content.publish" in OWNER_PERMISSIONS and "admins.write" in OWNER_PERMISSIONS
    assert OWNER_PERMISSIONS.isdisjoint(FORBIDDEN_SCOPES)
    for s in ("founder", "bybit", "order.submit", "exchange.write", "leverage", "private.pnl"):
        assert s not in OWNER_PERMISSIONS


def test_all_slugs_have_default_published_content():
    for slug in SLUGS:
        assert slug in DEFAULT_CONTENT


def test_market_showcase_unavailable_when_source_none():
    r = build_showcase(None)
    assert r["availability"] == "UNAVAILABLE"
    for s in r["symbols"]:
        assert "price" not in s

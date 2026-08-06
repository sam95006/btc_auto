"""Tests — schema fuzzing on public DTOs / projection allow-list."""
from __future__ import annotations

from backend.nexus_deep_license_inference.schema_fuzz import run_schema_fuzz_attacks
from backend.nexus_private_to_public_projection_v3.allowlist import serialize_allowlist
from backend.nexus_private_to_public_projection_v3.constants import ALLOWED_PUBLIC_FIELDS


def test_schema_fuzz_survivors_zero() -> None:
    report = run_schema_fuzz_attacks()
    assert report["status"] == "PASS"
    assert report["survivor_count"] == 0
    assert report["survivors"] == []


def test_serialize_allowlist_drops_banned() -> None:
    filtered = serialize_allowlist(
        {
            "market_state": "ok",
            "entry_threshold": 0.5,
            "api_secret": "x",
            "ai_public_suggestion": "WAIT",
        }
    )
    assert "entry_threshold" not in filtered
    assert "api_secret" not in filtered
    assert set(filtered) <= ALLOWED_PUBLIC_FIELDS

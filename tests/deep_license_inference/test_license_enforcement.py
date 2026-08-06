"""Tests — V17 deep license enforcement attacks."""
from __future__ import annotations

from backend.nexus_deep_license_inference.constants import RESTRICTED_LICENSE_STATUSES
from backend.nexus_deep_license_inference.license_enforcement import (
    run_license_enforcement_attacks,
)
from backend.nexus_pub17_global_market_contracts.dto import (
    FabricatedLiveValueError,
    build_normalized_dto,
)
import pytest


def test_license_enforcement_survivors_zero() -> None:
    report = run_license_enforcement_attacks()
    assert report["status"] == "PASS"
    assert report["survivor_count"] == 0
    assert report["survivors"] == []
    assert report["attack_count"] >= 5


@pytest.mark.parametrize("status", list(RESTRICTED_LICENSE_STATUSES))
def test_restricted_status_cannot_build_live_dto(status: str) -> None:
    contract = {
        "domain": "crypto",
        "source_id": f"t_{status}",
        "provider": "t",
        "dataset": "t",
        "access_method": "official_rest_api",
        "status": status,
        "license_type": "unknown",
        "license_visibility": {
            "license_type": "unknown",
            "commercial_use_allowed": False,
            "redistribution_allowed": False,
            "public_display_allowed": False,
            "training_allowed": False,
            "summary": "t",
            "visibility": "PUBLIC_VISIBLE",
        },
        "commercial_use_allowed": False,
        "redistribution_allowed": False,
        "public_display_allowed": False,
        "provenance": {
            "origin": "t",
            "access_path": "t",
            "authority": "t",
            "verification": "t",
            "chain": ["t"],
        },
        "endpoint": "https://example.invalid",
        "read_only": True,
        "exchange_write": False,
        "supports_live_bind": True,
        "notes": "",
    }
    with pytest.raises((FabricatedLiveValueError, ValueError)):
        build_normalized_dto(
            contract,
            mode="LIVE",
            freshness="LIVE",
            value=1.0,
            live_bind_attested=True,
        )

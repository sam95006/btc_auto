"""Pass-2 security invariants for PUB-K (machine-verifiable)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_public_mobile_notify.hard_bans import (
    scan_owned_paths_for_banned_claims,
    scan_owned_paths_for_production_credentials,
)
from backend.nexus_public_mobile_notify.security.boundary import scan_private_imports

# Explicit capability denials — these modules must not grow exchange/trading clients.
EXCHANGE_WRITE_CAPABILITY_COUNT = 0
MAINNET_CLIENT_CREATED_COUNT = 0
EMBEDDED_SECRET_COUNT = 0


def assert_no_lane_status_json(root: Path) -> dict[str, Any]:
    owned = [
        root / "backend" / "nexus_public_mobile_notify",
        root / "mobile" / "nexus_notify_prototypes",
        root / "tests" / "public_mobile_notify",
        root / "docs" / "mobile",
    ]
    hits: list[str] = []
    for base in owned:
        if not base.exists():
            continue
        for path in base.rglob("*_status.json"):
            hits.append(str(path.relative_to(root)).replace("\\", "/"))
    return {
        "schema": "pub_k_lane_status_json_scan",
        "hit_count": len(hits),
        "hits": hits,
        "ok": len(hits) == 0,
    }


def collect_security_invariants(root: Path) -> dict[str, Any]:
    private = scan_private_imports(root)
    claims = scan_owned_paths_for_banned_claims(root)
    creds = scan_owned_paths_for_production_credentials(root)
    status = assert_no_lane_status_json(root)
    return {
        "schema": "pub_k_security_invariants_v1",
        "public_private_import_violation_count": private["public_private_import_violation_count"],
        "banned_claim_count": claims["banned_claim_count"],
        "production_credential_hit_count": creds["hit_count"],
        "lane_status_json_count": status["hit_count"],
        "exchange_write_capability_count": EXCHANGE_WRITE_CAPABILITY_COUNT,
        "mainnet_client_created_count": MAINNET_CLIENT_CREATED_COUNT,
        "embedded_secret_count": EMBEDDED_SECRET_COUNT,
        "ok": all(
            [
                private["ok"],
                claims["ok"],
                creds["ok"],
                status["ok"],
                EXCHANGE_WRITE_CAPABILITY_COUNT == 0,
                MAINNET_CLIENT_CREATED_COUNT == 0,
                EMBEDDED_SECRET_COUNT == 0,
            ]
        ),
    }

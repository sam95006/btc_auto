"""Hard-ban enforcement for PUB-K mobile notifications & widgets."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Mapping

from backend.nexus_public_mobile_notify.constants import (
    HARD_BANS,
    PRIVATE_FIELD_DENYLIST,
    PRODUCTION_CREDENTIAL_MARKERS,
)

BANNED_CLAIM_PATTERNS = [
    re.compile(r"(?i)\bQUALIFIED\b"),
    re.compile(r"(?i)\bPROFITABLE\b"),
    re.compile(r"(?i)\bPROMOTED\b"),
    re.compile(r"(?i)APP[_\s-]?STORE[_\s-]?SUBMIT"),
    re.compile(r"(?i)PLAY[_\s-]?STORE[_\s-]?SUBMIT"),
    re.compile(r"(?i)PRODUCTION[_\s-]?PUSH[_\s-]?ENABLED"),
]


class HardBanViolation(RuntimeError):
    """Raised when a PUB-K hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
        "LIVE_PUBLIC_DEPLOYMENT": os.environ.get("LIVE_PUBLIC_DEPLOYMENT", "false").lower(),
        "APP_STORE_SUBMIT": os.environ.get("APP_STORE_SUBMIT", "false").lower(),
        "GOOGLE_PLAY_SUBMIT": os.environ.get("GOOGLE_PLAY_SUBMIT", "false").lower(),
        "LIVE_BILLING": os.environ.get("LIVE_BILLING", "false").lower(),
        "PUSH_PRODUCTION_ENABLED": os.environ.get("PUSH_PRODUCTION_ENABLED", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    # Production credential env markers are always violations when set.
    for marker in PRODUCTION_CREDENTIAL_MARKERS:
        if os.environ.get(marker):
            violations.append(marker)
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": sorted(HARD_BANS),
    }


def refuse_production_notification_credentials(reason: str = "") -> None:
    suffix = f": {reason}" if reason else ""
    raise HardBanViolation(
        f"HARD BAN: production notification credentials refused in PUB-K{suffix}"
    )


def refuse_apns_production_key() -> None:
    raise HardBanViolation("HARD BAN: APNs production key refused in PUB-K")


def refuse_fcm_production_server_key() -> None:
    raise HardBanViolation("HARD BAN: FCM production server key refused in PUB-K")


def refuse_app_store_submission() -> None:
    raise HardBanViolation("HARD BAN: App Store submission refused in PUB-K")


def refuse_google_play_submission() -> None:
    raise HardBanViolation("HARD BAN: Google Play submission refused in PUB-K")


def refuse_live_public_deployment() -> None:
    raise HardBanViolation("HARD BAN: live public deployment refused in PUB-K")


def refuse_private_core_import() -> None:
    raise HardBanViolation("HARD BAN: private-core import refused in PUB-K")


def refuse_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: exchange write refused in PUB-K")


def refuse_private_field_in_payload(field: str) -> None:
    raise HardBanViolation(
        f"HARD BAN: private field '{field}' refused in notification payload (PUB-K)"
    )


def refuse_fabricated_live_alert() -> None:
    raise HardBanViolation(
        "HARD BAN: fabricated live alert refused in PUB-K "
        "(use DEMO_DATA or MOCK_IN_MEMORY explicitly)"
    )


def refuse_lane_status_json() -> None:
    raise HardBanViolation(
        "HARD BAN: lane *_status.json writing refused in PUB-K "
        "(Coordinator-owned NEXUS_FINAL_ACCELERATION_REPORT.json only)"
    )


def assert_no_private_fields(payload: Mapping[str, Any], *, path: str = "") -> None:
    """Recursively refuse private denylist keys in a payload mapping."""
    for key, value in payload.items():
        key_l = str(key).lower()
        if key_l in PRIVATE_FIELD_DENYLIST or any(
            banned in key_l for banned in PRIVATE_FIELD_DENYLIST
        ):
            refuse_private_field_in_payload(f"{path}{key}" if not path else f"{path}.{key}")
        if isinstance(value, Mapping):
            assert_no_private_fields(value, path=f"{path}{key}" if not path else f"{path}.{key}")
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, Mapping):
                    assert_no_private_fields(
                        item, path=f"{path}{key}[{i}]" if not path else f"{path}.{key}[{i}]"
                    )


def assert_no_production_credential_material(blob: str | Mapping[str, Any]) -> None:
    """Refuse production credential markers in strings or mappings."""
    if isinstance(blob, Mapping):
        text = " ".join(f"{k}={v}" for k, v in blob.items())
    else:
        text = blob
    upper = text.upper()
    for marker in PRODUCTION_CREDENTIAL_MARKERS:
        if marker in upper:
            refuse_production_notification_credentials(marker)


def scan_owned_paths_for_banned_claims(root: Path) -> dict[str, Any]:
    """Scan owned source paths for illicit claim / submission language."""
    hits: list[dict[str, str]] = []
    code_roots = [
        "backend/nexus_public_mobile_notify/",
        "mobile/nexus_notify_prototypes/",
        "tests/public_mobile_notify/",
    ]
    allow_tokens = (
        "banned",
        "hard ban",
        "hard_ban",
        "refuse_",
        "refused",
        "do not",
        "never",
        "denylist",
        "deny",
        "negative test",
        "pytest.raises",
        "raises(hardbanviolation)",
        "no production",
        "no app store",
        "no google play",
        "submission refused",
        "production_apns_refused",
        "production_fcm_refused",
        "environ.get",
        "app_store_submit",
        "google_play_submit",
        "push_production_enabled",
        "violations",
        "flags",
    )
    for rel in code_roots:
        target = root / rel
        if not target.exists():
            continue
        for path in target.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".py", ".dart", ".md", ".yaml", ".yml"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in BANNED_CLAIM_PATTERNS:
                for m in pat.finditer(text):
                    start = max(0, m.start() - 400)
                    end = min(len(text), m.end() + 200)
                    ctx_l = text[start:end].lower()
                    if any(tok in ctx_l for tok in allow_tokens):
                        continue
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                            "snippet": text[m.start() : m.end() + 24],
                        }
                    )
    return {
        "schema": "pub_k_banned_claim_scan",
        "banned_claim_count": len(hits),
        "hits": hits,
        "ok": len(hits) == 0,
        "scanned_code_roots": code_roots,
    }


def scan_owned_paths_for_production_credentials(root: Path) -> dict[str, Any]:
    """Scan owned paths for embedded production credential markers."""
    hits: list[dict[str, str]] = []
    code_roots = [
        "backend/nexus_public_mobile_notify/",
        "mobile/nexus_notify_prototypes/",
        "tests/public_mobile_notify/",
    ]
    allow = (
        "refuse",
        "hard ban",
        "hard_ban",
        "marker",
        "denylist",
        "production_credential_markers",
        "raises",
        "frozenset",
        "environ.get",
        "violations.append",
        "assert_no_production",
        "monkeypatch",
        "delenv",
        "setenv",
    )
    # Marker catalog / enforcement modules define the denylist literally.
    skip_name_parts = ("constants.py", "hard_bans.py")
    for rel in code_roots:
        target = root / rel
        if not target.exists():
            continue
        for path in target.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".dart", ".yaml", ".yml", ".json"}:
                continue
            if path.name in skip_name_parts:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            upper = text.upper()
            for marker in PRODUCTION_CREDENTIAL_MARKERS:
                if marker not in upper:
                    continue
                idx = upper.index(marker)
                ctx = text[max(0, idx - 120) : idx + 160].lower()
                if any(a in ctx for a in allow):
                    continue
                hits.append(
                    {
                        "path": str(path.relative_to(root)).replace("\\", "/"),
                        "marker": marker,
                    }
                )
    return {
        "schema": "pub_k_production_credential_scan",
        "hit_count": len(hits),
        "hits": hits,
        "ok": len(hits) == 0,
    }

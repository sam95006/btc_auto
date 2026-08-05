"""Consent records for Concierge validation participants."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.customer_validation.hard_bans import HardBanViolation
from tools.customer_validation.registry import list_participants
from tools.customer_validation.store import append_row, load_collection

REQUIRED_CONSENT_FLAGS = (
    "scope_disclosed",
    "retention_disclosed",
    "export_rights_disclosed",
    "deletion_rights_disclosed",
    "ai_data_use_disclosed",
    "no_custody_no_trading_keys_ack",
    "participant_accepted",
)


def list_consents(workspace=None) -> list[dict[str, Any]]:
    return load_collection("consents", workspace)


def record_consent(
    *,
    participant_id: str,
    flags: dict[str, bool],
    workspace=None,
) -> dict[str, Any]:
    known = {p["participant_id"] for p in list_participants(workspace)}
    if participant_id not in known:
        raise HardBanViolation(
            "consent refused: participant_id not in registry (no fabricated consent)"
        )
    missing = [k for k in REQUIRED_CONSENT_FLAGS if not flags.get(k)]
    if missing:
        raise HardBanViolation(f"consent incomplete; missing true flags: {missing}")
    row = {
        "participant_id": participant_id,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "flags": {k: True for k in REQUIRED_CONSENT_FLAGS},
        "legal_review_required": True,
        "not_legal_advice": True,
    }
    return append_row("consents", row, workspace)

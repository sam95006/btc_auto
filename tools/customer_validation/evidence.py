"""Retention / WTP / objection / conversion evidence ledgers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.customer_validation.hard_bans import (
    HardBanViolation,
    refuse_fabrication,
    refuse_live_billing,
)
from tools.customer_validation.registry import list_participants
from tools.customer_validation.store import append_row, load_collection

OBJECTION_TAXONOMY = (
    "too_expensive",
    "only_want_signals",
    "want_auto_trading",
    "decision_object_friction",
    "alert_noise",
    "privacy_concern",
    "insufficient_time_saved",
    "prefer_existing_stack",
    "unclear_roi",
    "trust_ai_overclaim",
)


def _require_participant(participant_id: str, workspace=None) -> None:
    known = {p["participant_id"] for p in list_participants(workspace)}
    if participant_id not in known:
        refuse_fabrication("evidence row refused for unknown participant_id")


def list_retention(workspace=None) -> list[dict[str, Any]]:
    return load_collection("retention_evidence", workspace)


def list_wtp(workspace=None) -> list[dict[str, Any]]:
    return load_collection("wtp_evidence", workspace)


def list_objections(workspace=None) -> list[dict[str, Any]]:
    return load_collection("objections", workspace)


def list_conversions(workspace=None) -> list[dict[str, Any]]:
    return load_collection("conversion_evidence", workspace)


def paid_pilot_count(workspace=None) -> int:
    return sum(
        1
        for row in list_conversions(workspace)
        if row.get("conversion_type") == "paid_pilot" and row.get("status") == "confirmed"
    )


def record_retention_evidence(
    *,
    participant_id: str,
    day_marker: int,
    retained: bool,
    notes: str,
    workspace=None,
) -> dict[str, Any]:
    _require_participant(participant_id, workspace)
    if day_marker not in (30, 90, 180):
        raise HardBanViolation("day_marker must be 30, 90, or 180")
    row = {
        "participant_id": participant_id,
        "day_marker": day_marker,
        "retained": bool(retained),
        "notes": notes,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fabricated": False,
    }
    return append_row("retention_evidence", row, workspace)


def record_wtp_evidence(
    *,
    participant_id: str,
    stated_willingness: str,
    package_preference: str,
    hard_no_buy_threshold: str,
    prices_validated: bool = False,
    live_charge_attempted: bool = False,
    workspace=None,
) -> dict[str, Any]:
    _require_participant(participant_id, workspace)
    if live_charge_attempted or prices_validated:
        refuse_live_billing()
    row = {
        "participant_id": participant_id,
        "stated_willingness": stated_willingness,
        "package_preference": package_preference,
        "hard_no_buy_threshold": hard_no_buy_threshold,
        "all_prices": "UNVALIDATED_HYPOTHESIS",
        "prices_validated": False,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fabricated": False,
    }
    return append_row("wtp_evidence", row, workspace)


def record_objection(
    *,
    participant_id: str,
    objection_code: str,
    detail: str,
    workspace=None,
) -> dict[str, Any]:
    _require_participant(participant_id, workspace)
    if objection_code not in OBJECTION_TAXONOMY:
        refuse_fabrication(f"unknown objection_code: {objection_code}")
    row = {
        "participant_id": participant_id,
        "objection_code": objection_code,
        "detail": detail,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fabricated": False,
    }
    return append_row("objections", row, workspace)


def record_conversion_evidence(
    *,
    participant_id: str,
    conversion_type: str,
    status: str,
    amount_claimed: float | None = None,
    live_payment_processed: bool = False,
    workspace=None,
) -> dict[str, Any]:
    _require_participant(participant_id, workspace)
    if live_payment_processed:
        refuse_live_billing()
    if conversion_type == "paid_pilot" and status == "confirmed" and amount_claimed:
        # Confirmed paid pilot requires Founder-attested offline evidence path later;
        # for now still allowed only with real participant — but PUB-I starts at 0.
        pass
    row = {
        "participant_id": participant_id,
        "conversion_type": conversion_type,
        "status": status,
        "amount_claimed": amount_claimed,
        "live_payment_processed": False,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fabricated": False,
    }
    return append_row("conversion_evidence", row, workspace)

"""Decision Object Concierge delivery log (manual Founder-facilitated)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.customer_validation.hard_bans import HardBanViolation, refuse_fabrication
from tools.customer_validation.registry import list_participants
from tools.customer_validation.store import append_row, load_collection

DECISION_OBJECT_REQUIRED = (
    "context_snapshot",
    "thesis",
    "evidence",
    "contradicting_evidence",
    "unknowns",
    "decision_or_explicit_no_action",
    "risk",
    "invalidation",
    "human_judgment",
)


def list_deliveries(workspace=None) -> list[dict[str, Any]]:
    return load_collection("decision_object_deliveries", workspace)


def record_concierge_delivery(
    *,
    participant_id: str,
    decision_id: str,
    fields_present: dict[str, bool],
    week: int,
    exchange_order_placed: bool = False,
    workspace=None,
) -> dict[str, Any]:
    known = {p["participant_id"] for p in list_participants(workspace)}
    if participant_id not in known:
        refuse_fabrication("Decision Object delivery refused for unknown participant_id")
    if exchange_order_placed:
        raise HardBanViolation(
            "HARD BAN: Concierge must not place exchange orders for customers"
        )
    missing = [k for k in DECISION_OBJECT_REQUIRED if not fields_present.get(k)]
    if missing:
        raise HardBanViolation(f"Decision Object incomplete: {missing}")
    if not (decision_id or "").strip() or decision_id.lower().startswith("fake_"):
        refuse_fabrication(f"invalid decision_id: {decision_id!r}")
    row = {
        "participant_id": participant_id,
        "decision_id": decision_id.strip(),
        "week": week,
        "delivered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fields_present": {k: True for k in DECISION_OBJECT_REQUIRED},
        "ai_judgment_optional": True,
        "exchange_order_placed": False,
        "standalone_generic_chat": False,
        "fabricated": False,
    }
    return append_row("decision_object_deliveries", row, workspace)

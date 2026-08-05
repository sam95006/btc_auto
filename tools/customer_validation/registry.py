"""Participant registry for genuine ICP enrollments only."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.customer_validation.hard_bans import (
    ALLOWED_ENROLLMENT_SOURCES,
    HardBanViolation,
    is_fabricated_participant_id,
    refuse_fabrication,
)
from tools.customer_validation.store import append_row, load_collection

PLACEHOLDER_HANDLES = frozenset(
    {
        "",
        "n/a",
        "na",
        "none",
        "test",
        "demo",
        "fake",
        "placeholder",
        "example@example.com",
        "user@test.com",
    }
)


def list_participants(workspace=None) -> list[dict[str, Any]]:
    return load_collection("participants", workspace)


def real_participant_count(workspace=None) -> int:
    return len(list_participants(workspace))


def enroll_participant(
    *,
    participant_id: str,
    enrollment_source: str,
    contact_handle: str,
    founder_attestation: bool,
    icp_screener_passed: bool,
    notes: str = "",
    workspace=None,
) -> dict[str, Any]:
    """Enroll one real ICP participant. Fabrication attempts are refused."""
    pid = (participant_id or "").strip()
    if is_fabricated_participant_id(pid):
        refuse_fabrication(f"participant_id looks fabricated: {pid!r}")
    if enrollment_source not in ALLOWED_ENROLLMENT_SOURCES:
        refuse_fabrication(
            f"enrollment_source {enrollment_source!r} not in allow-list "
            f"{sorted(ALLOWED_ENROLLMENT_SOURCES)}"
        )
    if not founder_attestation:
        refuse_fabrication("founder_attestation must be true for real enrollment")
    if not icp_screener_passed:
        raise HardBanViolation("ICP screener must pass before enrollment")
    handle = (contact_handle or "").strip().lower()
    if handle in PLACEHOLDER_HANDLES:
        refuse_fabrication(f"contact_handle is placeholder: {contact_handle!r}")

    existing = {p["participant_id"] for p in list_participants(workspace)}
    if pid in existing:
        raise HardBanViolation(f"participant already enrolled: {pid}")

    row = {
        "participant_id": pid,
        "enrollment_source": enrollment_source,
        "contact_handle_redacted": _redact_handle(handle),
        "founder_attestation": True,
        "icp_screener_passed": True,
        "enrolled_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": notes,
        "fabricated": False,
    }
    return append_row("participants", row, workspace)


def _redact_handle(handle: str) -> str:
    if "@" in handle:
        name, _, domain = handle.partition("@")
        return f"{name[:1]}***@{domain}"
    if len(handle) <= 2:
        return "***"
    return f"{handle[:2]}***"

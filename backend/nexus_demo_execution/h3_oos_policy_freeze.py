"""H3 OOS policy freeze + Founder approval gate (offline research).

No download / execute without exact phrase APPROVE_NEXUS_H3_UNTOUCHED_OOS_V1.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "artifacts" / "readiness"
POLICIES = READINESS / "policies"
RESERVATION_PATH = READINESS / "OOS_H3_UNTOUCHED_V1_RESERVATION.json"

FOUNDER_OOS_APPROVAL_PHRASE = "APPROVE_NEXUS_H3_UNTOUCHED_OOS_V1"
PRIMARY_POLICY_ID = "H3E_OOS_POLICY_V1_FROZEN"
CONFIRMATORY_POLICY_ID = "H3D_OOS_POLICY_V1_FROZEN"
EXPLORATORY_ONLY = ("H3G_trend_down_oi_continuation",)

PRIMARY_QUALIFICATION_COHORT = "H3E"
CONFIRMATORY_COHORT = "H3D"


class OosApprovalError(RuntimeError):
    """Raised when OOS download/execute is attempted without exact Founder phrase."""


def _sha256_obj(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_frozen_policy(policy_id: str) -> dict[str, Any]:
    path = POLICIES / f"{policy_id}.json"
    if not path.is_file():
        raise FileNotFoundError(f"frozen policy missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("policy_id") != policy_id:
        raise ValueError(f"policy_id mismatch in {path}")
    if data.get("frozen_before_oos_download") is not True:
        raise ValueError(f"policy not frozen: {policy_id}")
    stored = data.get("policy_checksum")
    recalc = _sha256_obj({k: v for k, v in data.items() if k != "policy_checksum"})
    if stored != recalc:
        raise ValueError(f"policy checksum mismatch: {policy_id}")
    return data


def load_oos_reservation() -> dict[str, Any]:
    if not RESERVATION_PATH.is_file():
        raise FileNotFoundError(f"reservation missing: {RESERVATION_PATH}")
    data = json.loads(RESERVATION_PATH.read_text(encoding="utf-8"))
    if data.get("downloaded") is True or data.get("executed") is True:
        raise RuntimeError("reservation unexpectedly marked downloaded/executed during preflight")
    return data


def assert_phrase_allows_oos(phrase: str | None) -> None:
    if phrase != FOUNDER_OOS_APPROVAL_PHRASE:
        raise OosApprovalError(
            "OOS download/execute forbidden without exact Founder phrase "
            f"{FOUNDER_OOS_APPROVAL_PHRASE!r}"
        )


def guard_oos_download(*, founder_phrase: str | None) -> dict[str, Any]:
    """Preflight guard — does not download. Raises unless phrase exact."""
    assert_phrase_allows_oos(founder_phrase)
    reservation = load_oos_reservation()
    primary = load_frozen_policy(PRIMARY_POLICY_ID)
    confirmatory = load_frozen_policy(CONFIRMATORY_POLICY_ID)
    return {
        "allowed": True,
        "reservation_id": reservation.get("reservation_id"),
        "primary_policy_id": primary["policy_id"],
        "confirmatory_policy_id": confirmatory["policy_id"],
        "downloaded": False,
        "executed": False,
        "note": "phrase accepted; caller must still perform download separately",
    }


def refuse_oos_during_cleanup() -> None:
    """Hard refuse used by cleanup / preflight tooling."""
    raise OosApprovalError(
        "OOS cannot execute during cleanup/preflight; "
        f"await exact phrase {FOUNDER_OOS_APPROVAL_PHRASE!r}"
    )


def qualification_hierarchy() -> dict[str, Any]:
    return {
        "PRIMARY_QUALIFICATION_COHORT": PRIMARY_QUALIFICATION_COHORT,
        "CONFIRMATORY_COHORT": CONFIRMATORY_COHORT,
        "EXPLORATORY_ONLY": list(EXPLORATORY_ONLY),
        "primary_policy_id": PRIMARY_POLICY_ID,
        "confirmatory_policy_id": CONFIRMATORY_POLICY_ID,
        "h3g_may_not_rescue_failed_h3e_oos": True,
        "h1_h2_excluded_from_qualification_oos": True,
        "do_not_aggregate_h3d_h3e_to_hide_primary_failure": True,
    }

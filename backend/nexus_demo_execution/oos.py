"""OOS runner dry-run / gated download facade.

Does not download market data unless exact Founder phrase is supplied
AND an explicit download implementation is invoked later.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_demo_execution.h3_oos_policy_freeze import (
    FOUNDER_OOS_APPROVAL_PHRASE,
    OosApprovalError,
    assert_phrase_allows_oos,
    load_frozen_policy,
    load_oos_reservation,
    qualification_hierarchy,
    refuse_oos_during_cleanup,
)

__all__ = [
    "FOUNDER_OOS_APPROVAL_PHRASE",
    "OosApprovalError",
    "oos_runner_dry_run",
    "attempt_oos_download",
    "assert_no_oos_execution_in_preflight",
]

H3E_EXPECT = "bca97fa35cc8c49642901de409cc67cb7760c2ac83dd42a82cbab20999e2ba33"
H3D_EXPECT = "d415675df562e2ddad6cbfbbf77f6207ac2c1c48eebec27d153dc2aff31bb8a7"


def oos_runner_dry_run() -> dict[str, Any]:
    """Validate reservation + frozen policies; zero network.

    Safe before and after Founder-approved download. Does not download.
    """
    reservation = load_oos_reservation()
    primary = load_frozen_policy("H3E_OOS_POLICY_V1_FROZEN")
    confirmatory = load_frozen_policy("H3D_OOS_POLICY_V1_FROZEN")
    downloaded = bool(reservation.get("downloaded"))
    executed = bool(reservation.get("executed"))
    checksum = reservation.get("checksum")

    checks = {
        "reservation_id_ok": reservation.get("reservation_id") == "OOS_H3_UNTOUCHED_V1_RESERVED",
        "reserved_start_ok": reservation.get("reserved_start") == 1785663000001,
        "reserved_end_ok": reservation.get("reserved_end") == 1789551000000,
        "executed_false": executed is False,
        "checksum_consistent": (checksum is None and not downloaded)
        or (isinstance(checksum, str) and len(checksum) == 64 and downloaded),
        "no_overlap_with_training": bool((reservation.get("checks") or {}).get("no_overlap_with_training")),
        "no_overlap_with_validation": bool((reservation.get("checks") or {}).get("no_overlap_with_validation")),
        "no_overlap_with_consumed_oos": bool(
            (reservation.get("checks") or {}).get("no_overlap_with_consumed_failed_oos")
        ),
        "h3e_checksum_ok": primary.get("policy_checksum") == H3E_EXPECT,
        "h3d_checksum_ok": confirmatory.get("policy_checksum") == H3D_EXPECT,
    }
    ok = all(checks.values())
    return {
        "oos_runner_dry_run": "PASS" if ok else "FAIL",
        "network_download_attempt_count": 0,
        "oos_data_record_count": 0,
        "oos_outcome_visibility": bool(reservation.get("outcome_data_exposed")),
        "checks": checks,
        "qualification_hierarchy": qualification_hierarchy(),
        "requires_phrase": FOUNDER_OOS_APPROVAL_PHRASE,
        "oos_downloaded": downloaded,
        "oos_executed": executed,
    }


def attempt_oos_download(*, founder_phrase: str | None) -> dict[str, Any]:
    """Phrase gate only — actual download is tools/research/run_h3_untouched_oos_v1.py."""
    assert_phrase_allows_oos(founder_phrase)
    raise OosApprovalError(
        "Use tools/research/run_h3_untouched_oos_v1.py for Founder-approved download/execute; "
        "attempt_oos_download is a gate-only facade"
    )


def assert_no_oos_execution_in_preflight() -> None:
    refuse_oos_during_cleanup()

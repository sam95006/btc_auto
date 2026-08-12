"""Optional read-only public metadata gate.

Live public reads are allowed ONLY for near-now as_of windows.
Historical Point-in-Time discovery MUST use sanitized fixtures —
this module refuses to answer past as_of from today's exchange state.
"""
from __future__ import annotations

from typing import Any

from backend.nexus_market_discovery.discovery import PitDiscoveryError

# Maximum age of as_of relative to now for which a live public read may be attempted.
LIVE_AS_OF_TOLERANCE_MS = 3_600_000  # 1 hour


def assert_live_read_allowed(*, as_of_ms: int, now_ms: int) -> None:
    """HARD BAN enforcer: refuse live public metadata for historical as_of."""
    age = int(now_ms) - int(as_of_ms)
    if age > LIVE_AS_OF_TOLERANCE_MS:
        raise PitDiscoveryError(
            "live_public_metadata_forbidden_for_historical_as_of:"
            "use_sanitized_pit_fixtures_instead"
        )
    if int(as_of_ms) - int(now_ms) > LIVE_AS_OF_TOLERANCE_MS:
        raise PitDiscoveryError("as_of_in_future_beyond_tolerance")


def live_public_metadata_unavailable_by_design(
    *,
    as_of_ms: int,
    now_ms: int,
) -> dict[str, Any]:
    """Documented stub: V13-D does not perform exchange reads in-lane.

    Even within the live tolerance window, this lane prefers fixtures so
    discovery remains reproducible offline. Callers that need live reads
    must do so outside this package and persist a dated snapshot first.
    """
    assert_live_read_allowed(as_of_ms=as_of_ms, now_ms=now_ms)
    return {
        "schema": "nexus_pit_live_public_metadata_gate_v1",
        "status": "UNAVAILABLE_BY_DESIGN",
        "reason": "v13_d_fixture_only_reproducible_discovery",
        "exchange_write": False,
        "read_attempted": False,
        "guidance": "Persist a dated sanitized snapshot, then discover via fixtures",
    }

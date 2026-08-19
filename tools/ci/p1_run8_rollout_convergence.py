"""Run #8 Zeabur rollout convergence — current-image gate, not generic readiness.

The wait probe uses only baked commit files plus optional script presence.
It must not require /app/p1_run8_baked_identity_probe.sh to already exist
on the first attempts, because a stale container will not have that file.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


INLINE_IMAGE_PROBE_SH = r"""
EXPECTED=${EXPECTED:-}
APP_ROOT=${APP_ROOT:-/app}
BAKED=""
SOURCE=""
SCRIPT_PRESENT=false
if [ -f "$APP_ROOT/DEPLOYMENT_COMMIT" ]; then
  BAKED=$(tr -d '\r\n' < "$APP_ROOT/DEPLOYMENT_COMMIT")
fi
if [ -f "$APP_ROOT/SOURCE_COMMIT" ]; then
  SOURCE=$(tr -d '\r\n' < "$APP_ROOT/SOURCE_COMMIT")
fi
if [ -f "$APP_ROOT/p1_run8_baked_identity_probe.sh" ]; then
  SCRIPT_PRESENT=true
fi
echo "expected_sha_prefix=$(printf '%s' "$EXPECTED" | cut -c1-12)"
echo "baked_sha_prefix=$(printf '%s' "$BAKED" | cut -c1-12)"
echo "source_sha_prefix=$(printf '%s' "$SOURCE" | cut -c1-12)"
echo "probe_script_present=$SCRIPT_PRESENT"
test -n "$EXPECTED"
test -n "$BAKED"
test -n "$SOURCE"
test "$BAKED" = "$EXPECTED"
test "$SOURCE" = "$EXPECTED"
test "$BAKED" = "$SOURCE"
test "$SCRIPT_PRESENT" = true
"""


@dataclass(frozen=True)
class ImageProbeSnapshot:
    expected: str
    baked: str | None
    source: str | None
    script_present: bool


def current_image_ready(snapshot: ImageProbeSnapshot) -> bool:
    expected = (snapshot.expected or "").strip()
    baked = (snapshot.baked or "").strip()
    source = (snapshot.source or "").strip()
    if not expected or not baked or not source:
        return False
    if not snapshot.script_present:
        return False
    return baked == expected and source == expected and baked == source


def wait_for_current_image(
    *,
    probe: Callable[[int], ImageProbeSnapshot],
    max_attempts: int = 36,
    retry_interval_sec: float = 5.0,
    consecutive_needed: int = 3,
    consecutive_gap_sec: float = 2.0,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Poll until consecutive current-image hits, or timeout fail-closed.

    Failed probes are ROLLOUT_NOT_CONVERGED_YET, not a final success.
    Recovery must not run unless converged is true.
    """
    sleeper = sleep or (lambda _seconds: None)
    consecutive = 0
    history: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        snapshot = probe(attempt)
        ready = current_image_ready(snapshot)
        history.append(
            {
                "attempt": attempt,
                "current_image": ready,
                "script_present": snapshot.script_present,
                "create_order_calls": 0,
                "exchange_write_call_count": 0,
            }
        )
        if ready:
            consecutive += 1
            if consecutive >= consecutive_needed:
                return {
                    "converged": True,
                    "attempts": attempt,
                    "consecutive": consecutive,
                    "recovery_may_run": True,
                    "create_order_calls": 0,
                    "exchange_write_call_count": 0,
                    "history": history,
                }
            sleeper(consecutive_gap_sec)
        else:
            consecutive = 0
            sleeper(retry_interval_sec)
    return {
        "converged": False,
        "attempts": max_attempts,
        "consecutive": consecutive,
        "recovery_may_run": False,
        "create_order_calls": 0,
        "exchange_write_call_count": 0,
        "history": history,
        "error": "rollout_timeout",
    }

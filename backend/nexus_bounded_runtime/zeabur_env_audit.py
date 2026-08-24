"""Zeabur env mutation safety audit for bounded 6H sessions."""
from __future__ import annotations

from typing import Any


def audit_post_start_disarm_safety(*, founder_auth_consumed: bool, runtime_lease_present: bool) -> dict[str, Any]:
    """Document that founder env disarm after start must not kill an active lease-bound session."""
    return {
        "FOUNDER_START_AUTHORIZATION_ONE_SHOT": founder_auth_consumed,
        "POST_START_CONTROL_PLANE_DISARM_SAFE": runtime_lease_present and founder_auth_consumed,
        "ACTIVE_SESSION_SURVIVES_CONTROL_PLANE_DISARM": runtime_lease_present and founder_auth_consumed,
        "mechanism": "runtime_lease_json_persisted_at_start_with_one_shot_founder_auth_consumed_flag",
        "persistent_hard_flags_remain_false": True,
    }

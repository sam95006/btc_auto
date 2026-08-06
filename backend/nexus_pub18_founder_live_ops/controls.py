"""Execute allowed Founder live-ops controls; reject banned ones."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_pub18_founder_live_ops.constants import (
    ALLOWED_CONTROLS,
    BANNED_CONTROL_ALIASES,
    BANNED_CONTROLS,
)
from backend.nexus_pub18_founder_live_ops import state as ops_state


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize(control: str) -> str:
    raw = str(control or "").strip()
    lowered = raw.lower().replace("-", "_").replace(" ", "_")
    # Map UI aliases to canonical banned ids.
    alias_map = {
        "trade_now": "trade_now",
        "override_risk": "override_risk",
        "force_long": "force_long",
        "force_short": "force_short",
        "change_leverage": "change_leverage",
        "enable_mainnet": "enable_mainnet",
        "force_long_short": "force_long",
    }
    if lowered in alias_map:
        return alias_map[lowered]
    return lowered


def is_banned_control(control: str) -> bool:
    cleaned = _normalize(control)
    if cleaned in BANNED_CONTROLS:
        return True
    raw = str(control or "").strip()
    if raw in BANNED_CONTROL_ALIASES:
        return True
    # Substring guard for force LONG/SHORT style labels.
    low = raw.lower()
    for banned in ("trade now", "override risk", "force long", "force short", "change leverage", "enable mainnet"):
        if banned in low:
            return True
    return False


def apply_control(
    *,
    control: str,
    params: dict[str, Any] | None = None,
    actor_tier: str,
    identity_source: str,
) -> dict[str, Any]:
    """Apply an allowed control or fail-closed on banned/unknown."""
    params = params or {}
    cleaned = _normalize(control)

    if is_banned_control(control) or cleaned in BANNED_CONTROLS:
        return {
            "ok": False,
            "applied": False,
            "control": cleaned,
            "error": "banned_control",
            "banned": True,
            "exchangeWriteEnabled": False,
            "mainnetShortcut": False,
            "realExecutionEnabled": False,
            "founderOnly": True,
            "memberAccessible": False,
        }

    if cleaned not in ALLOWED_CONTROLS:
        return {
            "ok": False,
            "applied": False,
            "control": cleaned,
            "error": "unknown_or_disallowed_control",
            "allowedControls": list(ALLOWED_CONTROLS),
            "founderOnly": True,
            "memberAccessible": False,
            "exchangeWriteEnabled": False,
        }

    try:
        if cleaned == "pause_ingest":
            st = ops_state.set_ingest_paused(True)
        elif cleaned == "resume_ingest":
            st = ops_state.set_ingest_paused(False)
        elif cleaned == "disable_provider":
            st = ops_state.disable_provider(str(params.get("provider_id") or params.get("providerId") or ""))
        elif cleaned == "disable_source":
            st = ops_state.disable_source(str(params.get("source_id") or params.get("sourceId") or ""))
        elif cleaned == "force_read_only_degraded_mode":
            st = ops_state.force_read_only_degraded(True)
        elif cleaned == "export_evidence":
            st = ops_state.get_state()
        else:  # pragma: no cover — guarded by ALLOWED_CONTROLS
            return {
                "ok": False,
                "applied": False,
                "control": cleaned,
                "error": "unhandled_allowed_control",
            }
    except ValueError as exc:
        return {
            "ok": False,
            "applied": False,
            "control": cleaned,
            "error": str(exc),
            "founderOnly": True,
            "memberAccessible": False,
        }

    result: dict[str, Any] = {
        "ok": True,
        "applied": True,
        "control": cleaned,
        "appliedAt": _utc(),
        "actor": {"tier": actor_tier, "identitySource": identity_source},
        "opsState": {
            "ingest_paused": st.get("ingest_paused"),
            "disabled_providers": st.get("disabled_providers"),
            "disabled_sources": st.get("disabled_sources"),
            "read_only_degraded": st.get("read_only_degraded"),
            "emergency_read_only_stop": st.get("emergency_read_only_stop"),
            "updated_at": st.get("updated_at"),
        },
        "exchangeWriteEnabled": False,
        "mainnetShortcut": False,
        "realExecutionEnabled": False,
        "founderOnly": True,
        "memberAccessible": False,
        "banned_control_count": 0,
    }
    if cleaned == "export_evidence":
        result["evidenceExport"] = {
            "schema": "pub18_c_founder_ops_evidence_export_v1",
            "exportedAt": _utc(),
            "opsState": result["opsState"],
            "allowedControls": list(ALLOWED_CONTROLS),
            "bannedControls": list(BANNED_CONTROLS),
            "banned_control_count": 0,
            "note": "Evidence export only — no report/archive rebuild.",
        }
    return result

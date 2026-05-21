from __future__ import annotations

from datetime import datetime

from config.autonomy_config import NEXUS_SHADOW_MODE, NEXUS_AUTONOMY_LEVEL


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ShadowModeService:
    """P3 shadow execution: record would-be trades without submitting when gated."""

    def __init__(self, runtime_store, enabled=None):
        self.runtime_store = runtime_store
        self.enabled = NEXUS_SHADOW_MODE if enabled is None else enabled

    def should_shadow(self):
        return bool(self.enabled and int(NEXUS_AUTONOMY_LEVEL or 1) < 2)

    def record_shadow_trade(self, proposal, validation):
        if not self.should_shadow():
            return None
        entry = {
            "timestamp": _now(),
            "proposal_id": proposal.get("proposal_id"),
            "symbol": proposal.get("symbol"),
            "fleet": proposal.get("fleet"),
            "side": proposal.get("side"),
            "approved_by_validation": bool(validation.get("approved")),
            "governance_reason": validation.get("governance_reason"),
            "trace_id": validation.get("trace_id"),
        }
        self.runtime_store.append_shadow_session(entry)
        return entry

    def snapshot(self, limit=30):
        return {
            "enabled": self.enabled,
            "autonomy_level": int(NEXUS_AUTONOMY_LEVEL or 1),
            "active": self.should_shadow(),
            "recent": self.runtime_store.recent_shadow_sessions(limit=limit),
        }

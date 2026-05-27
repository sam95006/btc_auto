from __future__ import annotations

import os
import uuid
from datetime import datetime

from backend.trading.sandbox_mode import sandbox_active
from config.autonomy_config import NEXUS_AUTONOMY_LEVEL, NEXUS_SHADOW_MODE


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ExecutionGovernor:
    """P2 governance layer on top of validation_pipeline (hard safety envelope)."""

    def __init__(self, shadow_mode_enabled=None):
        self.shadow_mode_enabled = NEXUS_SHADOW_MODE if shadow_mode_enabled is None else shadow_mode_enabled
        self.autonomy_level = max(0, min(3, int(NEXUS_AUTONOMY_LEVEL or 1)))

    def evaluate(self, proposal, validation, portfolio_status=None, learning_guidance=None):
        validation = dict(validation or {})
        portfolio_status = portfolio_status or {}
        learning_guidance = learning_guidance or {}
        trace_id = str(uuid.uuid4())
        approved = bool(validation.get("approved"))
        reason = validation.get("reason", "")
        reject_layer = None
        why_not = []

        if approved and learning_guidance.get("pause_new_entries") and not sandbox_active():
            approved = False
            reason = "learning_pause_new_entries"
            reject_layer = "learning_guard"
            why_not.append("consecutive_loss_pause")

        if approved and learning_guidance.get("regime_blocked") and not sandbox_active():
            approved = False
            reason = "learning_regime_blocked"
            reject_layer = "learning_guard"
            why_not.append("regime_blocked_by_learning")

        fleet = str(proposal.get("fleet") or "").upper()
        restriction = dict((portfolio_status.get("fleet_restrictions") or {}).get(fleet, {}))
        if approved and not restriction.get("allowed_new_entries", True):
            approved = False
            reason = "portfolio_governor_block"
            reject_layer = "portfolio_governor"
            why_not.append("fleet_restricted_by_portfolio")

        shadow_only = False
        if (
            self.shadow_mode_enabled
            and self.autonomy_level < 2
            and not (sandbox_active() and SANDBOX_FORCE_LIVE_EXECUTE)
        ):
            shadow_only = True
            if approved:
                why_not.append("shadow_mode_blocks_live_execution")

        return {
            **validation,
            "trace_id": trace_id,
            "approved": approved and not shadow_only,
            "governance_reason": reason,
            "reject_layer": reject_layer or validation.get("reject_layer"),
            "why_not": why_not or validation.get("why_not"),
            "shadow_only": shadow_only,
            "autonomy_level": self.autonomy_level,
            "governed_at": _now(),
        }

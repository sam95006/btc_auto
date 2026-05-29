from __future__ import annotations

import os
import uuid
from datetime import datetime

from backend.trading.sandbox_mode import sandbox_active
from config.autonomy_config import NEXUS_AUTONOMY_LEVEL, NEXUS_SHADOW_MODE
from config.testnet_sandbox_config import SANDBOX_FORCE_LIVE_EXECUTE


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ExecutionGovernor:
    """P2 governance layer on top of validation_pipeline (hard safety envelope)."""

    def __init__(self, shadow_mode_enabled=None):
        self.shadow_mode_enabled = NEXUS_SHADOW_MODE if shadow_mode_enabled is None else shadow_mode_enabled
        self.autonomy_level = max(0, min(3, int(NEXUS_AUTONOMY_LEVEL or 1)))

    def evaluate(
        self,
        proposal,
        validation,
        portfolio_status=None,
        learning_guidance=None,
        regime_state=None,
        dynamic_blocklist=None,
    ):
        validation = dict(validation or {})
        portfolio_status = portfolio_status or {}
        learning_guidance = learning_guidance or {}
        regime_state = dict(regime_state or {})
        proposal = dict(proposal or {})
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
        symbol = str(proposal.get("symbol") or "").upper()
        strategy_key = str(proposal.get("strategy_key") or "")
        regime_label = str(regime_state.get("label") or "").upper()

        if approved and dynamic_blocklist is not None and dynamic_blocklist.is_symbol_blocked(symbol):
            approved = False
            reason = "dynamic_blocklist"
            reject_layer = "post_mortem_guard"
            why_not.append("symbol_blocked_by_postmortem")

        if (
            approved
            and regime_label == "HIGH_RISK_MACRO"
            and strategy_key != "market_neutral_funding"
        ):
            approved = False
            reason = "regime_high_risk_macro"
            reject_layer = "regime_classifier"
            why_not.append("high_risk_macro_no_new_entries")

        if approved and regime_label == "CHOP_RNG" and fleet == "PEPE":
            approved = False
            reason = "regime_chop_blocks_pepe"
            reject_layer = "regime_classifier"
            why_not.append("chop_range_blocks_meme_breakout")

        if (
            approved
            and regime_label == "CHOP_RNG"
            and fleet == "RADAR"
            and strategy_key in {"radar_market_scan_strategy", "ai_led_trade_proposer"}
        ):
            approved = False
            reason = "regime_chop_blocks_radar_directional"
            reject_layer = "regime_classifier"
            why_not.append("chop_range_blocks_radar")

        matrix_score = proposal.get("confidence_matrix", {}).get("confidence_score")
        if approved and matrix_score is not None and float(matrix_score) < 60.0:
            approved = False
            reason = "confidence_matrix_below_min"
            reject_layer = "confidence_matrix"
            why_not.append("score_below_60")

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

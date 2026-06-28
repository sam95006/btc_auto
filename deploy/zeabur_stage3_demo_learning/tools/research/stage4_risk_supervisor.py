"""Stage 4 Risk Supervisor — veto/adjust AI proposals; never submits orders."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tools.research.bybit_demo_learning_common import (
    MAX_LEVERAGE,
    MAX_MARGIN_USD,
    MAX_OPEN_POSITIONS,
    utc_now_iso,
)

CONFIDENCE_THRESHOLD = 0.35
VETO_ACTIONS = frozenset({"block_reentry", "manual_review_required"})


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def safety_constraints_from_env() -> Dict[str, Any]:
    return {
        "max_margin_usd": float(os.environ.get("MAX_MARGIN_USD", MAX_MARGIN_USD)),
        "max_leverage": int(float(os.environ.get("MAX_LEVERAGE", MAX_LEVERAGE))),
        "max_open_positions": int(float(os.environ.get("MAX_OPEN_POSITIONS", MAX_OPEN_POSITIONS))),
        "require_stop_loss": _truthy(os.environ.get("REQUIRE_STOP_LOSS", "true")),
        "require_max_hold": _truthy(os.environ.get("REQUIRE_MAX_HOLD", "true")),
        "mainnet_allowed": _truthy(os.environ.get("BYBIT_MAINNET_ALLOWED")),
        "real_money": _truthy(os.environ.get("REAL_MONEY")),
        "production_promotion_allowed": _truthy(os.environ.get("PRODUCTION_PROMOTION_ALLOWED")),
        "arm_allowed": _truthy(os.environ.get("ARM_ALLOWED")),
    }


@dataclass
class RiskSupervisorResult:
    approved: bool
    final_decision: str
    veto_reason: str = ""
    adjusted_confidence: float = 0.0
    adjusted_position_size: float = 0.0
    action: str = "approve"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "veto_reason": self.veto_reason,
            "adjusted_confidence": self.adjusted_confidence,
            "adjusted_position_size": self.adjusted_position_size,
            "action": self.action,
            "final_decision": self.final_decision,
            "notes": self.notes,
            "evaluated_at_utc": utc_now_iso(),
        }


class Stage4RiskSupervisor:
    def __init__(
        self,
        *,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.constraints = constraints or safety_constraints_from_env()

    def evaluate(
        self,
        *,
        proposal: Dict[str, Any],
        account_context: Dict[str, Any],
        retrieved_patches: List[Dict[str, Any]],
        open_positions: int = 0,
        market_context: Optional[Dict[str, Any]] = None,
        dry_run: bool = True,
    ) -> RiskSupervisorResult:
        notes: List[str] = []
        conf = float(proposal.get("confidence") or 0)
        size = float(proposal.get("position_size_suggestion") or 0)
        side = str(proposal.get("candidate_side") or "NONE").upper()
        action = str(proposal.get("final_action") or "skip").lower()
        intent = str(proposal.get("decision_intent") or "").lower()
        mc = market_context or {}

        c = self.constraints
        if c.get("mainnet_allowed"):
            return self._veto("mainnet_allowed_true", conf, size, notes)
        if c.get("real_money"):
            return self._veto("real_money_true", conf, size, notes)
        if c.get("production_promotion_allowed"):
            return self._veto("production_promotion_allowed_true", conf, size, notes)
        if c.get("arm_allowed"):
            return self._veto("arm_allowed_true", conf, size, notes)
        if not c.get("require_stop_loss"):
            return self._veto("require_stop_loss_false", conf, size, notes)
        if not c.get("require_max_hold"):
            return self._veto("require_max_hold_false", conf, size, notes)

        max_margin = float(c.get("max_margin_usd") or MAX_MARGIN_USD)
        max_pos = int(c.get("max_open_positions") or MAX_OPEN_POSITIONS)

        if size > max_margin:
            size = max_margin
            conf = min(conf, conf * 0.85)
            notes.append("reduce_position_size_to_max_margin")

        data_quality = str(mc.get("data_quality") or "ok")
        if data_quality == "error":
            return self._force_skip("missing_market_context", conf, size, notes)

        for patch in retrieved_patches:
            patch_action = str(patch.get("action") or "")
            if patch_action in VETO_ACTIONS:
                notes.append(f"active_patch_{patch_action}")
                return self._force_skip("patch_block", conf, size, notes)

        if open_positions >= max_pos and action == "enter":
            return self._force_skip("open_positions_at_cap", conf, size, notes)

        avail = float(account_context.get("available_balance") or 0)
        if action == "enter" and avail < max_margin:
            return self._force_skip("account_available_below_max_margin", conf, size, notes)

        if dry_run and _truthy(os.environ.get("STAGE4_ORDER_ALLOWED")) is False and action == "enter":
            return self._force_skip("order_not_allowed_dry_run", conf, size, notes)

        if action != "enter" or side == "NONE":
            if intent == "hard_skip":
                return self._force_skip("hard_skip", conf, size, notes)
            if intent == "soft_skip":
                return self._force_skip("soft_skip", conf, size, notes)
            if intent == "watch":
                return self._force_skip("watch", conf, size, notes)
            if conf < self.confidence_threshold:
                reason = "soft_skip" if conf >= 0.1 else "hard_skip"
                return self._force_skip(reason, conf, size, notes)
            return RiskSupervisorResult(
                approved=False,
                final_decision="skip",
                veto_reason="agent_recommended_skip",
                adjusted_confidence=conf,
                adjusted_position_size=size,
                action="approve",
                notes=notes or ["agent_recommended_skip"],
            )

        if conf < self.confidence_threshold:
            notes.append("confidence_below_threshold")
            return self._force_skip("confidence_below_threshold", conf, size, notes)

        return RiskSupervisorResult(
            approved=True,
            final_decision="enter",
            adjusted_confidence=round(conf, 4),
            adjusted_position_size=round(min(size, max_margin), 4),
            action="approve",
            notes=notes,
        )

    def _veto(
        self,
        reason: str,
        conf: float,
        size: float,
        notes: List[str],
        *,
        action: str = "veto",
    ) -> RiskSupervisorResult:
        notes.append(reason)
        return RiskSupervisorResult(
            approved=False,
            final_decision="skip",
            veto_reason=reason,
            adjusted_confidence=conf,
            adjusted_position_size=size,
            action=action,
            notes=notes,
        )

    def _force_skip(
        self,
        reason: str,
        conf: float,
        size: float,
        notes: List[str],
    ) -> RiskSupervisorResult:
        if reason not in notes:
            notes.append(reason)
        return RiskSupervisorResult(
            approved=False,
            final_decision="skip",
            veto_reason=reason,
            adjusted_confidence=conf,
            adjusted_position_size=size,
            action="force_skip",
            notes=notes,
        )

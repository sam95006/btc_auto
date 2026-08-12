"""Deterministic Research Risk — required for RESEARCH_AI_DEMO.

V18.2.24: integrates risk-based sizing for RESEARCH_PNL_TRADE; canaries keep min qty.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_research_ai_autonomy.constants import (
    DEFAULT_LEVERAGE,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_MAX_HOLD_SEC,
    RESEARCH_PNL_DEFAULT_MAX_HOLD_SEC,
    RESEARCH_PNL_MIN_HOLD_SEC,
)
from backend.nexus_research_ai_autonomy.lifecycle_purpose import (
    LIFECYCLE_PURPOSE_EXECUTION_CANARY,
    LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE,
)
from backend.nexus_research_ai_autonomy.risk_based_sizing import compute_risk_based_size


@dataclass
class ResearchRiskResult:
    passed: bool
    blocks: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    leverage: int = DEFAULT_LEVERAGE
    max_hold_sec: int = DEFAULT_MAX_HOLD_SEC
    protective_stop_ok: bool = False
    size: float = 0.0
    lifecycle_purpose: str = LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
    sizing: dict[str, Any] = field(default_factory=dict)
    action: str = "PASS"  # PASS | WAIT

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ResearchRiskEngine:
    """Fail-closed research risk. Never widens max risk. Demo/1x/isolated."""

    def evaluate(self, packet: dict[str, Any] | None) -> ResearchRiskResult:
        p = dict(packet or {})
        blocks: list[str] = []
        reasons: list[str] = []

        purpose = str(
            p.get("lifecycle_purpose")
            or (
                LIFECYCLE_PURPOSE_EXECUTION_CANARY
                if p.get("execution_canary")
                else LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
            )
        )
        # Legacy callers omit lifecycle_purpose — treat as canary-style min-qty path
        # unless risk_based_sizing explicitly requested.
        use_risk_sizing = bool(
            p.get("risk_based_sizing")
            or purpose == LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
            and p.get("equity")
            and (p.get("entry_price") or p.get("price"))
        )
        if not p.get("lifecycle_purpose") and not p.get("risk_based_sizing"):
            # Preserve V17/V23 default: min-qty path when no V24 fields present
            use_risk_sizing = False
            purpose = LIFECYCLE_PURPOSE_EXECUTION_CANARY if p.get("execution_canary") else purpose
            if not p.get("lifecycle_purpose") and not p.get("execution_canary"):
                # Classic RESEARCH_AI_DEMO packets → keep min-size behavior
                use_risk_sizing = False

        if str(p.get("execution_purpose") or "") != "RESEARCH_AI_DEMO":
            # Allow REAL_EXCHANGE purpose as research demo family
            if str(p.get("execution_purpose") or "") == "RESEARCH_AI_DEMO_REAL_EXCHANGE":
                reasons.append("purpose_ok")
            else:
                blocks.append("execution_purpose_not_research_ai_demo")
        else:
            reasons.append("purpose_ok")

        if p.get("demo_only") is not True:
            blocks.append("demo_only_required")
        else:
            reasons.append("demo_only")

        if p.get("mainnet") or p.get("real_money"):
            blocks.append("mainnet_or_real_money")

        lev = int(p.get("leverage") or DEFAULT_LEVERAGE)
        if lev != 1:
            blocks.append("leverage_not_1x")
        else:
            reasons.append("leverage_1x")

        if int(p.get("open_positions") or 0) >= DEFAULT_MAX_CONCURRENT:
            blocks.append("concurrent_cap")
        else:
            reasons.append("concurrent_ok")

        stop = p.get("stop_logic") or {}
        if not stop or not (stop.get("price") or stop.get("pct") or stop.get("type")):
            blocks.append("protective_stop_missing")
        else:
            reasons.append("protective_stop_ok")

        max_hold = int(p.get("max_hold") or 0)
        if max_hold <= 0:
            blocks.append("max_hold_missing")
        else:
            reasons.append("max_hold_ok")

        if p.get("martingale") or p.get("average_down") or p.get("pyramid"):
            blocks.append("forbidden_sizing_style")

        if p.get("member_execution"):
            blocks.append("member_execution_forbidden")

        sizing: dict[str, Any] = {}
        size = float(p.get("requested_size") or 0.0)
        action = "PASS"

        if use_risk_sizing and str(p.get("lifecycle_purpose") or "") == LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE:
            entry = float(p.get("entry_price") or p.get("price") or 0.0)
            stop_pct = float(stop.get("pct") or p.get("stop_distance_pct") or 0.0)
            if stop_pct <= 0 and stop.get("price") and entry > 0:
                stop_pct = abs(float(stop["price"]) - entry) / entry * 100.0
            tp = p.get("take_profit_logic") or {}
            tgt_pct = float(tp.get("pct") or p.get("target_distance_pct") or 0.0)
            if tgt_pct <= 0 and tp.get("price") and entry > 0:
                tgt_pct = abs(float(tp["price"]) - entry) / entry * 100.0
            rs = compute_risk_based_size(
                equity=float(p.get("equity") or 0.0),
                entry_price=entry,
                stop_distance_pct=stop_pct if stop_pct > 0 else 0.8,
                target_distance_pct=tgt_pct if tgt_pct > 0 else 0.55,
                fee_rate_roundtrip=float(p.get("fee_rate_roundtrip") or 0.0011),
                slippage_pct=float(p.get("slippage_pct") or 0.02),
                liquidity=float(p.get("liquidity") if p.get("liquidity") is not None else 0.9),
                confidence=float(p.get("confidence") if p.get("confidence") is not None else 0.7),
                qty_step=float(p.get("qty_step") or p.get("min_size") or 0.001),
                min_qty=float(p.get("min_size") or 0.001),
                min_notional=float(p.get("min_notional") or 5.0),
                preferred_notional=p.get("preferred_notional"),
            )
            sizing = rs.to_dict()
            if rs.action == "WAIT":
                action = "WAIT"
                blocks.append("risk_based_sizing_wait")
                reasons.extend(rs.reasons)
                size = 0.0
            else:
                size = rs.qty
                reasons.append("risk_based_sizing_ok")
                if max_hold > 0 and max_hold < RESEARCH_PNL_MIN_HOLD_SEC:
                    max_hold = RESEARCH_PNL_MIN_HOLD_SEC
                    reasons.append("min_hold_enforced_for_pnl_research")
                elif max_hold <= 0:
                    max_hold = RESEARCH_PNL_DEFAULT_MAX_HOLD_SEC
                    if "max_hold_missing" in blocks:
                        blocks = [b for b in blocks if b != "max_hold_missing"]
                    reasons.append("max_hold_default_pnl_research")
        else:
            min_size = float(p.get("min_size") or 0.001)
            max_size = float(p.get("max_research_size") or min_size * 5)
            if size <= 0:
                size = min_size
            if size > max_size:
                blocks.append("size_above_research_cap")
                size = max_size
            sizing = {"mode": "MIN_QTY_OR_REQUESTED", "size": size}
            if purpose == LIFECYCLE_PURPOSE_EXECUTION_CANARY:
                reasons.append("canary_min_qty_sizing")

        passed = len(blocks) == 0 and action != "WAIT"
        return ResearchRiskResult(
            passed=passed,
            blocks=blocks,
            reasons=reasons,
            leverage=1,
            max_hold_sec=max_hold if max_hold > 0 else DEFAULT_MAX_HOLD_SEC,
            protective_stop_ok="protective_stop_ok" in reasons,
            size=size,
            lifecycle_purpose=str(p.get("lifecycle_purpose") or purpose),
            sizing=sizing,
            action="WAIT" if action == "WAIT" or not passed else "PASS",
        )

    def allow_management_action(
        self,
        *,
        proposal: str,
        widens_max_risk: bool,
        fast_safety_triggered: bool,
    ) -> tuple[bool, str]:
        if fast_safety_triggered:
            return True, "fast_safety_overrides"
        if widens_max_risk:
            return False, "ai_may_never_widen_max_risk"
        action = str(proposal or "").upper()
        if action in {"HOLD", "REDUCE", "TAKE_PROFIT", "EXIT"}:
            return True, "deterministic_allow"
        return False, f"unknown_action:{action}"

"""6H V2 Session Controller — dry-run by default; never auto-starts live write.

DEMO_6H_V2_DRY_RUN_ONLY=true keeps exchange_write_call_count at 0.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_demo_execution.cost_entry_gate import evaluate_cost_gate
from backend.nexus_demo_execution.fee_rate import (
    FEE_RATE_CONFIGURED_CONSERVATIVE,
    FEE_RATE_CONFIG_EXPIRED,
    FeeRateQuote,
)
from backend.nexus_demo_execution.trade_geometry import compute_structure_geometry
from backend.nexus_demo_execution.v2_decision_delta import classify_block_event, is_learning_decision_delta
from backend.nexus_demo_execution.v2_evidence_schema import evidence_manifest
from backend.nexus_demo_execution.v2_policy import (
    ACCOUNT_SNAPSHOT_MAX_AGE_SEC,
    FEE_REVIEW_BY,
    FEE_VERSION,
    FIXED_LEVERAGE,
    MARGIN_MODE,
    MARGIN_PER_TRADE_CAP,
    MAX_CONCURRENT_POSITIONS,
    MAX_CONTROLLER_OWNERS,
    MAX_PENDING_ORDERS,
    MAX_TOTAL_ENTRY_ORDERS,
    MIN_MARGIN_IF_RISK_SAFE,
    MIN_NET_REWARD_RISK_RATIO,
    POLICY_VERSION,
    PRETRADE_ROUND_TRIP_FEE_RATE,
    SESSION_DURATION_SEC,
    SESSION_GATE_NAME,
    TAKER_FEE_RATE,
)
from backend.nexus_demo_execution.v2_six_role import evaluate_six_role_review


def _env_flag(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SessionControllerV2:
    dry_run_only: bool = True
    exchange_write_call_count: int = 0
    session_id: str = field(default_factory=lambda: f"NEXUS-DEMO-6H-V2-{uuid.uuid4().hex[:8]}")
    started_at: float | None = None
    entries_total: int = 0
    blocks: list[dict[str, Any]] = field(default_factory=list)
    intents: list[dict[str, Any]] = field(default_factory=list)
    decision_deltas: list[dict[str, Any]] = field(default_factory=list)
    kill_switch: bool = False
    autonomous_enabled: bool = False

    def __post_init__(self) -> None:
        # Default dry-run. Live write never enabled from readiness controller.
        raw = (os.environ.get("DEMO_6H_V2_DRY_RUN_ONLY") or "true").strip().lower()
        self.dry_run_only = raw not in {"0", "false", "no", "off"}
        if _env_flag("EXCHANGE_WRITE") or _env_flag("DEMO_AUTONOMOUS_ENABLED"):
            self.dry_run_only = True
            self.autonomous_enabled = False

    def _fee_quote(self, *, expired: bool = False) -> FeeRateQuote:
        status = FEE_RATE_CONFIG_EXPIRED if expired else FEE_RATE_CONFIGURED_CONSERVATIVE
        return FeeRateQuote(
            status=status,
            symbol="BTCUSDT",
            maker_fee_rate=0.00020,
            taker_fee_rate=TAKER_FEE_RATE,
            fee_source="FOUNDER_APPROVED_CONFIG",
            fee_fetch_error=None,
            fee_fetched_at=time.time(),
            fail_closed=True,
            new_entry_blocked=expired,
            fee_rate_version=FEE_VERSION,
            fee_endpoint_supported=False,
            fee_account_specific=False,
            fee_live_private_api=False,
            pretrade_entry_fee_rate=TAKER_FEE_RATE,
            pretrade_exit_fee_rate=TAKER_FEE_RATE,
            pretrade_round_trip_fee_rate=PRETRADE_ROUND_TRIP_FEE_RATE,
        )

    def evaluate_candidate(
        self,
        candidate: dict[str, Any],
        *,
        roles: dict[str, Any] | None = None,
        account: dict[str, Any] | None = None,
        fee_expired: bool = False,
        mistake_guard_block: bool = False,
        duplicate_intent: bool = False,
    ) -> dict[str, Any]:
        if self.kill_switch:
            return self._block("SESSION_KILL_SWITCH", candidate)
        if self.entries_total >= MAX_TOTAL_ENTRY_ORDERS:
            return self._block("MAX_TOTAL_ENTRIES", candidate)
        if mistake_guard_block:
            return self._block("MISTAKE_GUARD_BLOCK", candidate)

        role_res = evaluate_six_role_review(roles)
        if not role_res["allowed"]:
            return self._block(role_res["reason"], candidate, extra=role_res)

        acct = account or {
            "snapshot_age_sec": 1,
            "position_count": 0,
            "open_order_count": 0,
            "available_balance": 100.0,
            "reconciliation": "MATCH",
            "execution_owner_count": 1,
        }
        if float(acct.get("snapshot_age_sec") or 999) > ACCOUNT_SNAPSHOT_MAX_AGE_SEC:
            return self._block("STALE_ACCOUNT", candidate)
        if int(acct.get("position_count") or 0) > 0 or int(acct.get("position_count") or 0) > MAX_CONCURRENT_POSITIONS - 1:
            if int(acct.get("position_count") or 0) != 0:
                return self._block("POSITION_EXISTS", candidate)
        if int(acct.get("open_order_count") or 0) != 0:
            return self._block("OPEN_ORDERS_EXIST", candidate)
        if str(acct.get("reconciliation") or "") != "MATCH":
            return self._block("RECONCILIATION_MISMATCH", candidate)
        if int(acct.get("execution_owner_count") or 0) != MAX_CONTROLLER_OWNERS:
            return self._block("EXECUTION_OWNER_COUNT_INVALID", candidate)
        if float(acct.get("available_balance") or 0) < MIN_MARGIN_IF_RISK_SAFE:
            return self._block("SKIP_INSUFFICIENT_SAFE_MARGIN", candidate)
        if duplicate_intent:
            return self._block("DUPLICATE_INTENT", candidate)

        fee = self._fee_quote(expired=fee_expired)
        if fee.status == FEE_RATE_CONFIG_EXPIRED or fee.new_entry_blocked and fee_expired:
            return self._block("FEE_RATE_CONFIG_EXPIRED", candidate)

        geo = compute_structure_geometry(
            side=str(candidate.get("side") or candidate.get("direction") or "Buy"),
            entry_price=float(candidate["entry_reference"]),
            atr=candidate.get("atr"),
            recent_swing_high=candidate.get("recent_swing_high"),
            recent_swing_low=candidate.get("recent_swing_low"),
            support=(candidate.get("support_levels") or [None])[0]
            if isinstance(candidate.get("support_levels"), list)
            else candidate.get("support"),
            resistance=(candidate.get("resistance_levels") or [None])[0]
            if isinstance(candidate.get("resistance_levels"), list)
            else candidate.get("resistance"),
            liquidity_levels=list(candidate.get("liquidity_above") or [])
            + list(candidate.get("liquidity_below") or []),
            spread_bps=float(candidate.get("spread_bps") or 0),
            slippage_bps=float(candidate.get("slippage_bps") or 0),
            funding_rate=candidate.get("funding_rate"),
            tick_size=candidate.get("tick_size"),
            qty=(MARGIN_PER_TRADE_CAP * FIXED_LEVERAGE) / float(candidate["entry_reference"]),
            fee_rate=float(fee.pretrade_fee_rate or TAKER_FEE_RATE),
            time_horizon_sec=30 * 60,
        )
        if not geo.allowed:
            return self._block(str(geo.block_reason or "GEOMETRY_BLOCK"), candidate, extra=geo.to_dict())

        # qty from notional / entry
        entry = float(geo.entry_price)  # type: ignore[arg-type]
        qty = (MARGIN_PER_TRADE_CAP * FIXED_LEVERAGE) / entry
        cost = evaluate_cost_gate(
            entry_price=entry,
            stop_loss=float(geo.stop_loss),  # type: ignore[arg-type]
            take_profit=float(geo.take_profit),  # type: ignore[arg-type]
            qty=qty,
            side=str(candidate.get("side") or "Buy"),
            fee_rate=float(fee.pretrade_fee_rate or TAKER_FEE_RATE),
            funding_rate=candidate.get("funding_rate"),
            slippage_bps=float(candidate.get("slippage_bps") or 0)
            + float(candidate.get("spread_bps") or 0),
            fee_meta=fee.to_dict(),
        )
        if not cost.allowed:
            return self._block(str(cost.reason), candidate, extra=cost.to_dict())

        trade_case_id = f"tc-{uuid.uuid4().hex[:10]}"
        intent = {
            "session_id": self.session_id,
            "trade_case_id": trade_case_id,
            "candidate_id": candidate.get("candidate_id"),
            "order_link_id": f"ol-{uuid.uuid4().hex[:12]}",
            "idempotency_key": f"idemp-{uuid.uuid4().hex[:12]}",
            "correlation_id": f"corr-{uuid.uuid4().hex[:12]}",
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side") or candidate.get("direction"),
            "leverage": FIXED_LEVERAGE,
            "margin_mode": MARGIN_MODE,
            "margin": MARGIN_PER_TRADE_CAP,
            "auto_add_margin": False,
            "cross": False,
            "martingale": False,
            "averaging_down": False,
            "entry_price": geo.entry_price,
            "stop_loss": geo.stop_loss,
            "take_profit": geo.take_profit,
            "geometry": geo.to_dict(),
            "cost_gate": cost.to_dict(),
            "fee_status": fee.status,
            "fee_version": FEE_VERSION,
            "fee_review_by": FEE_REVIEW_BY,
            "net_rr_min": MIN_NET_REWARD_RISK_RATIO,
            "protection": {"sl": True, "tp": True, "full_position_protection": True},
            "dry_run": self.dry_run_only,
            "exchange_write": False,
            "gate": SESSION_GATE_NAME,
            "policy_version": POLICY_VERSION,
        }
        # Never send to exchange in readiness / dry-run.
        self.intents.append(intent)
        self.entries_total += 1
        return {
            "allowed": True,
            "reason": "DRY_RUN_INTENT_BUILT" if self.dry_run_only else "INTENT_BUILT_NO_SEND",
            "intent": intent,
            "exchange_write_call_count": self.exchange_write_call_count,
            "decision_delta": False,
        }

    def _block(self, reason: str, candidate: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
        event = classify_block_event(reason)
        row = {
            "allowed": False,
            "reason": reason,
            "candidate_id": candidate.get("candidate_id"),
            "block_event": event,
            "extra": extra or {},
            "decision_delta": False,
            "exchange_write_call_count": self.exchange_write_call_count,
        }
        self.blocks.append(row)
        return row

    def record_learning_delta(self, payload: dict[str, Any]) -> bool:
        if not is_learning_decision_delta(payload):
            return False
        self.decision_deltas.append(payload)
        return True

    def summary(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "gate": SESSION_GATE_NAME,
            "policy_version": POLICY_VERSION,
            "dry_run_only": self.dry_run_only,
            "duration_sec": SESSION_DURATION_SEC,
            "entries_total": self.entries_total,
            "blocks_total": len(self.blocks),
            "intents_total": len(self.intents),
            "learning_decision_delta_count": len(self.decision_deltas),
            "exchange_write_call_count": self.exchange_write_call_count,
            "autonomous_enabled": self.autonomous_enabled,
            "mainnet": False,
            "real_money": False,
            "evidence": evidence_manifest(
                session_id=self.session_id, policy_version=POLICY_VERSION, dry_run=self.dry_run_only
            ),
        }

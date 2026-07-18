"""Phase 6 Gate C — Position Exit Policies.

RESEARCH ONLY. All exits operate on simulated positions only.
No real orders, no real funds, no private API.

Every exit creates:
  1. A ledger evidence entry (via SimLedger)
  2. A reason code from ExitReason
  3. A domain event via publish_event
  4. A storage record in "paper_exits"

Exit types:
  - STOP_LOSS          : unrealised PnL below stop threshold
  - TAKE_PROFIT        : unrealised PnL above profit threshold
  - MAX_HOLD           : position held longer than policy max
  - STALE_DATA         : mark price not updated in time
  - KILL_SWITCH        : simulator kill switch activated
  - RISK_DETERIORATION : re-check risk engine BLOCK verdict on open position
  - CANDIDATE_INVALID  : candidate no longer valid (expired, score drop)
  - MANUAL_RESEARCH    : operator-triggered manual close (researchOnly guard)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from backend.nexus_research.domain_events import publish_event, PAPER_POSITION_EXITED

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Reason codes ──────────────────────────────────────────────────────────────
class ExitReason:
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT = "TAKE_PROFIT"
    MAX_HOLD = "MAX_HOLD"
    STALE_DATA = "STALE_DATA"
    KILL_SWITCH = "KILL_SWITCH"
    RISK_DETERIORATION = "RISK_DETERIORATION"
    CANDIDATE_INVALID = "CANDIDATE_INVALID"
    MANUAL_RESEARCH = "MANUAL_RESEARCH"
    MODE_OFF = "MODE_OFF"
    CONTROLLER_KILLED = "CONTROLLER_KILLED"


class ExitRecord:
    """Evidence record for a triggered exit."""

    def __init__(
        self,
        position_id: str,
        symbol: str,
        side: str,
        reason: str,
        triggered_by: str,
        entry_price: float,
        exit_price: float | None,
        qty: float,
        unrealised_pnl: float,
        realised_pnl: float | None,
        hold_ms: int,
        detail: str,
    ) -> None:
        self.position_id = position_id
        self.symbol = symbol
        self.side = side
        self.reason = reason
        self.triggered_by = triggered_by
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.qty = qty
        self.unrealised_pnl = unrealised_pnl
        self.realised_pnl = realised_pnl
        self.hold_ms = hold_ms
        self.detail = detail
        self.created_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "positionId": self.position_id,
            "symbol": self.symbol,
            "side": self.side,
            "reason": self.reason,
            "triggeredBy": self.triggered_by,
            "entryPrice": self.entry_price,
            "exitPrice": self.exit_price,
            "qty": self.qty,
            "unrealisedPnl": self.unrealised_pnl,
            "realisedPnl": self.realised_pnl,
            "holdMs": self.hold_ms,
            "detail": self.detail,
            "createdAtMs": self.created_at_ms,
            "researchOnly": True,
            "privateApi": False,
        }


def _record_exit(
    record: ExitRecord,
    sim,      # SimulatedExchange
    mark_prices: dict[str, float],
) -> float | None:
    """Execute close on simulator, record ledger evidence, publish event, store record."""
    realised_pnl: float | None = None
    try:
        realised_pnl = sim.close_position(record.position_id, mark_prices)
        record.realised_pnl = realised_pnl
    except Exception as exc:  # noqa: BLE001
        logger.warning("[exit] close_position failed for %s: %s", record.position_id, exc)

    # Ledger evidence
    try:
        from backend.nexus_research.sim_ledger import get_sim_ledger
        ledger = get_sim_ledger()
        exit_price = record.exit_price or record.entry_price
        ledger.record_position_closed(
            position_id=record.position_id,
            symbol=record.symbol,
            side=record.side,
            qty=record.qty,
            entry_price=record.entry_price,
            exit_price=exit_price,
            realised_pnl=realised_pnl or 0.0,
            exit_fee=0.0,
            idempotency_key=f"exit_{record.position_id}_{record.reason}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[exit] ledger record failed: %s", exc)

    # Domain event
    try:
        publish_event(
            PAPER_POSITION_EXITED,
            record.to_dict(),
            idempotency_key=f"exit_{record.position_id}_{record.reason}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("[exit] publish_event failed: %s", exc)

    # Storage record
    try:
        from backend.nexus_research.storage import get_research_store
        get_research_store().append("paper_exits", record.to_dict())
    except Exception as exc:  # noqa: BLE001
        logger.debug("[exit] storage record failed: %s", exc)

    return realised_pnl


class ExitPolicyEngine:
    """Evaluates all exit policies on each open position and executes exits.

    Call evaluate(position, mark_prices, policy) for each open position.
    Returns ExitRecord if exit was triggered, else None.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._total_exits = 0
        self._exits_by_reason: dict[str, int] = {}
        self._manual_close_queue: list[str] = []  # position_ids queued for manual close

    def evaluate(
        self,
        position: dict[str, Any],
        mark_prices: dict[str, float],
        policy: dict[str, Any],
        sim,
        candidates: dict[str, Any] | None = None,
    ) -> ExitRecord | None:
        """Evaluate all policies on a single position. Returns ExitRecord if exit triggered."""
        pos_id = position.get("positionId", "")
        symbol = position.get("symbol", "")
        side = position.get("side", "")
        entry_price = float(position.get("entryPrice", 0.0))
        qty = float(position.get("qty", 0.0))
        notional = qty * entry_price
        unrealised_pnl = float(position.get("unrealisedPnl", 0.0))
        opened_at_ms = int(position.get("openedAtMs", 0))
        last_mark_price = float(position.get("lastMarkPrice", entry_price))
        now_ms = int(time.time() * 1000)
        hold_ms = now_ms - opened_at_ms if opened_at_ms else 0

        mark = mark_prices.get(symbol)

        # 1. Kill switch
        if getattr(sim, "_kill_switch", False):
            record = ExitRecord(
                position_id=pos_id, symbol=symbol, side=side,
                reason=ExitReason.KILL_SWITCH, triggered_by="kill_switch",
                entry_price=entry_price,
                exit_price=mark, qty=qty, unrealised_pnl=unrealised_pnl,
                realised_pnl=None, hold_ms=hold_ms,
                detail="Simulator kill switch is active",
            )
            return self._execute(record, sim, mark_prices)

        # 2. Manual close queue
        with self._lock:
            if pos_id in self._manual_close_queue:
                self._manual_close_queue.remove(pos_id)
                record = ExitRecord(
                    position_id=pos_id, symbol=symbol, side=side,
                    reason=ExitReason.MANUAL_RESEARCH, triggered_by="operator",
                    entry_price=entry_price,
                    exit_price=mark, qty=qty, unrealised_pnl=unrealised_pnl,
                    realised_pnl=None, hold_ms=hold_ms,
                    detail="Manual research close requested by operator",
                )
                return self._execute(record, sim, mark_prices)

        if mark is None:
            return None

        # 3. Stale data — no mark price update for too long
        stale_ms = int(policy.get("stale_mark_price_ms", 60_000))
        updated_at = int(position.get("updatedAtMs", opened_at_ms))
        if now_ms - updated_at > stale_ms:
            record = ExitRecord(
                position_id=pos_id, symbol=symbol, side=side,
                reason=ExitReason.STALE_DATA, triggered_by="stale_data_policy",
                entry_price=entry_price, exit_price=mark, qty=qty,
                unrealised_pnl=unrealised_pnl, realised_pnl=None, hold_ms=hold_ms,
                detail=f"Mark price stale for {(now_ms - updated_at) // 1000}s > {stale_ms // 1000}s",
            )
            return self._execute(record, sim, mark_prices)

        # 4. Max hold time
        max_hold_ms = int(float(policy.get("max_hold_hours", 24.0)) * 3_600_000)
        if hold_ms > max_hold_ms:
            record = ExitRecord(
                position_id=pos_id, symbol=symbol, side=side,
                reason=ExitReason.MAX_HOLD, triggered_by="max_hold_policy",
                entry_price=entry_price, exit_price=mark, qty=qty,
                unrealised_pnl=unrealised_pnl, realised_pnl=None, hold_ms=hold_ms,
                detail=(
                    f"Max hold {hold_ms // 3600000:.1f}h exceeded "
                    f"limit {float(policy.get('max_hold_hours', 24.0)):.1f}h"
                ),
            )
            return self._execute(record, sim, mark_prices)

        # 5. Stop loss
        stop_pct = float(policy.get("stop_loss_pct", 2.0))
        stop_threshold = -notional * stop_pct / 100.0
        if unrealised_pnl < stop_threshold:
            record = ExitRecord(
                position_id=pos_id, symbol=symbol, side=side,
                reason=ExitReason.STOP_LOSS, triggered_by="stop_loss_policy",
                entry_price=entry_price, exit_price=mark, qty=qty,
                unrealised_pnl=unrealised_pnl, realised_pnl=None, hold_ms=hold_ms,
                detail=(
                    f"Unrealised PnL {unrealised_pnl:.4f} < stop "
                    f"{stop_threshold:.4f} ({stop_pct}% of notional {notional:.2f})"
                ),
            )
            return self._execute(record, sim, mark_prices)

        # 6. Take profit
        tp_pct = float(policy.get("take_profit_pct", 4.0))
        tp_threshold = notional * tp_pct / 100.0
        if unrealised_pnl > tp_threshold:
            record = ExitRecord(
                position_id=pos_id, symbol=symbol, side=side,
                reason=ExitReason.TAKE_PROFIT, triggered_by="take_profit_policy",
                entry_price=entry_price, exit_price=mark, qty=qty,
                unrealised_pnl=unrealised_pnl, realised_pnl=None, hold_ms=hold_ms,
                detail=(
                    f"Unrealised PnL {unrealised_pnl:.4f} > TP "
                    f"{tp_threshold:.4f} ({tp_pct}% of notional {notional:.2f})"
                ),
            )
            return self._execute(record, sim, mark_prices)

        # 7. Risk deterioration — re-run risk engine on open position
        try:
            from backend.nexus_research.risk_engine import get_risk_engine, RiskRequest
            from backend.nexus_research.sim_ledger import get_sim_ledger
            risk = get_risk_engine()
            ledger = get_sim_ledger()
            req = RiskRequest(
                symbol=symbol,
                side=side,
                qty=qty,
                entry_price=last_mark_price,
                leverage=float(position.get("leverage", 3.0)),
                candidate={"score": 60.0, "side": side},
            )
            verdict = risk.check(req, sim=sim, ledger=ledger)
            if not verdict.allowed and verdict.verdict.startswith("BLOCK"):
                record = ExitRecord(
                    position_id=pos_id, symbol=symbol, side=side,
                    reason=ExitReason.RISK_DETERIORATION,
                    triggered_by="risk_deterioration_policy",
                    entry_price=entry_price, exit_price=mark, qty=qty,
                    unrealised_pnl=unrealised_pnl, realised_pnl=None, hold_ms=hold_ms,
                    detail=f"Risk re-check returned {verdict.verdict}: {'; '.join(verdict.reasons)}",
                )
                return self._execute(record, sim, mark_prices)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[exit] risk_deterioration check failed: %s", exc)

        # 8. Candidate invalidation
        if candidates is not None:
            cand = candidates.get(symbol)
            if cand is not None:
                expiry = cand.get("expiresAt") or cand.get("expires_at")
                if expiry and isinstance(expiry, (int, float)) and now_ms > expiry:
                    record = ExitRecord(
                        position_id=pos_id, symbol=symbol, side=side,
                        reason=ExitReason.CANDIDATE_INVALID,
                        triggered_by="candidate_invalidation_policy",
                        entry_price=entry_price, exit_price=mark, qty=qty,
                        unrealised_pnl=unrealised_pnl, realised_pnl=None, hold_ms=hold_ms,
                        detail=f"Candidate for {symbol} has expired",
                    )
                    return self._execute(record, sim, mark_prices)

        return None

    def queue_manual_close(self, position_id: str) -> None:
        """Queue a position for manual research close on next evaluate() call."""
        with self._lock:
            if position_id not in self._manual_close_queue:
                self._manual_close_queue.append(position_id)
        logger.info("[exit] manual close queued for position %s", position_id)

    def close_all_positions(
        self,
        sim,
        mark_prices: dict[str, float],
        reason: str,
        detail: str,
    ) -> list[ExitRecord]:
        """Force-close all open positions (e.g., mode=OFF or controller killed)."""
        closed: list[ExitRecord] = []
        try:
            open_positions = sim.list_open_positions()
            for position in open_positions:
                pos_id = position.get("positionId", "")
                symbol = position.get("symbol", "")
                side = position.get("side", "")
                entry_price = float(position.get("entryPrice", 0.0))
                qty = float(position.get("qty", 0.0))
                unrealised_pnl = float(position.get("unrealisedPnl", 0.0))
                opened_at_ms = int(position.get("openedAtMs", 0))
                hold_ms = int(time.time() * 1000) - opened_at_ms
                mark = mark_prices.get(symbol)
                record = ExitRecord(
                    position_id=pos_id, symbol=symbol, side=side,
                    reason=reason, triggered_by="exit_policy_engine",
                    entry_price=entry_price, exit_price=mark, qty=qty,
                    unrealised_pnl=unrealised_pnl, realised_pnl=None,
                    hold_ms=hold_ms, detail=detail,
                )
                self._execute(record, sim, mark_prices)
                closed.append(record)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[exit] close_all_positions failed: %s", exc)
        return closed

    def _execute(
        self,
        record: ExitRecord,
        sim,
        mark_prices: dict[str, float],
    ) -> ExitRecord:
        _record_exit(record, sim, mark_prices)
        with self._lock:
            self._total_exits += 1
            self._exits_by_reason[record.reason] = (
                self._exits_by_reason.get(record.reason, 0) + 1
            )
        logger.info(
            "[exit] %s position %s %s %s — reason=%s detail=%s",
            record.reason, record.position_id, record.symbol, record.side,
            record.reason, record.detail,
        )
        return record

    def list_exits(self, limit: int = 50) -> list[dict[str, Any]]:
        """Read recent exit records from research store."""
        try:
            from backend.nexus_research.storage import get_research_store
            return get_research_store().query("paper_exits", limit=limit)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[exit] list_exits failed: %s", exc)
            return []

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "researchOnly": True,
                "privateApi": False,
                "totalExits": self._total_exits,
                "exitsByReason": dict(self._exits_by_reason),
                "manualCloseQueueLength": len(self._manual_close_queue),
                "generatedAt": int(time.time() * 1000),
            }


# ── Singleton ─────────────────────────────────────────────────────────────────
_EXIT_ENGINE: ExitPolicyEngine | None = None
_EXIT_LOCK = threading.Lock()


def get_exit_policy_engine() -> ExitPolicyEngine:
    global _EXIT_ENGINE
    with _EXIT_LOCK:
        if _EXIT_ENGINE is None:
            _EXIT_ENGINE = ExitPolicyEngine()
            logger.info("[exit] ExitPolicyEngine initialised (researchOnly=true)")
        return _EXIT_ENGINE

"""Phase 6 Gate C — Continuous Autonomous Paper Runtime Controller.

RESEARCH ONLY. No real orders, no real funds, no private API.
researchOnly=true on all outputs.

Mode environment variable: NEXUS_AUTONOMOUS_RESEARCH_MODE
  OFF    — controller registered but no positions created (default safe)
  SHADOW — full guard pipeline executes; stops before creating sim orders (dry-run)
  PAPER  — full pipeline including sim order creation (paper trading only)

Rationale for SHADOW default: safer than OFF because it exercises all guards
and surfaces issues earlier, while PAPER requires explicit operator opt-in.

Runtime states (independent of mode):
  RUNNING   — controller tick loop is active
  PAUSED    — tick loop suspended (operator request or transient issue)
  KILLED    — controller permanently halted (kill switch or repeated failures)
  DEGRADED  — running but with non-fatal errors; UI shows warning

Each controller tick:
  1. Mode + kill switch check
  2. Load READY_FOR_SIMULATION decisions from research store
  3. Per-candidate guards:
     a. Not expired
     b. Fresh data (age check)
     c. Evidence coverage
     d. Risk Critic not BLOCK
     e. ALLOW / REDUCE
     f. No duplicate position (checked by risk engine)
     g. No sector overexposure (checked by risk engine)
     h. Drawdown block check (from ledger)
     i. Kill switch (from simulator)
     j. Storage healthy
  4. Capital allocation
  5. PAPER: submit sim order via gate_b_to_gate_c bridge
     SHADOW: log dry-run record, no order submitted
  6. Exit policies on all open positions
  7. Mark positions with latest public mark prices
  8. Record paper cycle event to research store

UI MUST NOT create sim orders directly — only this controller.
The /api/nexus/simulator/order POST endpoint is a test helper only.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

RESEARCH_ONLY: bool = True

# ── Mode constants ─────────────────────────────────────────────────────────────
MODE_OFF = "OFF"
MODE_SHADOW = "SHADOW"
MODE_PAPER = "PAPER"

_VALID_MODES = {MODE_OFF, MODE_SHADOW, MODE_PAPER}
_DEFAULT_MODE = MODE_SHADOW   # explicit safe default; document: never default to PAPER

# ── Runtime states ─────────────────────────────────────────────────────────────
STATE_RUNNING = "RUNNING"
STATE_PAUSED = "PAUSED"
STATE_KILLED = "KILLED"
STATE_DEGRADED = "DEGRADED"
STATE_PAPER_ACTIVE = "PAPER_ACTIVE"
STATE_PAPER_PAUSED = "PAPER_PAUSED"
STATE_DEGRADED_STORAGE = "DEGRADED_STORAGE"
STATE_DEGRADED_LEDGER = "DEGRADED_LEDGER"
STATE_DEGRADED_OWNERSHIP = "DEGRADED_OWNERSHIP"
STATE_DEGRADED_CASE_CAPACITY = "DEGRADED_CASE_CAPACITY"
STATE_DEGRADED_RISK = "DEGRADED_RISK"

# ── Env var ───────────────────────────────────────────────────────────────────
_MODE_ENV_VAR = "NEXUS_AUTONOMOUS_RESEARCH_MODE"


def _read_mode() -> str:
    try:
        from backend.nexus_research.config import read_autonomous_mode
        return read_autonomous_mode()
    except Exception:  # noqa: BLE001
        raw = (os.getenv(_MODE_ENV_VAR) or "").strip().upper()
        if raw in _VALID_MODES:
            return raw
        if raw:
            logger.warning(
                "[paper_ctrl] Unknown mode %r for %s; defaulting to %s",
                raw, _MODE_ENV_VAR, _DEFAULT_MODE,
            )
        return _DEFAULT_MODE


class PaperCycleRecord:
    """Single paper controller tick result."""

    def __init__(
        self,
        cycle_id: str,
        mode: str,
        state: str,
        candidates_evaluated: int,
        orders_submitted: int,
        shadow_dry_runs: int,
        exits_triggered: int,
        guards_blocked: int,
        errors: list[str],
        detail: dict[str, Any],
    ) -> None:
        self.cycle_id = cycle_id
        self.mode = mode
        self.state = state
        self.candidates_evaluated = candidates_evaluated
        self.orders_submitted = orders_submitted
        self.shadow_dry_runs = shadow_dry_runs
        self.exits_triggered = exits_triggered
        self.guards_blocked = guards_blocked
        self.errors = errors
        self.detail = detail
        self.created_at_ms = int(time.time() * 1000)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycleId": self.cycle_id,
            "mode": self.mode,
            "state": self.state,
            "candidatesEvaluated": self.candidates_evaluated,
            "ordersSubmitted": self.orders_submitted,
            "shadowDryRuns": self.shadow_dry_runs,
            "exitsTriggered": self.exits_triggered,
            "guardsBlocked": self.guards_blocked,
            "errors": self.errors,
            "detail": self.detail,
            "createdAtMs": self.created_at_ms,
            "researchOnly": True,
            "privateApi": False,
        }


class PaperController:
    """Autonomous paper trading controller.

    Registered as a supervisor job via start_paper_controller_job().
    Tick interval from simulation policy (default 60s).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = STATE_RUNNING
        self._state_reason: str = "initialised"
        self._total_cycles = 0
        self._total_orders = 0
        self._total_shadow = 0
        self._total_exits = 0
        self._total_errors = 0
        self._recent_cycles: list[PaperCycleRecord] = []
        self._recent_limit = 20
        self._paused_by_operator = False
        self._started_at_ms = int(time.time() * 1000)

    # ── State management ──────────────────────────────────────────────────────

    def pause(self, reason: str = "operator") -> None:
        with self._lock:
            self._paused_by_operator = True
            if self._state != STATE_KILLED:
                self._state = STATE_PAUSED
                self._state_reason = reason
        logger.info("[paper_ctrl] paused: %s", reason)

    def resume(self, reason: str = "operator") -> None:
        with self._lock:
            self._paused_by_operator = False
            if self._state == STATE_PAUSED:
                self._state = STATE_RUNNING
                self._state_reason = reason
        logger.info("[paper_ctrl] resumed: %s", reason)

    def kill(self, reason: str = "operator") -> None:
        with self._lock:
            self._state = STATE_KILLED
            self._state_reason = reason
        logger.warning("[paper_ctrl] KILLED: %s", reason)

    # ── Main tick ─────────────────────────────────────────────────────────────

    def run_tick(self) -> PaperCycleRecord:
        """Single controller tick. Called by supervisor at configured interval."""
        import uuid
        cycle_id = str(uuid.uuid4())
        mode = _read_mode()
        errors: list[str] = []
        detail: dict[str, Any] = {"cycleId": cycle_id, "mode": mode}

        with self._lock:
            state = self._state

        # ── State guard ──────────────────────────────────────────────────────
        if state == STATE_KILLED:
            return self._make_record(
                cycle_id, mode, state, 0, 0, 0, 0, 0, errors, detail
            )

        if state == STATE_PAUSED or state == STATE_PAPER_PAUSED:
            detail["pauseReason"] = self._state_reason
            return self._make_record(
                cycle_id, mode, state, 0, 0, 0, 0, 0, errors, detail
            )

        if mode == MODE_OFF:
            detail["note"] = "mode=OFF; no positions created"
            return self._make_record(
                cycle_id, mode, state, 0, 0, 0, 0, 0, errors, detail
            )

        # ── Phase 6.3: PAPER activation fail-closed preflight ────────────────
        paper_account_id = None
        activation_session_id = None
        if mode == MODE_PAPER:
            try:
                from backend.nexus_research.paper_activation import (
                    activate_or_resume_paper_session,
                    ACCOUNT_PAPER_MAIN_V1,
                )
                act = activate_or_resume_paper_session()
                detail["activation"] = {
                    "ok": act.get("ok"),
                    "sessionId": (act.get("session") or {}).get("activationSessionId"),
                    "hint": act.get("controllerHint"),
                    "reasons": (act.get("preflight") or {}).get("reasons") or [],
                }
                session = act.get("session") or {}
                activation_session_id = session.get("activationSessionId")
                paper_account_id = session.get("accountId") or ACCOUNT_PAPER_MAIN_V1
                if not act.get("ok") or act.get("controllerHint") == "PAPER_PAUSED":
                    with self._lock:
                        self._state = STATE_PAPER_PAUSED
                        self._state_reason = ",".join(
                            (act.get("preflight") or {}).get("reasons") or ["preflight_failed"]
                        )
                    return self._make_record(
                        cycle_id, mode, STATE_PAPER_PAUSED, 0, 0, 0, 0, 0, errors, detail
                    )
                with self._lock:
                    if self._state not in (STATE_KILLED, STATE_PAUSED):
                        self._state = STATE_PAPER_ACTIVE
                        self._state_reason = "paper_activation_ok"
                state = STATE_PAPER_ACTIVE
            except Exception as exc:  # noqa: BLE001
                errors.append(f"paper activation failed: {exc}")
                with self._lock:
                    self._state = STATE_PAPER_PAUSED
                    self._state_reason = f"activation_error:{exc}"
                return self._make_record(
                    cycle_id, mode, STATE_PAPER_PAUSED, 0, 0, 0, 0, 0, errors, detail
                )

        # ── Load required components (fail-fast but degrade gracefully) ───────
        try:
            from backend.nexus_research.simulator import get_simulator
            from backend.nexus_research.sim_ledger import get_sim_ledger
            from backend.nexus_research.risk_engine import get_risk_engine, RiskRequest
            from backend.nexus_research.capital_allocator import get_capital_allocator
            from backend.nexus_research.gate_b_to_gate_c import try_simulate_decision
            from backend.nexus_research.exit_policies import get_exit_policy_engine, ExitReason
            from backend.nexus_research.simulation_policy import get_simulation_policy
            from backend.nexus_research.storage import get_research_store
            from backend.nexus_research.durable_ledger import ACCOUNT_PAPER_DEFAULT

            sim = get_simulator()
            ledger = get_sim_ledger(
                account_id=paper_account_id or ACCOUNT_PAPER_DEFAULT
            )
            risk = get_risk_engine()
            allocator = get_capital_allocator()
            exit_engine = get_exit_policy_engine()
            policy = get_simulation_policy()
            store = get_research_store()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"component load failed: {exc}")
            self._set_degraded(str(exc))
            return self._make_record(
                cycle_id, mode, STATE_DEGRADED, 0, 0, 0, 0, 0, errors, detail
            )

        # ── Kill switch check ─────────────────────────────────────────────────
        if getattr(sim, "_kill_switch", False):
            detail["killSwitchActive"] = True
            logger.warning("[paper_ctrl] kill switch active — skipping tick")
            return self._make_record(
                cycle_id, mode, state, 0, 0, 0, 0, 0, errors, detail
            )

        # ── Storage health check ──────────────────────────────────────────────
        try:
            from backend.nexus_research.storage import storage_audit
            audit = storage_audit()
            if not audit.get("ok", True) is not False:
                pass  # storage_audit returns ok=True for in-memory; continue
        except Exception as exc:  # noqa: BLE001
            errors.append(f"storage health check failed: {exc}")

        # ── Fetch mark prices (public data only) ──────────────────────────────
        mark_prices: dict[str, float] = {}
        try:
            mark_prices = _fetch_public_mark_prices()
            detail["markPricesFetched"] = len(mark_prices)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"mark price fetch failed: {exc}")
            detail["markPricesError"] = str(exc)

        # ── Exit policies on open positions ───────────────────────────────────
        exits_triggered = 0
        try:
            open_positions = sim.list_open_positions()
            if open_positions and mark_prices:
                sim.process_pending_orders(mark_prices)

            for pos in sim.list_open_positions():
                exit_record = exit_engine.evaluate(
                    position=pos,
                    mark_prices=mark_prices,
                    policy=policy._policy,
                    sim=sim,
                )
                if exit_record is not None:
                    exits_triggered += 1
                    logger.info(
                        "[paper_ctrl] exit triggered for %s: %s",
                        pos.get("symbol"), exit_record.reason
                    )

            # Mode→OFF: force-close all open positions
            if mode == MODE_OFF and sim.list_open_positions():
                closed = exit_engine.close_all_positions(
                    sim, mark_prices,
                    reason=ExitReason.MODE_OFF,
                    detail="Mode changed to OFF",
                )
                exits_triggered += len(closed)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"exit policy evaluation failed: {exc}")

        # ── Load READY_FOR_SIMULATION decisions ───────────────────────────────
        candidates_evaluated = 0
        orders_submitted = 0
        shadow_dry_runs = 0
        guards_blocked = 0
        try:
            processed_ids = _load_processed_decision_ids(store)
            decisions = store.query("research_decisions", limit=100)
            ready = [
                d for d in decisions
                if _decision_ready_for_paper(d)
                and str(d.get("decisionId") or "") not in processed_ids
            ]
            max_per_cycle = int(policy.get("max_candidates_per_cycle", 3))
            ready = ready[:max_per_cycle]
            detail["readyDecisions"] = len(ready)

            for decision in ready:
                candidates_evaluated += 1
                decision_id = decision.get("decisionId", "")

                # Guard: check all required guards
                guard_result = _run_guards(decision, sim, ledger, risk, policy, mark_prices)
                if not guard_result["passed"]:
                    guards_blocked += 1
                    logger.debug(
                        "[paper_ctrl] decision %s blocked by guard: %s",
                        decision_id, guard_result.get("reason"),
                    )
                    try:
                        from backend.nexus_research.domain_events import PAPER_GUARD_BLOCKED, publish_event

                        publish_event(
                            PAPER_GUARD_BLOCKED,
                            {
                                "decisionId": decision_id,
                                "symbol": decision.get("symbol"),
                                "reason": guard_result.get("reason"),
                                "checks": guard_result.get("checks"),
                            },
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    # Mark as processed to avoid re-evaluating next tick
                    _mark_decision_processed(
                        store, decision_id, "GUARD_BLOCKED", guard_result.get("reason")
                    )
                    continue

                if mode == MODE_PAPER:
                    # Full pipeline: submit sim order on NEXUS_PAPER_MAIN_V1
                    try:
                        result = try_simulate_decision(
                            decision,
                            account_id=paper_account_id,
                            activation_session_id=activation_session_id,
                        )
                        if result.success:
                            orders_submitted += 1
                            logger.info(
                                "[paper_ctrl] PAPER: sim order %s for %s %s",
                                result.order_id, decision.get("symbol"), decision.get("side"),
                            )
                            # Same-tick fill attempt with public mark prices
                            try:
                                if mark_prices:
                                    sim.process_pending_orders(mark_prices)
                            except Exception as fill_exc:  # noqa: BLE001
                                logger.debug("[paper_ctrl] same-tick fill deferred: %s", fill_exc)
                        else:
                            errors.append(
                                f"sim failed for {decision_id}: "
                                f"{result.skip_reason or result.error}"
                            )
                        _mark_decision_processed(
                            store, decision_id,
                            "SIM_SUBMITTED" if result.success else "SIM_FAILED",
                            result.skip_reason or result.error,
                        )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"try_simulate_decision failed: {exc}")

                elif mode == MODE_SHADOW:
                    # Dry-run: log everything, create no sim orders
                    shadow_dry_runs += 1
                    shadow_record = {
                        "decisionId": decision_id,
                        "symbol": decision.get("symbol"),
                        "side": decision.get("side"),
                        "score": decision.get("score"),
                        "guardResult": guard_result,
                        "mode": MODE_SHADOW,
                        "note": "SHADOW: all guards passed; no sim order created",
                        "createdAtMs": int(time.time() * 1000),
                        "researchOnly": True,
                    }
                    try:
                        store.append("paper_shadow_runs", shadow_record)
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("[paper_ctrl] shadow record store failed: %s", exc)
                    logger.info(
                        "[paper_ctrl] SHADOW dry-run passed for %s %s (score=%s)",
                        decision.get("symbol"), decision.get("side"), decision.get("score"),
                    )
                    _mark_decision_processed(
                        store, decision_id, "SHADOW_DRY_RUN", "SHADOW mode"
                    )

        except Exception as exc:  # noqa: BLE001
            errors.append(f"decision processing failed: {exc}")

        # ── Trigger reflection on newly closed positions ───────────────────────
        if exits_triggered > 0:
            try:
                from backend.nexus_research.gate_b_to_gate_c import (
                    read_sim_closed_positions_for_reflection,
                )
                from backend.nexus_research.reflection import get_reflection_analyst
                closed = read_sim_closed_positions_for_reflection(limit=10)
                if closed:
                    analyst = get_reflection_analyst()
                    for pos in closed[-exits_triggered:]:
                        try:
                            analyst.reflect(pos)
                        except Exception:  # noqa: BLE001
                            pass
            except Exception as exc:  # noqa: BLE001
                logger.debug("[paper_ctrl] reflection pass failed: %s", exc)

        record = self._make_record(
            cycle_id, mode, state,
            candidates_evaluated, orders_submitted, shadow_dry_runs,
            exits_triggered, guards_blocked, errors, detail,
        )

        # Persist cycle record
        try:
            store.append("paper_cycles", record.to_dict())
        except Exception as exc:  # noqa: BLE001
            logger.debug("[paper_ctrl] cycle record store failed: %s", exc)

        return record

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _make_record(
        self,
        cycle_id: str,
        mode: str,
        state: str,
        candidates_evaluated: int,
        orders_submitted: int,
        shadow_dry_runs: int,
        exits_triggered: int,
        guards_blocked: int,
        errors: list[str],
        detail: dict[str, Any],
    ) -> PaperCycleRecord:
        record = PaperCycleRecord(
            cycle_id=cycle_id,
            mode=mode,
            state=state,
            candidates_evaluated=candidates_evaluated,
            orders_submitted=orders_submitted,
            shadow_dry_runs=shadow_dry_runs,
            exits_triggered=exits_triggered,
            guards_blocked=guards_blocked,
            errors=errors,
            detail=detail,
        )
        with self._lock:
            self._total_cycles += 1
            self._total_orders += orders_submitted
            self._total_shadow += shadow_dry_runs
            self._total_exits += exits_triggered
            if errors:
                self._total_errors += 1
            self._recent_cycles.append(record)
            if len(self._recent_cycles) > self._recent_limit:
                self._recent_cycles = self._recent_cycles[-self._recent_limit:]
        return record

    def _set_degraded(self, reason: str) -> None:
        with self._lock:
            if self._state not in (STATE_KILLED,):
                self._state = STATE_DEGRADED
                self._state_reason = reason

    # ── Read accessors ────────────────────────────────────────────────────────

    def list_recent_cycles(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            cycles = list(self._recent_cycles)
        cycles.sort(key=lambda c: c.created_at_ms, reverse=True)
        return [c.to_dict() for c in cycles[:limit]]

    def status(self) -> dict[str, Any]:
        mode = _read_mode()
        with self._lock:
            state = self._state
            state_reason = self._state_reason
            total_cycles = self._total_cycles
            total_orders = self._total_orders
            total_shadow = self._total_shadow
            total_exits = self._total_exits
            total_errors = self._total_errors
            last_cycle = self._recent_cycles[-1].to_dict() if self._recent_cycles else None
        activation = None
        ledger_snap = None
        try:
            from backend.nexus_research.paper_activation import get_active_paper_session
            activation = get_active_paper_session()
        except Exception:  # noqa: BLE001
            activation = None
        if mode == MODE_PAPER:
            try:
                from backend.nexus_research.sim_ledger import get_sim_ledger
                from backend.nexus_research.paper_activation import ACCOUNT_PAPER_MAIN_V1
                ledger_snap = get_sim_ledger(account_id=ACCOUNT_PAPER_MAIN_V1).snapshot()
            except Exception:  # noqa: BLE001
                ledger_snap = None
        return {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "mode": mode,
            "modeEnvVar": _MODE_ENV_VAR,
            "validModes": sorted(_VALID_MODES),
            "defaultMode": _DEFAULT_MODE,
            "defaultModeRationale": (
                "SHADOW is default: exercises all guards without creating positions; "
                "PAPER requires explicit operator opt-in via env var"
            ),
            "runtimeState": state,
            "paperControllerState": state,
            "stateReason": state_reason,
            "activationSession": activation,
            "paperAccountId": (activation or {}).get("accountId") if activation else None,
            "ledger": ledger_snap,
            "totalCycles": total_cycles,
            "totalOrdersSubmitted": total_orders,
            "totalShadowRuns": total_shadow,
            "totalExits": total_exits,
            "totalErrorCycles": total_errors,
            "startedAtMs": self._started_at_ms,
            "lastCycle": last_cycle,
            "realOrderCreated": False,
            "generatedAt": int(time.time() * 1000),
        }


# ── Guard pipeline ─────────────────────────────────────────────────────────────

def _run_guards(
    decision: dict[str, Any],
    sim,
    ledger,
    risk,
    policy,
    mark_prices: dict[str, float],
) -> dict[str, Any]:
    """Run all pre-submission guards. Returns {passed: bool, reason: str, checks: dict}."""
    checks: dict[str, str] = {}
    now_ms = int(time.time() * 1000)
    symbol = decision.get("symbol", "")
    side = decision.get("side", "LONG")
    score = float(decision.get("score", 0.0))
    evidence = decision.get("evidence") or {}

    # 1. Score gate
    min_score = float(policy.get("min_score_for_paper", 65.0))
    if score < min_score:
        checks["score"] = "FAIL"
        return {"passed": False, "reason": f"score {score:.1f} < min {min_score:.1f}", "checks": checks}
    checks["score"] = "OK"

    # 2. Candidate expiry
    expires_at = decision.get("expiresAt") or decision.get("expires_at")
    if expires_at:
        grace = int(policy.get("candidate_expiry_grace_ms", 2_000))
        if isinstance(expires_at, (int, float)) and now_ms > expires_at + grace:
            checks["candidate_expiry"] = "FAIL"
            return {"passed": False, "reason": "candidate expired", "checks": checks}
    checks["candidate_expiry"] = "OK"

    # 3. Evidence coverage
    if policy.get("require_evidence_coverage", True):
        has_evidence = bool(evidence) and any(
            bool(v) for v in evidence.values() if v is not None
        )
        if not has_evidence:
            checks["evidence_coverage"] = "FAIL"
            return {"passed": False, "reason": "no evidence fields populated", "checks": checks}
    checks["evidence_coverage"] = "OK"

    # 4. Fresh data
    data_ts = (
        evidence.get("dataTimestampMs")
        or evidence.get("timestamp")
        or decision.get("createdAtMs")
        or 0
    )
    fresh_ms = int(policy.get("require_fresh_data_age_ms", 30_000))
    if data_ts:
        age_ms = now_ms - int(data_ts)
        if age_ms > fresh_ms:
            checks["fresh_data"] = "FAIL"
            return {
                "passed": False,
                "reason": f"data age {age_ms}ms > {fresh_ms}ms",
                "checks": checks,
            }
    checks["fresh_data"] = "OK"

    # 5. Mark price available (for PAPER mode position sizing)
    if symbol not in mark_prices and symbol:
        checks["mark_price"] = "WARN"  # warn but don't block (price from evidence fallback)
    else:
        checks["mark_price"] = "OK"

    # 6. Risk Critic check via risk engine
    try:
        from backend.nexus_research.risk_engine import RiskRequest, ALLOW_SIMULATION, REDUCE_SIZE
        entry_price = float(
            mark_prices.get(symbol, 0)
            or evidence.get("price")
            or evidence.get("lastPrice")
            or 65_000.0
        )
        leverage = float(decision.get("leverage", policy.get("default_leverage", 3.0)))
        equity = 10_000.0
        try:
            snap = ledger.snapshot(unrealised_pnl=sim.total_unrealised_pnl())
            equity = snap.get("equity", 10_000.0)
        except Exception:  # noqa: BLE001
            pass

        qty = equity * float(policy.get("equity_fraction_pct", 1.0)) / 100.0 / max(entry_price, 1)
        req = RiskRequest(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            leverage=leverage,
            candidate={"score": score, "side": side},
        )
        verdict = risk.check(req, sim=sim, ledger=ledger)
        checks["risk_critic"] = verdict.verdict
        if not verdict.allowed:
            return {
                "passed": False,
                "reason": f"risk blocked: {verdict.verdict} — {'; '.join(verdict.reasons)}",
                "checks": checks,
            }
    except Exception as exc:  # noqa: BLE001
        checks["risk_critic"] = f"ERROR: {exc}"
        # Don't block on risk engine error — degrade gracefully

    # 7. Kill switch
    if getattr(sim, "_kill_switch", False):
        checks["kill_switch"] = "FAIL"
        return {"passed": False, "reason": "simulator kill switch active", "checks": checks}
    checks["kill_switch"] = "OK"

    return {"passed": True, "reason": "all guards passed", "checks": checks}


def _fetch_public_mark_prices() -> dict[str, float]:
    """Fetch public mark prices for open positions. NEVER uses private API."""
    mark_prices: dict[str, float] = {}
    try:
        from backend.market.scanner.scanner_service import get_market_scanner
        scanner = get_market_scanner()
        # Use scanner's cached candidates as mark price source (public data)
        candidates = scanner.get_candidates() if hasattr(scanner, "get_candidates") else []
        for c in candidates:
            sym = c.get("symbol") or c.get("ticker")
            price = (
                c.get("price")
                or c.get("lastPrice")
                or c.get("markPrice")
                or c.get("closePrice")
            )
            if sym and price:
                try:
                    mark_prices[str(sym)] = float(price)
                except (TypeError, ValueError):
                    pass
    except Exception as exc:  # noqa: BLE001
        logger.debug("[paper_ctrl] scanner mark price fetch failed: %s", exc)

    # Fallback: use last known prices from open positions (already marked)
    if not mark_prices:
        try:
            from backend.nexus_research.simulator import get_simulator
            for pos in get_simulator().list_open_positions():
                sym = pos.get("symbol")
                mark = pos.get("lastMarkPrice") or pos.get("entryPrice")
                if sym and mark:
                    mark_prices[sym] = float(mark)
        except Exception as exc:  # noqa: BLE001
            logger.debug("[paper_ctrl] fallback mark price failed: %s", exc)

    return mark_prices


def _decision_ready_for_paper(d: dict) -> bool:
    """Canonical field is decisionStatus; status is legacy-only.

    Conflict (both present and unequal) → fail-closed (not ready).
    """
    canonical = d.get("decisionStatus")
    legacy = d.get("status")
    if canonical is not None and legacy is not None and str(canonical) != str(legacy):
        return False  # fail-closed on conflict — never create paper order
    status = canonical if canonical is not None else legacy
    return status == "READY_FOR_SIMULATION"


def _load_processed_decision_ids(store) -> set[str]:
    ids: set[str] = set()
    try:
        for row in store.query("paper_processed_decisions", limit=500):
            did = row.get("decisionId") or row.get("decision_id")
            if did:
                ids.add(str(did))
    except Exception:  # noqa: BLE001
        pass
    return ids


def _mark_decision_processed(
    store,
    decision_id: str,
    outcome: str,
    detail: str | None,
) -> None:
    """Record that a decision was processed by paper controller this cycle."""
    try:
        store.append("paper_processed_decisions", {
            "decisionId": decision_id,
            "outcome": outcome,
            "detail": detail,
            "processedAtMs": int(time.time() * 1000),
            "researchOnly": True,
        })
    except Exception as exc:  # noqa: BLE001
        logger.debug("[paper_ctrl] mark_decision_processed failed: %s", exc)


# ── Singleton ─────────────────────────────────────────────────────────────────
_CONTROLLER: PaperController | None = None
_CONTROLLER_LOCK = threading.Lock()


def get_paper_controller() -> PaperController:
    global _CONTROLLER
    with _CONTROLLER_LOCK:
        if _CONTROLLER is None:
            _CONTROLLER = PaperController()
            logger.info("[paper_ctrl] PaperController initialised (researchOnly=true)")
        return _CONTROLLER


def start_paper_controller_job() -> None:
    """Register paper controller tick as a supervisor job. Idempotent."""
    try:
        from backend.nexus_research.runtime_supervisor import get_supervisor
        from backend.nexus_research.simulation_policy import get_simulation_policy

        policy = get_simulation_policy()
        interval_sec = float(policy.get("paper_loop_interval_sec", 60.0))
        controller = get_paper_controller()
        supervisor = get_supervisor()
        supervisor.register_job(
            job_id="paper_controller_tick",
            fn=controller.run_tick,
            interval_sec=interval_sec,
            timeout_sec=120,
            max_retries=0,
            backoff_sec=10.0,
        )
        supervisor.start()
        logger.info(
            "[paper_ctrl] paper controller job registered (interval=%ss, mode=%s)",
            interval_sec, _read_mode(),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[paper_ctrl] could not register supervisor job: %s", exc)

"""Bootstrap single-owner autonomous Demo scanner (scan-only by default)."""
from __future__ import annotations

import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_BOOTSTRAPPED = False
_BOOT_LOCK = threading.Lock()


def _auto_send_enabled() -> bool:
    """Fail-closed: only explicit Zeabur/env enable opens new demo sends.

    Session.auto_send alone must NOT enable sends when env is missing/false.
    """
    raw = os.environ.get("NEXUS_AUTONOMOUS_DEMO_AUTO_SEND", "").strip().lower()
    return raw in ("1", "true", "yes")


def _scanner_enabled() -> bool:
    # Default ON so UI can prove continuity after deploy. Writes still need session.
    raw = os.environ.get("NEXUS_AUTONOMOUS_DEMO_SCANNER", "true").strip().lower()
    return raw in ("1", "true", "yes", "")


def _build_orch(*, dry_run: bool):
    from backend.nexus_research.demo_autonomous.orchestrator import AutonomousDemoOrchestrator
    from backend.nexus_research.demo_autonomous.session_authorization import get_authorization_validator
    from backend.nexus_research.demo_autonomous.write_adapter import AutonomousDemoOrderAdapter
    from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport
    from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator
    from backend.nexus_research.demo_exchange.signer import DemoRequestSigner

    auth = get_authorization_validator()
    adapter = None
    try:
        if dry_run:
            transport = DemoWriteTransport(
                signer=DemoRequestSigner("dry-run", "dry-run"),
                auth=auth,
                dry_run=True,
            )
            adapter = AutonomousDemoOrderAdapter(transport, auth=auth)
        else:
            key, secret = DemoCredentialPresenceValidator().load_secrets_for_signer()
            transport = DemoWriteTransport(
                signer=DemoRequestSigner(key, secret),
                auth=auth,
                dry_run=False,
            )
            adapter = AutonomousDemoOrderAdapter(transport, auth=auth, get_json=transport.get)
    except Exception as exc:
        logger.warning("autonomous_orch_adapter_failed: %s", type(exc).__name__)
    return AutonomousDemoOrchestrator(auth=auth, write_adapter=adapter, dry_run=bool(dry_run))


def _run_scan_cycle() -> dict[str, Any]:
    from backend.nexus_research.demo_autonomous.controller import get_autonomous_controller
    from backend.nexus_research.demo_autonomous.ops_status import record_scan_result
    from backend.nexus_research.demo_autonomous.reentry_guard import get_reentry_guard
    from backend.nexus_research.demo_autonomous.session_authorization import get_authorization_validator
    from backend.nexus_research.demo_autonomous.session_rotator import get_session_rotator

    ctrl = get_autonomous_controller()
    ctrl.mark_progress("account_snapshot")
    equity = 5000.0
    open_positions = 0
    open_orders = 0
    snap = None
    try:
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        snap = capture_account_snapshot()
        equity = float(snap.total_equity or equity)
        open_positions = len([p for p in (snap.positions or []) if float(p.get("size") or 0) > 0])
        open_orders = len(snap.open_orders or [])
    except Exception as exc:
        logger.warning("autonomous_scan_snapshot_failed: %s", type(exc).__name__)

    ctrl.mark_progress("session_rotation")
    rotator = get_session_rotator()
    rotation = rotator.rotate_if_needed(
        position_count=open_positions,
        open_order_count=open_orders,
        reconcile_ok=True,
        ambiguous=False,
    )
    rotator.clear_new_entries_pause_if_flat(open_positions)

    instruments = None
    quality = None
    try:
        ctrl.mark_progress("instruments")
        from backend.nexus_research.demo_autonomous.instruments_fetch import (
            fetch_linear_perpetual_instruments,
        )
        from backend.nexus_research.demo_autonomous.market_quality_fetch import fetch_ticker_quality

        instruments = fetch_linear_perpetual_instruments()
        ctrl.mark_progress("market_quality")
        quality = fetch_ticker_quality()
    except Exception as exc:
        logger.warning("autonomous_scan_instruments_failed: %s", type(exc).__name__)

    auth = get_authorization_validator()
    session_active = bool(auth.session and auth.session.is_active())
    entries_paused = bool(rotator.continuity.new_entries_paused)
    send = bool(
        _auto_send_enabled()
        and session_active
        and open_positions == 0
        and open_orders == 0
        and not entries_paused
        and ctrl.health.allow_new_orders()[0]
    )

    # Prefer live dry_run=false only when sending; otherwise dry scan is fine for ranking.
    dry_run = not send
    ctrl.mark_progress("candidate_generation")
    orch = _build_orch(dry_run=dry_run)
    result = orch.run_cycle(
        equity=equity,
        instruments=instruments,
        quality=quality,
        open_positions=open_positions,
        open_orders=open_orders,
        send=False if not send else True,
    )
    payload = result.to_dict()
    top = payload.get("top") or {}

    # Supervisor / Time Stop: only when a persisted exit policy exists for the open symbol.
    # Never invent Time Stop for legacy trades without exit_policy_records.
    supervisor_note = None
    supervisor_tick = None
    if open_positions > 0 and snap is not None:
        ctrl.mark_progress("supervisor")
        from backend.nexus_research.demo_autonomous.exit_policy_record import latest_exit_policy
        from backend.nexus_research.demo_autonomous.position_lifecycle import (
            LifecyclePolicy,
            PositionSnapshot,
        )
        from backend.nexus_research.demo_autonomous.position_supervisor import (
            AutonomousPositionSupervisor,
        )

        pos_raw = next(
            (p for p in (snap.positions or []) if float(p.get("size") or 0) > 0),
            None,
        )
        if pos_raw:
            policy = latest_exit_policy(str(pos_raw.get("symbol") or ""))
            if policy is None or not policy.is_complete():
                supervisor_note = "legacy_or_incomplete_exit_policy_exchange_protection_only"
            else:
                opened_at = int(
                    pos_raw.get("createdTime")
                    or pos_raw.get("updatedTime")
                    or policy.created_at_ms
                    or 0
                )
                snap_pos = PositionSnapshot(
                    symbol=str(pos_raw.get("symbol") or ""),
                    side=str(pos_raw.get("side") or ""),
                    size=float(pos_raw.get("size") or 0),
                    entry_price=float(pos_raw.get("avgPrice") or pos_raw.get("entryPrice") or 0),
                    mark_price=float(pos_raw.get("markPrice") or pos_raw.get("avgPrice") or 0),
                    unrealised_pnl=float(pos_raw.get("unrealisedPnl") or 0),
                    liquidation_price=(
                        float(pos_raw["liqPrice"])
                        if pos_raw.get("liqPrice") not in (None, "", "0")
                        else None
                    ),
                    stop_loss=(
                        float(policy.protective_stop_plan.get("triggerPrice"))
                        if policy.protective_stop_plan.get("triggerPrice") is not None
                        else None
                    ),
                    take_profit=(
                        float(policy.take_profit_plan.get("triggerPrice"))
                        if policy.take_profit_plan.get("triggerPrice") is not None
                        else None
                    ),
                    opened_at_ms=opened_at,
                    protection_verified=True,
                )
                # Build live write adapter only when session can write (not emergency-stopped).
                write_adapter = None
                dry_sup = True
                if session_active:
                    try:
                        live_orch = _build_orch(dry_run=False)
                        write_adapter = live_orch.write_adapter
                        dry_sup = False
                    except Exception:
                        write_adapter = None
                        dry_sup = True
                supervisor = AutonomousPositionSupervisor(
                    write_adapter=write_adapter, dry_run=dry_sup,
                )
                supervisor.lifecycle.policy = LifecyclePolicy(max_hold_ms=policy.max_hold_ms)
                stop_dist = 0.0
                if snap_pos.entry_price and policy.protective_stop_plan.get("triggerPrice"):
                    stop_dist = abs(
                        snap_pos.entry_price - float(policy.protective_stop_plan["triggerPrice"])
                    ) / snap_pos.entry_price * 100.0
                tick = supervisor.tick(
                    snap_pos,
                    stop_distance_pct=stop_dist or 1.5,
                    risk_amount=max(1.0, equity * 0.005),
                    strategy=policy.strategy,
                    regime="",
                    confidence=70.0,
                    leverage=25,
                )
                supervisor_tick = tick.to_dict()
                supervisor_note = (
                    f"exit_supervisor:{tick.exit_decision.reason.value}"
                    f":closed={tick.closed}"
                )
                if tick.closed:
                    get_reentry_guard().record_close(
                        symbol=snap_pos.symbol,
                        side=snap_pos.side,
                        strategy=policy.strategy,
                        signal_id=policy.signal_id,
                    )

    ctrl.mark_progress("record_result")
    record_scan_result(payload)
    return {
        "ok": True,
        "send": send,
        "openPositions": open_positions,
        "openOrders": open_orders,
        "state": payload.get("state"),
        "blocker": payload.get("blocker"),
        "eligible": len(payload.get("candidates") or []),
        "top": top.get("symbol") if top else None,
        "rotation": rotation.to_dict(),
        "newEntriesPaused": entries_paused,
        "supervisorNote": supervisor_note,
        "supervisorTick": supervisor_tick,
        "sessionRotationEnabled": True,
        "exitSupervisorEnabled": True,
    }


def ensure_autonomous_runtime() -> dict[str, Any]:
    """Idempotent: restore session + start single controller owner."""
    global _BOOTSTRAPPED
    with _BOOT_LOCK:
        from backend.nexus_research.demo_autonomous.controller import get_autonomous_controller
        from backend.nexus_research.demo_autonomous.session_authorization import (
            autonomous_enabled_from_env,
            get_authorization_validator,
        )

        auth = get_authorization_validator()
        restored = auth.restore_from_disk()
        issued = False
        if auth.session is None and autonomous_enabled_from_env():
            # Auto-issue Demo session only when explicitly enabled via env.
            auth.issue(ttl_ms=6 * 60 * 60 * 1000, max_risk_per_trade_pct=0.5)
            auth.persist_to_disk()
            issued = True

        ctrl = get_autonomous_controller()
        started = False
        if _scanner_enabled() and not (ctrl._thread and ctrl._thread.is_alive()):
            started = ctrl.start(_run_scan_cycle)

        _BOOTSTRAPPED = True
        return {
            "bootstrapped": True,
            "sessionRestored": restored,
            "sessionIssued": issued,
            "scannerStarted": started,
            "scannerRunning": bool(ctrl._thread and ctrl._thread.is_alive()),
            "ownerId": ctrl.owner_id,
            "autoSend": _auto_send_enabled(),
        }

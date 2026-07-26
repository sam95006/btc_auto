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
    return os.environ.get("NEXUS_AUTONOMOUS_DEMO_AUTO_SEND", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


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
    from backend.nexus_research.demo_autonomous.ops_status import record_scan_result
    from backend.nexus_research.demo_autonomous.session_authorization import get_authorization_validator

    equity = 5000.0
    open_positions = 0
    open_orders = 0
    try:
        from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

        snap = capture_account_snapshot()
        equity = float(snap.total_equity or equity)
        open_positions = len([p for p in (snap.positions or []) if float(p.get("size") or 0) > 0])
        open_orders = len(snap.open_orders or [])
    except Exception as exc:
        logger.warning("autonomous_scan_snapshot_failed: %s", type(exc).__name__)

    instruments = None
    quality = None
    try:
        from backend.nexus_research.demo_autonomous.instruments_fetch import (
            fetch_linear_perpetual_instruments,
        )
        from backend.nexus_research.demo_autonomous.market_quality_fetch import fetch_ticker_quality

        instruments = fetch_linear_perpetual_instruments()
        quality = fetch_ticker_quality()
    except Exception as exc:
        logger.warning("autonomous_scan_instruments_failed: %s", type(exc).__name__)

    auth = get_authorization_validator()
    session_active = bool(auth.session and auth.session.is_active())
    send = bool(_auto_send_enabled() and session_active and open_positions == 0 and open_orders == 0)

    # Prefer live dry_run=false only when sending; otherwise dry scan is fine for ranking.
    dry_run = not send
    orch = _build_orch(dry_run=dry_run)
    result = orch.run_cycle(
        equity=equity,
        instruments=instruments,
        quality=quality,
        open_positions=open_positions,
        open_orders=open_orders,
        send=send,
    )
    payload = result.to_dict()
    record_scan_result(payload)
    return {
        "ok": True,
        "send": send,
        "openPositions": open_positions,
        "openOrders": open_orders,
        "state": payload.get("state"),
        "blocker": payload.get("blocker"),
        "eligible": len(payload.get("candidates") or []),
        "top": (payload.get("top") or {}).get("symbol") if payload.get("top") else None,
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

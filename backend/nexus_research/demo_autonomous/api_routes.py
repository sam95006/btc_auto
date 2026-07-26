"""API routes for NEXUS Autonomous Bybit Demo trading (Demo-only)."""
from __future__ import annotations

import logging
import os
from typing import Any

from flask import Flask, jsonify, request

logger = logging.getLogger(__name__)

_ORCH_SINGLETON: Any = None
_WRITE_ADAPTER: Any = None


def _get_orch(*, dry_run: bool | None = None):
    global _ORCH_SINGLETON, _WRITE_ADAPTER
    from backend.nexus_research.demo_autonomous.orchestrator import AutonomousDemoOrchestrator
    from backend.nexus_research.demo_autonomous.session_authorization import (
        get_authorization_validator,
    )

    auth = get_authorization_validator()
    if dry_run is None:
        dry_run = os.environ.get("NEXUS_AUTONOMOUS_DEMO_DRY_RUN", "true").strip().lower() in (
            "1", "true", "yes", "",
        )
    if _ORCH_SINGLETON is None or getattr(_ORCH_SINGLETON, "dry_run", None) != dry_run:
        adapter = _WRITE_ADAPTER
        if adapter is None:
            try:
                from backend.nexus_research.demo_autonomous.write_adapter import AutonomousDemoOrderAdapter
                from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport
                from backend.nexus_research.demo_exchange.signer import DemoRequestSigner

                if dry_run:
                    # Dry-run path: no live credentials required; transport never POSTs.
                    transport = DemoWriteTransport(
                        signer=DemoRequestSigner("dry-run", "dry-run"),
                        auth=auth,
                        dry_run=True,
                    )
                    adapter = AutonomousDemoOrderAdapter(transport, auth=auth)
                else:
                    key = os.environ.get("BYBIT_DEMO_API_KEY", "").strip()
                    secret = os.environ.get("BYBIT_DEMO_API_SECRET", "").strip()
                    if key and secret:
                        transport = DemoWriteTransport(
                            signer=DemoRequestSigner(key, secret),
                            auth=auth,
                            dry_run=False,
                        )
                        adapter = AutonomousDemoOrderAdapter(transport, auth=auth)
                        _WRITE_ADAPTER = adapter
            except Exception as exc:
                logger.warning("write_adapter_init_failed: %s", type(exc).__name__)
                adapter = None
        _ORCH_SINGLETON = AutonomousDemoOrchestrator(
            auth=auth, write_adapter=adapter, dry_run=bool(dry_run),
        )
    return _ORCH_SINGLETON


def register_autonomous_demo_routes(app: Flask) -> None:
    """Register /api/nexus/demo/autonomous/* routes."""

    @app.route("/api/nexus/demo/autonomous/status")
    def nexus_autonomous_status():
        try:
            from backend.nexus_research.demo_autonomous.session_authorization import (
                autonomous_enabled_from_env,
                get_authorization_validator,
            )

            auth = get_authorization_validator()
            sess = auth.session
            return jsonify({
                "ok": True,
                "enabledEnv": autonomous_enabled_from_env(),
                "session": sess.to_public_dict() if sess else None,
                "dryRunDefault": os.environ.get("NEXUS_AUTONOMOUS_DEMO_DRY_RUN", "true"),
                "mainnetAllowed": False,
                "realMoneyAllowed": False,
                "secretSafe": True,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/session/issue", methods=["POST"])
    def nexus_autonomous_session_issue():
        """Issue one-shot Demo session authorization (no secrets returned)."""
        try:
            from backend.nexus_research.demo_autonomous.session_authorization import (
                get_authorization_validator,
            )

            body = request.get_json(silent=True) or {}
            ttl_ms = int(body.get("ttlMs") or (6 * 60 * 60 * 1000))
            ttl_ms = max(60_000, min(ttl_ms, 12 * 60 * 60 * 1000))
            max_risk = float(body.get("maxRiskPerTradePct") or 0.5)
            max_risk = max(0.1, min(max_risk, 0.75))
            symbols = body.get("allowedSymbols") or []
            if isinstance(symbols, str):
                symbols = [s.strip() for s in symbols.split(",") if s.strip()]
            auth = get_authorization_validator().issue(
                ttl_ms=ttl_ms,
                allowed_symbols=tuple(symbols),
                max_risk_per_trade_pct=max_risk,
            )
            return jsonify({"ok": True, "session": auth.to_public_dict(), "secretSafe": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/session/emergency-stop", methods=["POST"])
    def nexus_autonomous_emergency_stop():
        try:
            from backend.nexus_research.demo_autonomous.session_authorization import (
                get_authorization_validator,
            )

            body = request.get_json(silent=True) or {}
            reason = str(body.get("reason") or "operator_stop")
            get_authorization_validator().emergency_stop(reason)
            return jsonify({"ok": True, "emergencyStopped": True, "reason": reason, "secretSafe": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/scan", methods=["POST", "GET"])
    def nexus_autonomous_scan():
        """Scan universe + rank candidates. send=false by default."""
        try:
            body = request.get_json(silent=True) or {}
            send = bool(body.get("send") or request.args.get("send") == "1")
            dry_run = body.get("dryRun")
            if dry_run is None:
                dry_run = None  # env default
            else:
                dry_run = bool(dry_run)
            equity = float(body.get("equity") or request.args.get("equity") or 4994.18989642)
            open_positions = int(body.get("openPositions") or 0)
            open_orders = int(body.get("openOrders") or 0)
            use_live_instruments = bool(body.get("liveInstruments") or request.args.get("live") == "1")

            instruments = None
            quality = None
            if use_live_instruments:
                from backend.nexus_research.demo_autonomous.instruments_fetch import (
                    fetch_linear_perpetual_instruments,
                )
                from backend.nexus_research.demo_autonomous.market_quality_fetch import (
                    fetch_ticker_quality,
                )
                instruments = fetch_linear_perpetual_instruments()
                quality = fetch_ticker_quality()

            orch = _get_orch(dry_run=dry_run)
            # Never auto-send on GET
            if request.method == "GET":
                send = False
            result = orch.run_cycle(
                equity=equity,
                instruments=instruments,
                quality=quality,
                open_positions=open_positions,
                open_orders=open_orders,
                send=send,
            )
            return jsonify({"ok": True, **result.to_dict()})
        except Exception as exc:
            logger.exception("autonomous_scan_failed")
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True, "orderSent": False}), 500

    @app.route("/api/nexus/demo/autonomous/universe")
    def nexus_autonomous_universe():
        try:
            from backend.nexus_research.demo_autonomous.universe import (
                DynamicContractUniverse,
                FIXTURE_INSTRUMENTS,
                fixture_quality,
            )

            live = request.args.get("live") == "1"
            instruments = FIXTURE_INSTRUMENTS
            quality = fixture_quality()
            if live:
                from backend.nexus_research.demo_autonomous.instruments_fetch import (
                    fetch_linear_perpetual_instruments,
                )
                from backend.nexus_research.demo_autonomous.market_quality_fetch import (
                    fetch_ticker_quality,
                )
                instruments = fetch_linear_perpetual_instruments()
                quality = fetch_ticker_quality()
            contracts = DynamicContractUniverse().build(instruments, quality)
            summary = DynamicContractUniverse().summary(contracts)
            return jsonify({
                "ok": True,
                "summary": summary,
                "contracts": [c.to_dict() for c in contracts[:80]],
                "secretSafe": True,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

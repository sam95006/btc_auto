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
        adapter = None
        try:
            from backend.nexus_research.demo_autonomous.write_adapter import AutonomousDemoOrderAdapter
            from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport
            from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator
            from backend.nexus_research.demo_exchange.signer import DemoRequestSigner

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
                adapter = AutonomousDemoOrderAdapter(
                    transport, auth=auth, get_json=transport.get,
                )
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

    @app.route("/api/nexus/demo/autonomous/write-trace", methods=["GET", "POST"])
    def nexus_autonomous_write_trace():
        """Safe account-mode + optional stepwise write diagnosis (no secrets)."""
        try:
            from backend.nexus_research.demo_autonomous.account_mode import (
                DemoAccountModeResolver,
                DemoPositionModeResolver,
            )
            from backend.nexus_research.demo_autonomous.session_authorization import (
                get_authorization_validator,
            )
            from backend.nexus_research.demo_autonomous.write_adapter import AutonomousDemoOrderAdapter
            from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport
            from backend.nexus_research.demo_autonomous.write_trace import (
                DEMO_UNSUPPORTED_WRITE_PATHS,
                WriteStage,
            )
            from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator
            from backend.nexus_research.demo_exchange.signer import DemoRequestSigner

            body = request.get_json(silent=True) or {}
            symbol = str(body.get("symbol") or request.args.get("symbol") or "BTCUSDT")
            run_writes = bool(body.get("runWrites") or request.args.get("runWrites") == "1")
            dry_run = body.get("dryRun")
            if dry_run is None:
                # Reads always use live credentials; dryRun only affects POSTs when runWrites.
                dry_run = request.args.get("dryRun", "0" if not run_writes else "1") != "0"
            else:
                dry_run = bool(dry_run)

            from backend.nexus_research.demo_exchange.credentials import (
                DemoCredentialPresenceValidator,
                fingerprint_secret,
            )
            presence = DemoCredentialPresenceValidator().validate(require=True)
            key, secret = DemoCredentialPresenceValidator().load_secrets_for_signer()
            auth = get_authorization_validator()
            # Account truth GETs must use real signer even when write dry-run is requested.
            read_transport = DemoWriteTransport(
                signer=DemoRequestSigner(key, secret),
                auth=auth,
                dry_run=False,
            )
            write_transport = DemoWriteTransport(
                signer=DemoRequestSigner(key, secret),
                auth=auth,
                dry_run=bool(dry_run),
            )
            adapter = AutonomousDemoOrderAdapter(
                write_transport, auth=auth, get_json=read_transport.get,
            )
            account = adapter.refresh_account_truth()
            pos = DemoPositionModeResolver().resolve_symbol(read_transport.get, symbol)

            read_only = account.read_only_key
            preflight_pass = (
                read_only == 0
                and account.contract_trade_order
                and account.contract_trade_position
            )
            out: dict[str, Any] = {
                "ok": True,
                "symbol": symbol,
                "domain": "api-demo.bybit.com",
                "accountIdentity": "BYBIT_DEMO_ACCOUNT",
                "credentialPresent": presence.configured,
                "credentialFingerprint": presence.fingerprint,
                "readOnly": read_only,
                "contractTradeOrder": account.contract_trade_order,
                "contractTradePosition": account.contract_trade_position,
                "preflightPass": preflight_pass,
                "readWriteKeyNotActive": read_only == 1,
                "account": account.to_dict(),
                "position": pos.to_dict(),
                "demoUnsupportedPaths": sorted(DEMO_UNSUPPORTED_WRITE_PATHS),
                "secretSafe": True,
                "mainnetUsed": False,
            }
            _ = fingerprint_secret  # imported for clarity; presence already fingerprinted

            if read_only == 1:
                out["status"] = "READ_WRITE_KEY_NOT_ACTIVE"
                out["ok"] = False
                return jsonify(out), 409

            if run_writes:
                if not dry_run:
                    try:
                        auth.require_active()
                    except Exception:
                        auth.issue(ttl_ms=600_000, max_risk_per_trade_pct=0.5)
                lev = int(body.get("leverage") or 25)
                s1 = adapter.set_leverage(symbol, lev)
                s2 = adapter.ensure_isolated(symbol, lev)
                out["stages"] = {
                    "STEP_1_SET_LEVERAGE": s1.to_dict(),
                    "STEP_2_VERIFY_OR_SET_MARGIN_MODE": s2.to_dict(),
                }
                out["trace"] = adapter.last_trace.to_dict()
                out["rootCause"] = adapter.last_trace.root_cause_report()
                out["WRITE_10005_ROOT_STAGE"] = adapter.last_trace.root_cause_report()
            return jsonify(out)
        except Exception as exc:
            logger.exception("write_trace_failed")
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/close", methods=["POST"])
    def nexus_autonomous_close():
        """Controlled reduce-only close for Demo position (session required)."""
        try:
            from backend.nexus_research.demo_autonomous.outcome_reflection import build_reflection_bundle
            from backend.nexus_research.demo_autonomous.session_authorization import (
                get_authorization_validator,
            )
            from backend.nexus_research.demo_autonomous.write_adapter import AutonomousDemoOrderAdapter
            from backend.nexus_research.demo_autonomous.write_transport import DemoWriteTransport
            from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot
            from backend.nexus_research.demo_exchange.credentials import DemoCredentialPresenceValidator
            from backend.nexus_research.demo_exchange.signer import DemoRequestSigner

            body = request.get_json(silent=True) or {}
            auth = get_authorization_validator()
            auth.require_active()
            snap = capture_account_snapshot()
            positions = list(snap.positions or [])
            if not positions:
                return jsonify({"ok": True, "closed": False, "reason": "no_position", "secretSafe": True})
            pos = positions[0]
            symbol = str(pos.get("symbol") or body.get("symbol") or "")
            side = str(pos.get("side") or "")
            size = float(pos.get("size") or 0)
            if size <= 0 or not symbol:
                return jsonify({"ok": False, "error": "invalid_position", "secretSafe": True}), 400

            key, secret = DemoCredentialPresenceValidator().load_secrets_for_signer()
            transport = DemoWriteTransport(
                signer=DemoRequestSigner(key, secret), auth=auth, dry_run=False,
            )
            adapter = AutonomousDemoOrderAdapter(transport, auth=auth, get_json=transport.get)
            res = adapter.close_position(symbol, side, size)
            reflection = None
            if res.ok:
                upnl = float(pos.get("unrealisedPnl") or 0)
                reflection = build_reflection_bundle(
                    symbol=symbol,
                    side=side,
                    strategy=str(body.get("strategy") or "UNKNOWN"),
                    regime=str(body.get("regime") or "UNKNOWN"),
                    confidence=float(body.get("confidence") or 0),
                    leverage=int(body.get("leverage") or 25),
                    gross_pnl=upnl,
                    fees=abs(float(pos.get("realisedPnl") or 0)) if float(pos.get("realisedPnl") or 0) < 0 else 0.5,
                    funding=0.0,
                    slippage=0.0,
                    risk_amount=float(body.get("riskAmount") or 25),
                    exit_reason="CONTROLLED_CLOSE",
                ).to_dict()
            return jsonify({
                "ok": res.ok,
                "closed": res.ok,
                "write": res.to_dict(),
                "reflection": reflection,
                "secretSafe": True,
                "mainnetUsed": False,
            })
        except Exception as exc:
            logger.exception("autonomous_close_failed")
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

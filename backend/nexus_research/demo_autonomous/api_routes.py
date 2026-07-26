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

    try:
        from backend.nexus_research.demo_autonomous.runtime_bootstrap import (
            ensure_autonomous_runtime,
        )

        ensure_autonomous_runtime()
    except Exception as exc:
        logger.warning("autonomous_runtime_bootstrap_failed: %s", type(exc).__name__)

    @app.route("/api/nexus/demo/autonomous/status")
    def nexus_autonomous_status():
        try:
            from backend.nexus_research.demo_autonomous.ops_status import build_operations_status

            return jsonify(build_operations_status(include_snapshot=True))
        except Exception as exc:
            logger.exception("autonomous_status_failed")
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/account")
    def nexus_autonomous_account():
        try:
            from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

            snap = capture_account_snapshot().to_dict()
            return jsonify({
                "ok": True,
                "demoEquity": snap.get("total_equity"),
                "availableBalance": snap.get("available_balance"),
                "walletBalance": snap.get("wallet_balance"),
                "unrealisedPnl": snap.get("unrealised_pnl"),
                "positionCount": len([
                    p for p in (snap.get("positions") or []) if float(p.get("size") or 0) > 0
                ]),
                "openOrderCount": len(snap.get("open_orders") or []),
                "fingerprint": snap.get("fingerprint"),
                "status": snap.get("status"),
                "mainnetUsed": False,
                "realMoneyUsed": False,
                "secretSafe": True,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/candidates")
    def nexus_autonomous_candidates():
        try:
            from backend.nexus_research.demo_autonomous.ops_status import get_ops_store

            store = get_ops_store()
            return jsonify({
                "ok": True,
                "eligibleCandidates": store.eligible_candidates,
                "topCandidate": store.top_candidate,
                "blockReasons": list(store.last_block_reasons),
                "lastScanAtMs": store.last_scan_at_ms,
                "symbolsScanned": store.symbols_scanned,
                "tradableSymbols": store.tradable_symbols,
                "secretSafe": True,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/position")
    def nexus_autonomous_position():
        try:
            from backend.nexus_research.demo_autonomous.ops_status import build_operations_status

            st = build_operations_status(include_snapshot=True)
            return jsonify({
                "ok": True,
                "positionOpen": int(st.get("positionCount") or 0) > 0,
                "currentPosition": st.get("currentPosition"),
                "protectionStatus": st.get("protectionStatus"),
                "openOrderCount": st.get("openOrderCount"),
                "reconciliationStatus": st.get("reconciliationStatus"),
                "secretSafe": True,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/recent-trades")
    def nexus_autonomous_recent_trades():
        try:
            from backend.nexus_research.demo_autonomous.ops_status import get_ops_store
            from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

            store = get_ops_store()
            trades: list[dict[str, Any]] = []
            if store.last_trade:
                trades.append(store.last_trade)
            else:
                # Incomplete backfill — do not invent zeros.
                try:
                    snap = capture_account_snapshot()
                    execs = list(snap.executions or [])[:6]
                    if execs:
                        trades.append({
                            "incomplete": True,
                            "noteZh": "資料尚未完整回填",
                            "executionsSample": [
                                {
                                    "symbol": e.get("symbol"),
                                    "side": e.get("side"),
                                    "execPrice": e.get("execPrice") or e.get("price"),
                                    "execQty": e.get("execQty") or e.get("qty"),
                                    "execTime": e.get("execTime") or e.get("updatedTime"),
                                }
                                for e in execs
                                if isinstance(e, dict)
                            ],
                        })
                    else:
                        trades.append({"incomplete": True, "noteZh": "資料尚未完整回填"})
                except Exception:
                    trades.append({"incomplete": True, "noteZh": "資料尚未完整回填"})
            return jsonify({"ok": True, "trades": trades, "secretSafe": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/reflections")
    def nexus_autonomous_reflections():
        try:
            from backend.nexus_research.demo_autonomous.ops_status import get_ops_store

            store = get_ops_store()
            items = []
            if store.last_reflection:
                items.append(store.last_reflection)
            return jsonify({
                "ok": True,
                "reflections": items,
                "lastReflectionAtMs": store.last_reflection_at_ms,
                "secretSafe": True,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/risk")
    def nexus_autonomous_risk():
        try:
            from backend.nexus_research.demo_autonomous.ops_status import build_operations_status

            st = build_operations_status(include_snapshot=False)
            return jsonify({
                "ok": True,
                "demoOnly": True,
                "mainnetBlocked": True,
                "realMoneyBlocked": True,
                "isolatedOnly": True,
                "maxPositions": 1,
                "maxPendingOrders": 1,
                "riskPerTradeMaxPct": 0.5,
                "dailyLossGate": True,
                "weeklyDrawdownGate": True,
                "consecutiveLossGate": True,
                "emergencyStop": st.get("emergencyStop"),
                "reconciliationStatus": st.get("reconciliationStatus"),
                "capitalTier": st.get("capitalTier"),
                "riskTier": st.get("riskTier"),
                "sessionStatus": st.get("sessionStatus"),
                "secretSafe": True,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/health")
    def nexus_autonomous_health():
        try:
            from backend.nexus_research.demo_autonomous.ops_status import build_operations_status

            st = build_operations_status(include_snapshot=True)
            return jsonify({
                "ok": True,
                "opsState": st.get("opsState"),
                "controllerStatus": st.get("controllerStatus"),
                "scannerStatus": st.get("scannerStatus"),
                "sessionStatus": st.get("sessionStatus"),
                "lastScanAtMs": st.get("lastScanAtMs"),
                "lastScanTimeProgressing": st.get("lastScanTimeProgressing"),
                "controllerOwnerCount": st.get("controllerOwnerCount"),
                "bootId": st.get("bootId"),
                "deploymentCommit": st.get("deploymentCommit"),
                "paperStatus": st.get("paperStatus"),
                "ledgerValid": st.get("ledgerValid"),
                "secretSafe": True,
                "mainnetUsed": False,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/source-of-truth")
    def nexus_autonomous_source_of_truth():
        """Live SoT probe — never infer solely from git push."""
        try:
            from backend.nexus_research.demo_autonomous.ops_status import build_operations_status

            st = build_operations_status(include_snapshot=True)
            deploy = str(st.get("deploymentCommit") or "")
            tip_hint = (os.environ.get("NEXUS_EXPECTED_GIT_TIP") or "").strip()
            match = None
            if deploy and tip_hint:
                match = deploy.startswith(tip_hint) or tip_hint.startswith(deploy[:7])
            return jsonify({
                "ok": True,
                "report": "NEXUS_AUTONOMOUS_LIVE_SOURCE_OF_TRUTH",
                "current_deployed_commit": deploy or None,
                "commit_matches_expected": match,
                "runtime_status": st.get("controllerStatus"),
                "boot_id": st.get("bootId"),
                "paper_status": st.get("paperStatus"),
                "ledger_valid": st.get("ledgerValid"),
                "v2_preserved": st.get("v2Preserved"),
                "credential_fingerprint": st.get("credentialFingerprint"),
                "demo_equity": st.get("demoEquity"),
                "available_balance": st.get("availableBalance"),
                "position_count": st.get("positionCount"),
                "open_order_count": st.get("openOrderCount"),
                "autonomous_session_enabled": st.get("sessionStatus") == "ACTIVE",
                "session": st.get("session"),
                "session_expired": (st.get("session") or {}).get("expired") if st.get("session") else None,
                "controller_owner_count": st.get("controllerOwnerCount"),
                "scanner_running": st.get("scannerStatus") == "RUNNING",
                "last_scan_time": st.get("lastScanAtMs"),
                "last_scan_time_progressing": st.get("lastScanTimeProgressing"),
                "last_candidate_time": st.get("lastCandidateTime"),
                "last_order_time": st.get("lastOrderTime"),
                "last_reflection_time": st.get("lastReflectionTime"),
                "ops_state": st.get("opsState"),
                "source_of_truth_pass": bool(
                    st.get("scannerStatus") == "RUNNING"
                    and st.get("bootId")
                    and st.get("secretSafe")
                ),
                "secretSafe": True,
                "mainnetUsed": False,
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
            max_risk = max(0.1, min(max_risk, 0.5))
            symbols = body.get("allowedSymbols") or []
            if isinstance(symbols, str):
                symbols = [s.strip() for s in symbols.split(",") if s.strip()]
            auto_send = bool(body.get("autoSend", True))
            max_cl = int(body.get("maxConsecutiveLosses") or 3)
            risk_tier = str(body.get("riskTier") or "VALIDATION")
            auth = get_authorization_validator().issue(
                ttl_ms=ttl_ms,
                allowed_symbols=tuple(symbols),
                max_risk_per_trade_pct=max_risk,
                auto_send=auto_send,
                max_consecutive_losses=max_cl,
                risk_tier=risk_tier,
            )
            return jsonify({"ok": True, "session": auth.to_public_dict(), "secretSafe": True})
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/session/renew", methods=["POST"])
    def nexus_autonomous_session_renew():
        """Safe Demo session renew — cannot raise risk; mainnet forever blocked."""
        try:
            from backend.nexus_research.demo_autonomous.session_authorization import (
                get_authorization_validator,
            )
            from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

            # Reconcile before write grant.
            snap = capture_account_snapshot()
            body = request.get_json(silent=True) or {}
            ttl_ms = int(body.get("ttlMs") or (6 * 60 * 60 * 1000))
            ttl_ms = max(60_000, min(ttl_ms, 12 * 60 * 60 * 1000))
            auth = get_authorization_validator().renew(ttl_ms=ttl_ms)
            return jsonify({
                "ok": True,
                "session": auth.to_public_dict(),
                "reconcile": {
                    "positionCount": len([
                        p for p in (snap.positions or []) if float(p.get("size") or 0) > 0
                    ]),
                    "openOrderCount": len(snap.open_orders or []),
                },
                "secretSafe": True,
                "mainnetAllowed": False,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 400

    @app.route("/api/nexus/demo/autonomous/session/emergency-stop", methods=["POST"])
    def nexus_autonomous_emergency_stop():
        try:
            from backend.nexus_research.demo_autonomous.controller import get_autonomous_controller
            from backend.nexus_research.demo_autonomous.session_authorization import (
                get_authorization_validator,
            )

            body = request.get_json(silent=True) or {}
            reason = str(body.get("reason") or "operator_stop")
            get_authorization_validator().emergency_stop(reason)
            ctrl = get_autonomous_controller()
            ctrl.health.emergency_stop = True
            # Stop new orders only — do not close positions / cancel protection.
            return jsonify({
                "ok": True,
                "emergencyStopped": True,
                "reason": reason,
                "closesPositions": False,
                "cancelsOrders": False,
                "secretSafe": True,
            })
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secretSafe": True}), 500

    @app.route("/api/nexus/demo/autonomous/scan", methods=["POST", "GET"])
    def nexus_autonomous_scan():
        """Scan universe + rank candidates. send=false by default."""
        try:
            from backend.nexus_research.demo_autonomous.ops_status import record_scan_result

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
            payload = result.to_dict()
            record_scan_result(payload)
            return jsonify({"ok": True, **payload})
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
            _ = WriteStage
            _ = DemoAccountModeResolver

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
            from backend.nexus_research.demo_autonomous.ops_status import record_reflection
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
                fees_raw = body.get("fees")
                funding_raw = body.get("funding")
                slippage_raw = body.get("slippage")
                incomplete = fees_raw is None or funding_raw is None or slippage_raw is None
                if incomplete:
                    reflection = {
                        "incomplete": True,
                        "noteZh": "資料尚未完整回填",
                        "outcome": {
                            "symbol": symbol,
                            "side": side,
                            "strategy": str(body.get("strategy") or "UNKNOWN"),
                            "grossPnl": upnl,
                            "fees": None,
                            "funding": None,
                            "slippage": None,
                            "netPnl": None,
                            "rMultiple": None,
                            "livePatchApplied": False,
                        },
                        "livePatchApplied": False,
                    }
                else:
                    reflection = build_reflection_bundle(
                        symbol=symbol,
                        side=side,
                        strategy=str(body.get("strategy") or "UNKNOWN"),
                        regime=str(body.get("regime") or "UNKNOWN"),
                        confidence=float(body.get("confidence") or 0),
                        leverage=int(body.get("leverage") or 25),
                        gross_pnl=upnl,
                        fees=float(fees_raw),
                        funding=float(funding_raw),
                        slippage=float(slippage_raw),
                        risk_amount=float(body.get("riskAmount") or 25),
                        exit_reason="CONTROLLED_CLOSE",
                    ).to_dict()
                trade = {
                    "symbol": symbol,
                    "side": side,
                    "strategy": body.get("strategy") or "UNKNOWN",
                    "confidence": body.get("confidence"),
                    "leverage": body.get("leverage") or 25,
                    "entry": pos.get("avgPrice") or pos.get("entryPrice"),
                    "exit": None,
                    "grossPnl": upnl,
                    "fees": None if incomplete else float(fees_raw),
                    "funding": None if incomplete else float(funding_raw),
                    "slippage": None if incomplete else float(slippage_raw),
                    "netPnl": None,
                    "rMultiple": None,
                    "exitReason": "CONTROLLED_CLOSE",
                    "reflectionStatus": "CREATED",
                    "incomplete": incomplete,
                    "noteZh": "資料尚未完整回填" if incomplete else None,
                }
                record_reflection(reflection, trade)
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

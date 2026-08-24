import json
import time
from pathlib import Path

from flask import jsonify, request, send_file

try:
    from flask_sock import Sock
except Exception:
    Sock = None

from backend.core.json_safe import sanitize_for_json
from backend.coordination.station_dialogue_service import StationDialogueService
from backend.services.runtime_store import runtime_store
from backend.autonomy.pure_ai_status import build_pure_ai_status
from backend.services.console_assets import verify_console_assets
from backend.services.layout_store import layout_store
from backend.trading.trading_mode import get_trading_mode, require_testnet_credentials
from backend.core.data_paths import resolve_runtime_db_path
import backend.runtime.embed_flags as embed_flags
from config.live_sync_config import WS_PUSH_INTERVAL_SECONDS


_dialogue = None
_llm_gateway = None


def _llm_gateway_instance():
    global _llm_gateway
    if _llm_gateway is None:
        try:
            from backend.llm import LLMGateway

            _llm_gateway = LLMGateway()
        except Exception:
            _llm_gateway = False
    return _llm_gateway if _llm_gateway is not False else None


def _dialogue_service():
    global _dialogue
    if _dialogue is None:
        from backend.services.nexus_runtime import nexus_runtime

        _dialogue = StationDialogueService(
            StationChatLog(runtime_store),
            llm_gateway=_llm_gateway_instance(),
            runtime_ops={
                "refresh_live_exchange_state": nexus_runtime.refresh_live_exchange_state,
                "flatten_all_positions": nexus_runtime.flatten_all_positions,
                "resume_trading": nexus_runtime.resume_trading,
                "reset_testnet_sandbox": nexus_runtime.reset_testnet_sandbox,
            },
        )
    return _dialogue


def register_nexus_routes(app):
    @app.route("/nexus")
    def nexus_dashboard():
        return send_file(Path(app.root_path) / "templates" / "nexus_command.html")

    @app.route("/api/nexus/connectivity")
    def nexus_connectivity():
        """Safe diagnostics for cloud vs local (no secrets)."""
        mode = get_trading_mode()
        missing = require_testnet_credentials() if mode == "binance_testnet" else []
        try:
            from backend.services.nexus_runtime import nexus_runtime

            nexus_runtime.refresh_live_exchange_state(force=True)
        except Exception as exc:
            print(f"[api] connectivity refresh failed: {exc}")
        snap = nexus_runtime.snapshot()
        system = snap.get("system") or {}
        binance_sync = snap.get("binance_sync") or {}
        capital = snap.get("capital") or {}
        binance_spot = capital.get("binance_spot") or {}
        binance_futures = capital.get("binance_futures") or {}
        account_binding = capital.get("account_binding") or {}
        decision = snap.get("decision_summary") or {}
        last_tick_error = decision.get("last_tick_error") or getattr(nexus_runtime, "_last_tick_error", None)
        startup_exit_check = decision.get("startup_exit_check") or getattr(nexus_runtime, "_startup_exit_check", None) or {}
        futures_write_probe = {}
        futures_trading_access = getattr(nexus_runtime, "_futures_trading_access", None) or {}
        try:
            if nexus_runtime.futures_client.is_configured():
                futures_trading_access = nexus_runtime.futures_client.validate_trading_access("ETHUSDT")
                futures_write_probe = futures_trading_access.get("write_probe") or nexus_runtime.futures_client.probe_write_access(
                    "ETHUSDT"
                )
        except Exception as exc:
            futures_write_probe = {"ok": False, "error": str(exc)}
            futures_trading_access = {"ok": False, "error": str(exc)}
        live_positions = [
            {
                "fleet": item.get("fleet"),
                "symbol": item.get("symbol"),
                "side": item.get("side"),
                "quantity": item.get("quantity"),
                "unrealized_pnl": item.get("unrealized_pnl"),
            }
            for item in (snap.get("positions") or [])
            if str(item.get("market_type") or "") == "futures"
        ]
        return jsonify(
            {
                "trading_mode": mode,
                "testnet_credentials_missing": missing,
                "account_binding": account_binding,
                "futures_scope": "usdt_m",
                "coin_margined_included": False,
                "runtime_db_path": resolve_runtime_db_path(),
                "embedded_worker_started": embed_flags.embedded_worker_started,
                "embedded_worker_error": embed_flags.embedded_worker_error,
                "snapshot_system_health": system.get("system_health"),
                "snapshot_worker_module": (system.get("module_health") or {}).get("worker"),
                "binance_sync_status": binance_sync.get("sync_status"),
                "capital_source": capital.get("source", ""),
                "live_position_count": int(decision.get("live_position_count") or len(live_positions)),
                "exchange_position_symbols": list(decision.get("exchange_position_symbols") or []),
                "live_positions": live_positions,
                "last_tick_error": last_tick_error,
                "startup_exit_check": startup_exit_check,
                "position_exit_diagnostics": decision.get("position_exit_diagnostics") or [],
                "futures_write_probe": futures_write_probe,
                "futures_trading_access": futures_trading_access,
                "external_market_intel": decision.get("external_market_intel")
                or (
                    nexus_runtime.external_market_intel.snapshot()
                    if getattr(nexus_runtime, "external_market_intel", None)
                    else {}
                ),
                "binance_balances": {
                    "spot_usdt": binance_spot.get("usdt_total", capital.get("spot_usdt_total")),
                    "spot_usdc": binance_spot.get("usdc_total", capital.get("spot_usdc_total")),
                    "spot_stable_total": binance_spot.get("stable_total", capital.get("spot_stable_total")),
                    "futures_wallet": binance_futures.get("wallet_balance", capital.get("futures_exchange_wallet_balance")),
                    "futures_equity": binance_futures.get("margin_balance", capital.get("futures_exchange_margin_balance")),
                    "futures_unrealized": binance_futures.get("unrealized_pnl", capital.get("futures_unrealized_pnl")),
                    "futures_available": binance_futures.get("available_balance", capital.get("futures_available_balance")),
                    "combined_total": capital.get("total"),
                },
                "hints": [
                    "If snapshot_system_health is WORKER_OFFLINE and embedded_worker_started is false, "
                    "set NEXUS_EMBEDDED_WORKER=1 or deploy on Zeabur (auto-detects ZEABUR_* IDs).",
                    "If testnet_credentials_missing is non-empty, add the four BINANCE_*_TESTNET_* keys in Zeabur Variables.",
                    "For the same DB as local, mount a volume at NEXUS_DATA_DIR and import a state bundle (see docs/NEXUS_GUIDE.zh-TW.md).",
                    (
                        "live_position_count is 0 but Binance App shows open positions: Zeabur "
                        "BINANCE_FUTURES_TESTNET_* keys likely belong to a different Demo account. "
                        "Regenerate keys on the same U本位 Demo account as the App and redeploy."
                        if not live_positions and not missing
                        else ""
                    ),
                    (
                        "account_binding.keys_distinct is true: spot/futures API keys are different strings (this is normal). "
                        "If balances or open positions don't match what you see in the Binance App, the keys may still point to "
                        "a different testnet account than the App you are viewing. Re-generate the four testnet keys from the same "
                        "account (Spot Testnet + Futures Demo) and redeploy."
                        if account_binding.get("keys_distinct") is True
                        else ""
                    ),
                    (
                        "futures_trading_access.write_post_probe.ok is false with -1109: "
                        "your Futures Demo key can READ positions but Binance rejects all signed POST trade calls. "
                        "This is not a NEXUS bug. Recreate the key on https://demo.binance.com → API Management, "
                        "enable Reading + Spot/Margin + Futures, paste Secret into BINANCE_FUTURES_TESTNET_SECRET_KEY, redeploy. "
                        "Local check: python tools/deploy/verify_binance_futures_write.py"
                        if (futures_trading_access.get("write_post_probe") or {}).get("ok") is False
                        else ""
                    ),
                    (
                        "futures_write_probe failed: same -1109 on signed write endpoints. Re-create API key+Secret on "
                        "demo.binance.com, set BINANCE_FUTURES_TESTNET_API_KEY and BINANCE_FUTURES_TESTNET_SECRET_KEY in Zeabur, redeploy."
                        if futures_write_probe and not futures_write_probe.get("ok")
                        else ""
                    ),
                    (
                        f"startup_exit_check ran: checked={startup_exit_check.get('positions_checked', 0)} "
                        f"exits={startup_exit_check.get('exits_triggered', 0)} "
                        f"errors={len(startup_exit_check.get('errors') or [])}. "
                        "See position_exit_diagnostics for stop/TP thresholds."
                        if startup_exit_check.get("ran_at")
                        else ""
                    ),
                ],
            }
        )

    @app.route("/api/nexus/state")
    def nexus_state():
        """Fast path: serve worker-maintained snapshot from memory/DB (no blocking rebuild)."""
        snap = runtime_store.load_snapshot() or {}
        meta = runtime_store.live_snapshot_meta()
        if not meta.get("has_data"):
            try:
                from backend.services.nexus_runtime import nexus_runtime

                thread = getattr(nexus_runtime, "_thread", None)
                worker_alive = bool(thread and thread.is_alive())
                if not worker_alive:
                    nexus_runtime.refresh_live_exchange_state(force=False, min_interval_sec=30)
                    snap = runtime_store.load_snapshot() or snap
            except Exception as exc:
                print(f"[api] cold-start snapshot refresh failed: {exc}")
        return jsonify(sanitize_for_json(snap))

    @app.route("/api/nexus/wallet")
    def nexus_wallet():
        snap = runtime_store.load_snapshot()
        return jsonify({"capital": snap.get("capital", {}), "loans": snap.get("loans", {}), "pnl": snap.get("pnl", {})})

    @app.route("/api/nexus/positions")
    def nexus_positions():
        try:
            from backend.services.nexus_runtime import nexus_runtime

            nexus_runtime.refresh_live_exchange_state(force=True)
            return jsonify(nexus_runtime.snapshot().get("positions", []))
        except Exception as exc:
            print(f"[api] positions refresh failed: {exc}")
        return jsonify(runtime_store.load_snapshot().get("positions", []))

    @app.route("/api/nexus/trades")
    def nexus_trades():
        snap = runtime_store.load_snapshot()
        return jsonify({"orders": snap.get("orders", []), "trades": snap.get("trades", [])})

    @app.route("/api/nexus/alerts")
    def nexus_alerts():
        snap = runtime_store.load_snapshot()
        return jsonify({"alerts": snap.get("alerts", []), "meetings": snap.get("meetings", [])})

    @app.route("/api/nexus/audit")
    def nexus_audit():
        return jsonify({"items": runtime_store.recent_decision_audit(limit=200)})

    @app.route("/api/nexus/maturity-radar")
    def nexus_maturity_radar():
        try:
            from backend.services.nexus_runtime import nexus_runtime

            snap = nexus_runtime.snapshot()
            return jsonify(snap.get("maturity_radar") or {})
        except Exception as exc:
            print(f"[api] maturity radar failed: {exc}")
        snap = runtime_store.load_snapshot()
        return jsonify(snap.get("maturity_radar") or {})

    @app.route("/api/nexus/trading-health")
    def nexus_trading_health():
        try:
            from backend.services.nexus_runtime import nexus_runtime

            snap = nexus_runtime.snapshot()
            return jsonify(snap.get("trading_health") or {})
        except Exception as exc:
            print(f"[api] trading health failed: {exc}")
        snap = runtime_store.load_snapshot()
        return jsonify(snap.get("trading_health") or {})

    @app.route("/api/nexus/daily-report")
    def nexus_daily_report():
        snap = runtime_store.load_snapshot()
        return jsonify(snap.get("daily_report", {}))

    @app.route("/api/nexus/pure-ai-status")
    def nexus_pure_ai_status():
        """Verifiable Pure AI mode — proves LLM pipeline is active (not a separate external API)."""
        try:
            from backend.services.nexus_runtime import nexus_runtime

            return jsonify(build_pure_ai_status(nexus_runtime))
        except Exception as exc:
            return jsonify({"active": False, "error": str(exc)}), 500

    @app.route("/api/nexus/hemostasis-status")
    def nexus_hemostasis_status():
        try:
            from config.hemostasis_config import defensive_mode_active, fleet_burst_enabled, radar_dispatch_entries_allowed
            from config.leverage_config import MAX_SYSTEM_LEVERAGE
            from backend.services.nexus_runtime import nexus_runtime

            growth = dict(getattr(nexus_runtime, "growth_status", None) or {})
            return jsonify(
                {
                    "defensive_mode": defensive_mode_active(),
                    "block_new_entries": bool(growth.get("block_new_entries")),
                    "block_reason": str(growth.get("block_reason") or ""),
                    "radar_dispatch_entries_allowed": radar_dispatch_entries_allowed(),
                    "fleet_burst_enabled": fleet_burst_enabled(),
                    "fleet_anti_burst": dict(getattr(nexus_runtime, "_fleet_burst_status", None) or {}),
                    "max_system_leverage": int(MAX_SYSTEM_LEVERAGE),
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/nexus/trade-results")
    def nexus_trade_results():
        limit = min(500, max(1, int(request.args.get("limit", 50))))
        symbol = str(request.args.get("symbol") or "").upper()
        items = runtime_store.recent_trade_results(limit=limit)
        if symbol:
            items = [row for row in items if str(row.get("symbol") or "").upper() == symbol]
        return jsonify({"items": items, "count": len(items), "limit": limit})

    @app.route("/api/nexus/reflection-records")
    def nexus_reflection_records():
        limit = min(500, max(1, int(request.args.get("limit", 50))))
        symbol = str(request.args.get("symbol") or "").upper()
        items = runtime_store.recent_reflection_records(limit=limit)
        if symbol:
            items = [row for row in items if str(row.get("symbol") or "").upper() == symbol]
        return jsonify({"items": items, "count": len(items), "limit": limit})

    @app.route("/api/nexus/applied-learning-patches")
    def nexus_applied_learning_patches():
        limit = min(500, max(1, int(request.args.get("limit", 50))))
        fleet = str(request.args.get("fleet") or "").upper()
        symbol = str(request.args.get("symbol") or "").upper()
        items = runtime_store.list_applied_learning_patches(limit=limit)
        if fleet:
            items = [row for row in items if str(row.get("fleet") or "").upper() == fleet]
        if symbol:
            items = [
                row
                for row in items
                if str((row.get("symbol_lesson") or {}).get("symbol") or "").upper() == symbol
            ]
        return jsonify({"items": items, "count": len(items), "limit": limit})

    @app.route("/api/nexus/micro-validation/status")
    def nexus_micro_validation_status():
        """Read-only Phase 3.0 session state (arm remains CLI-only)."""
        try:
            from config.micro_validation_config import (
                MICRO_VALIDATION_ALLOW_REARM,
                MICRO_VALIDATION_MAX_HOLD_MIN,
                MICRO_VALIDATION_MAX_LEVERAGE,
                MICRO_VALIDATION_MAX_MARGIN_USD,
                MICRO_VALIDATION_REQUIRE_REFLECTION,
                MICRO_VALIDATION_SIDE,
                MICRO_VALIDATION_SL_USD,
                MICRO_VALIDATION_SYMBOL,
                MICRO_VALIDATION_TP_ENABLED,
                MICRO_VALIDATION_TP_USD,
                micro_validation_active,
            )
            from backend.validation.micro_entry_guard import get_micro_entry_guard

            guard = get_micro_entry_guard()
            session = guard.snapshot()
            verification = dict(session.get("verification") or {})
            report = dict(session.get("report") or {})
            return jsonify(
                {
                    "enabled": micro_validation_active(),
                    "config": {
                        "symbol": MICRO_VALIDATION_SYMBOL,
                        "side": MICRO_VALIDATION_SIDE,
                        "max_margin_usd": MICRO_VALIDATION_MAX_MARGIN_USD,
                        "max_leverage": MICRO_VALIDATION_MAX_LEVERAGE,
                        "sl_usd": MICRO_VALIDATION_SL_USD,
                        "tp_enabled": MICRO_VALIDATION_TP_ENABLED,
                        "tp_usd": MICRO_VALIDATION_TP_USD,
                        "max_hold_min": MICRO_VALIDATION_MAX_HOLD_MIN,
                        "require_reflection": MICRO_VALIDATION_REQUIRE_REFLECTION,
                        "allow_rearm": MICRO_VALIDATION_ALLOW_REARM,
                    },
                    "session": session,
                    "verification": verification,
                    "report": report,
                    "arm_executed": str(session.get("state") or "IDLE").upper()
                    in {"ARMED", "ENTRY_SENT", "POSITION_OPEN", "EXIT_PENDING", "VERIFYING", "COMPLETED"}
                    or bool(session.get("entry_consumed")),
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/nexus/stage3/status")
    def nexus_stage3_status():
        """Read-only Stage 3 Bybit demo learning runner status for UI."""
        try:
            from backend.monitoring.stage3_status_service import build_stage3_context

            return jsonify(build_stage3_context())
        except Exception as exc:
            return jsonify({"read_only": True, "error": str(exc), "data_available": False}), 500

    @app.route("/api/nexus/demo/readiness")
    def nexus_demo_readiness():
        """Phase 6.6.1 read-only credential discovery — zero network calls, no secret values."""
        try:
            from backend.nexus_research.demo_exchange.discovery import DemoReadinessReport

            report = DemoReadinessReport.build()
            return jsonify(report.to_dict())
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "probe_enabled": False}), 500

    @app.route("/api/nexus/demo/discovery")
    def nexus_demo_discovery():
        """Phase 6.6.1 credential presence discovery — no secret values returned."""
        try:
            from backend.nexus_research.demo_exchange.discovery import discover_credentials

            result = discover_credentials()
            return jsonify(result.to_dict())
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "network_calls": 0}), 500

    @app.route("/api/nexus/demo/credential-audit")
    def nexus_demo_credential_audit():
        """Phase 6.6.1 credential presence + fingerprint + boot continuity — no secrets."""
        try:
            from backend.nexus_research.demo_exchange.credential_audit import DemoCredentialPresenceAudit

            audit = DemoCredentialPresenceAudit.build()
            return jsonify(audit.to_dict())
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "secret_safe": True}), 500

    @app.route("/api/nexus/demo/account-snapshot")
    def nexus_demo_account_snapshot():
        """Phase 6.6.1 GET-only account snapshot — probe_disabled with zero network calls when off."""
        try:
            from backend.nexus_research.demo_exchange.account_snapshot import capture_account_snapshot

            snapshot = capture_account_snapshot()
            return jsonify(snapshot.to_dict())
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc), "network_calls": 0, "secret_safe": True}), 500

    try:
        from backend.nexus_research.demo_autonomous.api_routes import register_autonomous_demo_routes

        register_autonomous_demo_routes(app)
    except Exception as _auto_reg_exc:  # noqa: BLE001 — keep server boot if optional module missing
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "autonomous_demo_routes_unavailable: %s", type(_auto_reg_exc).__name__
        )

    try:
        from backend.nexus_global_shadow.api_routes import register_shadow_routes

        register_shadow_routes(app)
    except Exception as _shadow_reg_exc:  # noqa: BLE001 — keep server boot if optional module missing
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "shadow_routes_unavailable: %s", type(_shadow_reg_exc).__name__
        )

    try:
        from backend.nexus_adaptive_policy.api_routes import register_adaptive_policy_routes

        register_adaptive_policy_routes(app)
    except Exception as _adaptive_reg_exc:  # noqa: BLE001 — keep server boot if optional module missing
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "adaptive_policy_routes_unavailable: %s", type(_adaptive_reg_exc).__name__
        )

    try:
        from backend.nexus_real_shadow.api_routes import register_real_shadow_routes

        register_real_shadow_routes(app)
    except Exception as _wave5_reg_exc:  # noqa: BLE001 — keep server boot if optional module missing
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "real_shadow_routes_unavailable: %s", type(_wave5_reg_exc).__name__
        )

    try:
        from backend.nexus_bounded_runtime import install_certified_bounded_runtime

        install_certified_bounded_runtime()
    except Exception as _bounded_rt_exc:  # noqa: BLE001
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "certified_bounded_runtime_unavailable: %s", type(_bounded_rt_exc).__name__
        )

    try:
        from backend.nexus_demo_execution.api_routes import register_demo_execution_routes

        register_demo_execution_routes(app)
    except Exception as _demo_exec_reg_exc:  # noqa: BLE001 — keep server boot if optional module missing
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "demo_execution_routes_unavailable: %s", type(_demo_exec_reg_exc).__name__
        )

    try:
        from backend.nexus_demo_execution.internal_market_routes import register_internal_market_routes

        register_internal_market_routes(app)
    except Exception as _mkt_reg_exc:  # noqa: BLE001
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "internal_market_routes_unavailable: %s", type(_mkt_reg_exc).__name__
        )

    try:
        from backend.nexus_control_plane.api_routes import register_control_plane_routes

        register_control_plane_routes(app)
    except Exception as _cp_reg_exc:  # noqa: BLE001 — keep server boot if optional module missing
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "control_plane_routes_unavailable: %s", type(_cp_reg_exc).__name__
        )

    @app.route("/api/nexus/stage3/summary")
    def nexus_stage3_summary():
        try:
            from backend.monitoring.stage3_status_service import build_stage3_summary

            return jsonify(build_stage3_summary())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/nexus/stage3/account")
    def nexus_stage3_account():
        try:
            from backend.monitoring.stage3_status_service import build_stage3_account

            return jsonify(build_stage3_account())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/nexus/stage3/trades")
    def nexus_stage3_trades():
        limit = min(500, max(1, int(request.args.get("limit", 50))))
        try:
            from backend.monitoring.stage3_status_service import build_stage3_trades

            return jsonify(build_stage3_trades(limit=limit))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/nexus/stage3/learning")
    def nexus_stage3_learning():
        limit = min(500, max(1, int(request.args.get("limit", 50))))
        try:
            from backend.monitoring.stage3_status_service import build_stage3_learning

            return jsonify(build_stage3_learning(limit=limit))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/nexus/stage3/log-tail")
    def nexus_stage3_log_tail():
        lines = min(200, max(1, int(request.args.get("lines", 80))))
        try:
            from backend.monitoring.stage3_status_service import build_stage3_log_tail

            return jsonify(build_stage3_log_tail(lines=lines))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/nexus/layout")
    def nexus_layout():
        return jsonify(layout_store.load())

    @app.route("/api/nexus/layout", methods=["POST"])
    def nexus_layout_save():
        payload = request.json or {}
        return jsonify(layout_store.save(payload))

    @app.route("/api/nexus/decision-traces")
    def nexus_decision_traces():
        return jsonify({"items": runtime_store.recent_decision_traces(limit=200)})

    @app.route("/api/nexus/learning-reviews")
    def nexus_learning_reviews():
        snap = runtime_store.load_snapshot()
        return jsonify((snap.get("learning_status") or {}).get("learning_reviews") or {})

    @app.route("/api/nexus/proposals")
    def nexus_proposals():
        return jsonify({"items": runtime_store.recent_trade_proposals(limit=100)})

    @app.route("/api/nexus/governance-status")
    def nexus_governance_status():
        snap = runtime_store.load_snapshot()
        return jsonify(snap.get("upgrade_pipeline") or {})

    @app.route("/api/nexus/research/observability")
    def nexus_research_observability():
        """Read-only functional research observability — no secrets."""
        try:
            from pathlib import Path
            import json

            root = Path(__file__).resolve().parents[2]
            path_edge = (
                root
                / "artifacts"
                / "readiness"
                / "immutable"
                / "edge_discovery_diagnostics_v2"
                / "functional_observability_status.json"
            )
            path_v12 = (
                root
                / "artifacts"
                / "readiness"
                / "immutable"
                / "strategy_engine_broad_coverage_v1_2"
                / "functional_observability_status.json"
            )
            path_v11 = (
                root
                / "artifacts"
                / "readiness"
                / "immutable"
                / "strategy_engine_semantic_repair_v1_1"
                / "functional_observability_status.json"
            )
            path = (
                root
                / "artifacts"
                / "readiness"
                / "immutable"
                / "general_multi_strategy_engine_v1"
                / "functional_observability_status.json"
            )
            if path_edge.is_file():
                payload = json.loads(path_edge.read_text(encoding="utf-8"))
            elif path_v12.is_file():
                payload = json.loads(path_v12.read_text(encoding="utf-8"))
            elif path_v11.is_file():
                payload = json.loads(path_v11.read_text(encoding="utf-8"))
            elif path.is_file():
                payload = json.loads(path.read_text(encoding="utf-8"))
            else:
                from backend.nexus_strategy_engine.observability import observability_contract

                payload = {
                    "schema": "functional_research_observability_status_v1",
                    "status": "NOT_GENERATED_YET",
                    "contract": observability_contract(),
                    "secrets_present_in_payload": False,
                    "read_only": True,
                }
            blob = json.dumps(payload)
            if any(x in blob for x in ("gsk_", "csk-", "Bearer ")):
                return jsonify({"error": "secret_leak_blocked"}), 500
            return jsonify(payload)
        except Exception as exc:
            return jsonify({"error": "observability_unavailable", "detail": str(exc)[:120]}), 500

    @app.route("/api/nexus/performance-report")
    def nexus_performance_report():
        try:
            from backend.analytics.performance_report import build_performance_report

            research_gate = {}
            try:
                from backend.services.nexus_runtime import nexus_runtime

                research_gate = dict(getattr(nexus_runtime, "_research_gate_status", None) or {})
            except Exception:
                research_gate = {}

            return jsonify(build_performance_report(runtime_store, research_gate=research_gate))
        except Exception as exc:
            # Fall back to the cached summary embedded in the last snapshot.
            snap = runtime_store.load_snapshot() or {}
            summary = ((snap.get("analytics") or {}).get("performance_report_summary") or {}) if isinstance(snap, dict) else {}
            return jsonify({"ok": False, "error": str(exc), "summary": summary}), 200

    @app.route("/api/nexus/research-gate")
    def nexus_research_gate():
        try:
            from backend.services.nexus_runtime import nexus_runtime

            return jsonify(dict(getattr(nexus_runtime, "_research_gate_status", None) or {}))
        except Exception as exc:
            return jsonify({"enabled": False, "error": str(exc)}), 500

    @app.route("/api/nexus/webhook/tradingview", methods=["POST"])
    def nexus_tradingview_webhook():
        from backend.api.tradingview_webhook import parse_tradingview_payload

        payload = request.json or {}
        ok, proposal, reason = parse_tradingview_payload(payload)
        if not ok or not proposal:
            return jsonify({"ok": False, "error": reason}), 400
        try:
            from backend.services.nexus_runtime import nexus_runtime

            executed = nexus_runtime.ingest_external_proposal(proposal)
            return jsonify({"ok": True, "reason": reason, "executed": bool(executed), "proposal": proposal})
        except AttributeError:
            return jsonify(
                {
                    "ok": True,
                    "reason": reason,
                    "executed": False,
                    "proposal": proposal,
                    "hint": "Proposal parsed; wire nexus_runtime.ingest_external_proposal for auto-trade.",
                }
            )
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    @app.route("/api/nexus/monthly-revenue")
    def nexus_monthly_revenue():
        try:
            from backend.services.nexus_runtime import nexus_runtime

            return jsonify(nexus_runtime.snapshot().get("monthly_revenue") or {})
        except Exception as exc:
            print(f"[api] monthly revenue failed: {exc}")
        return jsonify(runtime_store.load_snapshot().get("monthly_revenue") or {})

    @app.route("/api/nexus/revenue-plan")
    def nexus_revenue_plan():
        try:
            from backend.services.nexus_runtime import nexus_runtime

            snap = nexus_runtime.snapshot()
            return jsonify(snap.get("revenue_plan") or {})
        except Exception as exc:
            print(f"[api] revenue plan failed: {exc}")
        return jsonify(runtime_store.load_snapshot().get("revenue_plan") or {})

    @app.route("/api/nexus/decision-funnel")
    def nexus_decision_funnel():
        try:
            from backend.services.nexus_runtime import nexus_runtime

            return jsonify(nexus_runtime.snapshot().get("decision_funnel") or {})
        except Exception as exc:
            print(f"[api] decision funnel failed: {exc}")
        from backend.monitoring.decision_funnel_service import DecisionFunnelService

        return jsonify(
            DecisionFunnelService().build_report(
                audits=runtime_store.recent_decision_audit(limit=200),
                validations=runtime_store.recent_trade_validation_events(limit=200),
                proposals=runtime_store.recent_trade_proposals(limit=100),
                trade_results=runtime_store.recent_trade_results(limit=200),
                decision_traces=runtime_store.recent_decision_traces(limit=50),
            )
        )

    @app.route("/api/nexus/loss-review")
    def nexus_loss_review():
        """Recent losing trades + learning recommendations (no secrets) for Zeabur review."""
        snap = runtime_store.load_snapshot()
        trade_results = runtime_store.recent_trade_results(limit=120)
        losses = [item for item in trade_results if float(item.get("pnl", 0.0) or 0.0) < 0][:40]
        learning = snap.get("learning_status", {}) or {}
        reflection = (snap.get("agent_advisory", {}) or {}).get("reflection", {})
        return jsonify(
            {
                "generated_at": snap.get("system", {}).get("current_time"),
                "loss_trades": losses,
                "failure_patterns": learning.get("failure_patterns", []),
                "latest_recommendations": learning.get("latest_recommendations", []),
                "reflection_summary": reflection.get("summary") or reflection.get("machine_summary"),
                "strategy_adaptation": (learning.get("strategy_adaptation") or {}).get("strategies", {}),
                "decision_audit": runtime_store.recent_decision_audit(limit=40),
                "hint": "Download trading.db via NEXUS_DATA_DIR volume or: python tools/deploy/nexus_state_sync.py export",
            }
        )

    @app.route("/api/nexus/chat", methods=["POST"])
    def nexus_chat():
        payload = request.json or {}
        channel = str(payload.get("channel", "WORLD")).upper()
        message = str(payload.get("message", "")).strip()
        player_name = str(payload.get("speaker", "")).strip() or None
        allowed = {"WORLD", "HQ", "BTC", "ETH", "SOL", "PEPE", "RADAR", "NEWS", "RISK"}
        if channel not in allowed:
            return jsonify({"ok": False, "error": "invalid channel"}), 400
        if not message:
            return jsonify({"ok": False, "error": "message is required"}), 400
        if len(message) > 500:
            return jsonify({"ok": False, "error": "message too long"}), 400
        result = _dialogue_service().handle_player_message(channel, message, runtime_store.load_snapshot(), player_name)
        if not result.get("ok"):
            return jsonify(result), 400
        return jsonify(result)

    @app.route("/api/nexus/control", methods=["POST"])
    def nexus_control():
        payload = request.json or {}
        command = str(payload.get("command", "")).strip().upper()
        if not command:
            return jsonify({"ok": False, "error": "command is required"}), 400
        command_id = runtime_store.enqueue_command(command, payload)
        return jsonify({"ok": True, "command_id": command_id, "command": command})

    if Sock is not None:
        sock = Sock(app)

        @sock.route("/ws/nexus")
        def nexus_ws(ws):
            last_sent = None
            while True:
                snapshot = runtime_store.load_snapshot() or {}
                payload = {"snapshot": sanitize_for_json(snapshot)}
                encoded = json.dumps(payload, ensure_ascii=False)
                if encoded != last_sent:
                    ws.send(encoded)
                    last_sent = encoded
                else:
                    ws.send(json.dumps({"heartbeat": True}, ensure_ascii=False))
                time.sleep(WS_PUSH_INTERVAL_SECONDS)
    else:
        print("[nexus] flask-sock not installed; REST polling remains available.")

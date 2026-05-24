import json
import time
from pathlib import Path

from flask import jsonify, request, send_file

try:
    from flask_sock import Sock
except Exception:
    Sock = None

from backend.coordination.station_chat_log import StationChatLog
from backend.coordination.station_dialogue_service import StationDialogueService
from backend.services.runtime_store import runtime_store
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
        _dialogue = StationDialogueService(StationChatLog(runtime_store), llm_gateway=_llm_gateway_instance())
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
                        "account_binding.accounts_mismatch is true: spot and futures API keys belong to different "
                        "Binance testnet accounts. Dashboard totals are correct for the keys in Zeabur env, but may "
                        "not match a single Binance App screen. Use keys from the same testnet account."
                        if account_binding.get("accounts_mismatch")
                        else ""
                    ),
                ],
            }
        )

    @app.route("/api/nexus/state")
    def nexus_state():
        snap = None
        try:
            from backend.services.nexus_runtime import nexus_runtime

            nexus_runtime.refresh_live_exchange_state(force=True)
            snap = nexus_runtime.snapshot()
        except Exception as exc:
            print(f"[api] live exchange refresh failed: {exc}")
        if snap is None:
            snap = runtime_store.load_snapshot()
        try:
            runtime_store.save_snapshot(
                snap,
                worker_status="ONLINE",
                writer="api_state",
                single_instance=False,
            )
        except Exception as exc:
            print(f"[api] snapshot persist failed: {exc}")
        return jsonify(snap)

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

    @app.route("/api/nexus/performance-report")
    def nexus_performance_report():
        from tools.research.performance_report import build_performance_report

        return jsonify(build_performance_report(runtime_store))

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
                snapshot = None
                try:
                    from backend.services.nexus_runtime import nexus_runtime

                    nexus_runtime.refresh_live_exchange_state()
                    snapshot = nexus_runtime.snapshot()
                    runtime_store.save_snapshot(
                        snapshot,
                        worker_status="ONLINE",
                        writer="ws_push",
                        single_instance=False,
                    )
                except Exception as exc:
                    print(f"[ws] live exchange refresh failed: {exc}")
                if snapshot is None:
                    snapshot = runtime_store.load_snapshot()
                payload = {"snapshot": snapshot}
                encoded = json.dumps(payload, ensure_ascii=False)
                if encoded != last_sent:
                    ws.send(encoded)
                    last_sent = encoded
                else:
                    ws.send(json.dumps({"heartbeat": True}, ensure_ascii=False))
                time.sleep(WS_PUSH_INTERVAL_SECONDS)
    else:
        print("[nexus] flask-sock not installed; REST polling remains available.")

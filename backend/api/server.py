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
from backend.runtime.embed_flags import embedded_worker_error, embedded_worker_started


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
        snap = runtime_store.load_snapshot()
        system = snap.get("system") or {}
        binance_sync = snap.get("binance_sync") or {}
        return jsonify(
            {
                "trading_mode": mode,
                "testnet_credentials_missing": missing,
                "runtime_db_path": resolve_runtime_db_path(),
                "embedded_worker_started": embedded_worker_started,
                "embedded_worker_error": embedded_worker_error,
                "snapshot_system_health": system.get("system_health"),
                "snapshot_worker_module": (system.get("module_health") or {}).get("worker"),
                "binance_sync_status": binance_sync.get("sync_status"),
                "hints": [
                    "If snapshot_system_health is WORKER_OFFLINE and embedded_worker_started is false, "
                    "set NEXUS_EMBEDDED_WORKER=1 or deploy on Zeabur (auto-detects ZEABUR_* IDs).",
                    "If testnet_credentials_missing is non-empty, add the four BINANCE_*_TESTNET_* keys in Zeabur Variables.",
                    "For the same DB as local, mount a volume at NEXUS_DATA_DIR and import a state bundle (see tools/deploy/ZEABUR_SETUP.zh-TW.md).",
                ],
            }
        )

    @app.route("/api/nexus/state")
    def nexus_state():
        return jsonify(runtime_store.load_snapshot())

    @app.route("/api/nexus/wallet")
    def nexus_wallet():
        snap = runtime_store.load_snapshot()
        return jsonify({"capital": snap.get("capital", {}), "loans": snap.get("loans", {}), "pnl": snap.get("pnl", {})})

    @app.route("/api/nexus/positions")
    def nexus_positions():
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
                snapshot = runtime_store.load_snapshot()
                payload = {"snapshot": snapshot}
                encoded = json.dumps(payload, ensure_ascii=False)
                if encoded != last_sent:
                    ws.send(encoded)
                    last_sent = encoded
                else:
                    ws.send(json.dumps({"heartbeat": True}, ensure_ascii=False))
                time.sleep(2)
    else:
        print("[nexus] flask-sock not installed; REST polling remains available.")

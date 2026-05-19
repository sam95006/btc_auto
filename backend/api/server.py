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


_dialogue = None


def _dialogue_service():
    global _dialogue
    if _dialogue is None:
        _dialogue = StationDialogueService(StationChatLog(runtime_store))
    return _dialogue


def register_nexus_routes(app):
    @app.route("/nexus")
    def nexus_dashboard():
        return send_file(Path(app.root_path) / "templates" / "nexus_command.html")

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

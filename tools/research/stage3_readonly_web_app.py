#!/usr/bin/env python3
"""Minimal read-only Flask app for Stage 3 Bybit demo learning dashboard."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

app = Flask(__name__, template_folder=str(ROOT / "templates"))


def _port() -> int:
    for key in ("PORT", "WEB_PORT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                pass
    return 8080


@app.before_request
def _read_only_guard():
    if request.method != "GET":
        if request.path in {"/api/nexus/state", "/api/nexus/status", "/api/nexus/snapshot"}:
            return jsonify({"read_only": True, "error": "method_not_allowed"}), 405
        if request.path.startswith("/api/nexus/stage3/"):
            return jsonify({"read_only": True, "error": "method_not_allowed"}), 405
        if request.path.startswith("/api/"):
            return jsonify({"read_only": True, "error": "method_not_allowed"}), 405


@app.after_request
def _nexus_static_cache_control(response):
    if request.path.startswith("/static/nexus/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@app.route("/health")
def health():
    return jsonify({"ok": True, "service": "stage3-readonly-web", "read_only": True})


def _legacy_compat_payload() -> dict:
    from backend.monitoring.stage3_status_service import build_stage3_context

    try:
        stage3 = build_stage3_context()
    except Exception as exc:
        stage3 = {"read_only": True, "error": str(exc), "data_available": False}
    return {
        "ok": True,
        "read_only": True,
        "mode": "stage3_demo_learning",
        "legacy_compat": True,
        "stage3": stage3,
    }


@app.route("/api/nexus/state")
@app.route("/api/nexus/status")
@app.route("/api/nexus/snapshot")
def nexus_legacy_compat():
    return jsonify(_legacy_compat_payload())


@app.route("/")
def root():
    return render_template("nexus_command.html")


@app.route("/nexus")
def nexus_page():
    return render_template("nexus_command.html")


@app.route("/static/nexus/<path:filename>")
def nexus_static(filename: str):
    static_root = ROOT / "static" / "nexus"
    target = (static_root / filename).resolve()
    if not str(target).startswith(str(static_root.resolve())):
        abort(404)
    if not target.is_file():
        abort(404)
    return send_from_directory(static_root, filename)


@app.route("/api/nexus/stage3/status")
def stage3_status():
    from backend.monitoring.stage3_status_service import build_stage3_context

    try:
        return jsonify(build_stage3_context())
    except Exception as exc:
        return jsonify({"read_only": True, "error": str(exc), "data_available": False}), 500


@app.route("/api/nexus/stage3/summary")
def stage3_summary():
    from backend.monitoring.stage3_status_service import build_stage3_summary

    try:
        payload = build_stage3_summary()
        payload["read_only"] = True
        return jsonify(payload)
    except Exception as exc:
        return jsonify({"read_only": True, "error": str(exc)}), 500


@app.route("/api/nexus/stage3/account")
def stage3_account():
    from backend.monitoring.stage3_status_service import build_stage3_account

    try:
        return jsonify(build_stage3_account())
    except Exception as exc:
        return jsonify({"read_only": True, "error": str(exc)}), 500


@app.route("/api/nexus/stage3/trades")
def stage3_trades():
    limit = min(500, max(1, int(request.args.get("limit", 50))))
    from backend.monitoring.stage3_status_service import build_stage3_trades

    try:
        return jsonify(build_stage3_trades(limit=limit))
    except Exception as exc:
        return jsonify({"read_only": True, "error": str(exc)}), 500


@app.route("/api/nexus/stage3/learning")
def stage3_learning():
    limit = min(500, max(1, int(request.args.get("limit", 50))))
    from backend.monitoring.stage3_status_service import build_stage3_learning

    try:
        return jsonify(build_stage3_learning(limit=limit))
    except Exception as exc:
        return jsonify({"read_only": True, "error": str(exc)}), 500


@app.route("/api/nexus/stage3/log-tail")
def stage3_log_tail():
    lines = min(200, max(1, int(request.args.get("lines", 80))))
    from backend.monitoring.stage3_status_service import build_stage3_log_tail

    try:
        return jsonify(build_stage3_log_tail(lines=lines))
    except Exception as exc:
        return jsonify({"read_only": True, "error": str(exc)}), 500


def main() -> None:
    port = _port()
    bind = f"0.0.0.0:{port}"
    use_gunicorn = any(
        os.environ.get(key)
        for key in ("ZEABUR", "ZEABUR_SERVICE_ID", "ZEABUR_PROJECT_ID", "ZEABUR_ENVIRONMENT")
    )
    if use_gunicorn:
        try:
            os.execvp(
                "gunicorn",
                [
                    "gunicorn",
                    "-b",
                    bind,
                    "-w",
                    "1",
                    "--timeout",
                    "120",
                    "tools.research.stage3_readonly_web_app:app",
                ],
            )
        except OSError:
            pass
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    main()

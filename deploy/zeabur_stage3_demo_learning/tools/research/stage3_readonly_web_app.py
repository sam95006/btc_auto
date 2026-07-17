#!/usr/bin/env python3
"""Minimal read-only Flask app for Stage 3 + Operator Market Intelligence UI.

Serves:
  /              -> frontend Market Intelligence SPA (static/operator_ui) when present
  /nexus         -> legacy Stage 3 space-station command UI
  /api/...       -> Stage 3 read-only APIs
  /static/nexus  -> legacy assets

UI-DEPLOY-1: ROOT_ROUTE previously served nexus_command.html only; that is why Zeabur
showed the old UI while Cursor evolved frontend/.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

from backend.api.operator_ui_cache import apply_operator_ui_cache_headers, is_operator_ui_html_path
from backend.api.market_public_routes import register_market_public_routes
from backend.api.market_scanner_routes import register_market_scanner_routes

app = Flask(__name__, template_folder=str(ROOT / "templates"))

OPERATOR_UI_DIR = ROOT / "static" / "operator_ui"
OPERATOR_BUILD_MARKER = "NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE1_MARKET_SCANNER"
MVP22C_BUILD_MARKER = "NEXUS_UI_MVP22C_MARKET_ANOMALY_RADAR"
MVP22B_BUILD_MARKER = "NEXUS_UI_MVP22B_DERIVATIVES_CONTEXT"
MVP22A_BUILD_MARKER = "NEXUS_UI_MVP22A_LIVE_MARKET_DATA"
LEGACY_BUILD_MARKER = "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60"

# Client-side React routes that must fall back to SPA index.html
_SPA_PREFIXES = (
    "overview",
    "scanner",
    "market",
    "anomalies",
    "anomaly-outcomes",
    "fleets",
    "signals",
    "risk-evidence",
    "evidence",
    "reflection",
    "provider-shadow",
    "paper-lab",
    "assistant",
    "academy",
    "calculator",
    "membership",
)


def _port() -> int:
    for key in ("PORT", "WEB_PORT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            try:
                return max(1, int(raw))
            except ValueError:
                pass
    return 8080


def _operator_ui_ready() -> bool:
    return (OPERATOR_UI_DIR / "index.html").is_file()


def _operator_index():
    return send_from_directory(OPERATOR_UI_DIR, "index.html")


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
    if request.path.startswith("/assets/") or is_operator_ui_html_path(
        request.path, _SPA_PREFIXES
    ):
        response = apply_operator_ui_cache_headers(
            response, request.path, spa_prefixes=_SPA_PREFIXES
        )
    if request.path.startswith("/api/market/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


register_market_public_routes(app)
register_market_scanner_routes(app)


@app.route("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "service": "stage3-readonly-web",
            "read_only": True,
            "operator_ui_ready": _operator_ui_ready(),
            "operator_ui_dir": str(OPERATOR_UI_DIR),
            "build_marker": OPERATOR_BUILD_MARKER,
            "root_serves": "operator_ui" if _operator_ui_ready() else "legacy_nexus",
        }
    )


@app.route("/api/nexus/ui-build")
def ui_build():
    meta_path = OPERATOR_UI_DIR / "operator_ui_build.json"
    payload = {
        "ok": True,
        "read_only": True,
        "operator_ui_ready": _operator_ui_ready(),
        "build_marker": OPERATOR_BUILD_MARKER,
        "buildMarker": OPERATOR_BUILD_MARKER,
        "mvp22c_build_marker": MVP22C_BUILD_MARKER,
        "mvp22b_build_marker": MVP22B_BUILD_MARKER,
        "mvp22a_build_marker": MVP22A_BUILD_MARKER,
        "legacy_build_marker": LEGACY_BUILD_MARKER,
        "ui_style": "Live Market Intelligence",
        "ui_version": "MVP-22D",
        "public_name": "NEXUS — Live Market Intelligence",
        "legacy_nexus_path": "/nexus",
    }
    if meta_path.is_file():
        try:
            import json

            payload["sync_meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception as exc:
            payload["sync_meta_error"] = str(exc)
    return jsonify(payload)


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
        "operator_ui_ready": _operator_ui_ready(),
        "build_marker": OPERATOR_BUILD_MARKER,
        "stage3": stage3,
    }


@app.route("/api/nexus/state")
@app.route("/api/nexus/status")
@app.route("/api/nexus/snapshot")
def nexus_legacy_compat():
    return jsonify(_legacy_compat_payload())


@app.route("/")
def root():
    if _operator_ui_ready():
        return _operator_index()
    return render_template("nexus_command.html")


@app.route("/nexus")
def nexus_page():
    """Legacy Stage 3 space-station command UI (kept for rollback / ops)."""
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


@app.route("/assets/<path:filename>")
def operator_assets(filename: str):
    if not _operator_ui_ready():
        abort(404)
    target = (OPERATOR_UI_DIR / "assets" / filename).resolve()
    assets_root = (OPERATOR_UI_DIR / "assets").resolve()
    if not str(target).startswith(str(assets_root)):
        abort(404)
    if not target.is_file():
        abort(404)
    return send_from_directory(assets_root, filename)


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


@app.route("/<path:path>")
def spa_or_static_fallback(path: str):
    """SPA history fallback for Market Intelligence routes."""
    if path.startswith("api/") or path.startswith("static/"):
        abort(404)
    if path == "nexus" or path.startswith("nexus/"):
        return render_template("nexus_command.html")
    if not _operator_ui_ready():
        abort(404)
    # Prefer real files under operator_ui (e.g. favicon)
    candidate = (OPERATOR_UI_DIR / path).resolve()
    if str(candidate).startswith(str(OPERATOR_UI_DIR.resolve())) and candidate.is_file():
        return send_from_directory(OPERATOR_UI_DIR, path)
    first = path.split("/", 1)[0]
    if first in _SPA_PREFIXES or path == "index.html":
        return _operator_index()
    abort(404)


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

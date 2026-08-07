"""Serve Market Intelligence SPA from static/operator_ui (UI-DEPLOY-2).

Read-only static routing only. Does not touch trading / orders / ARM.
"""
from __future__ import annotations

from pathlib import Path

from flask import abort, jsonify, request, send_from_directory

from backend.api.operator_ui_cache import apply_operator_ui_cache_headers, is_operator_ui_html_path

OPERATOR_BUILD_MARKER = "PUBLIC_V18_2_9_HUMAN_PRODUCT_EXPERIENCE_HEAD"
PHASE4_BUILD_MARKER = "NEXUS_UI_PRODUCT_AND_INTELLIGENCE_PHASE4"
PHASE3_BUILD_MARKER = "NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE3_SECTOR_CHART_EQUITIES"
PHASE2_BUILD_MARKER = "NEXUS_UI_PRODUCT_TRANSFORMATION_PHASE2_DECISION_EXPERIENCE"
MVP22C_BUILD_MARKER = "NEXUS_UI_MVP22C_MARKET_ANOMALY_RADAR"
MVP22B_BUILD_MARKER = "NEXUS_UI_MVP22B_DERIVATIVES_CONTEXT"
MVP22A_BUILD_MARKER = "NEXUS_UI_MVP22A_LIVE_MARKET_DATA"
LEGACY_BUILD_MARKER = "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60"
_SPA_PREFIXES = (
    "overview",
    "universe",
    "opportunities",
    "alerts",
    "portfolio",
    "anomalies",
    "intelligence",
    "trade-plan",
    "performance",
    "learning",
    "scanner",
    "market",
    "watchlist",
    "crypto",
    "equities",
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
    "ai-reviews",
    "research-performance",
    "global-shadow",
    "ai-learning-lab",
    "founder",
    "preview",
    "account",
    "organization",
    "member-platform",
)


def _operator_ui_dir(app) -> Path:
    return Path(app.root_path) / "static" / "operator_ui"


def operator_ui_ready(app) -> bool:
    return (_operator_ui_dir(app) / "index.html").is_file()


def register_operator_ui_routes(app) -> None:
    """Mount SPA at / when static/operator_ui is present; leave /nexus for legacy."""

    @app.after_request
    def _operator_ui_cache_control(response):
        if request.path.startswith("/static/nexus/"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            return response
        if request.path.startswith("/assets/") or is_operator_ui_html_path(
            request.path, _SPA_PREFIXES
        ):
            return apply_operator_ui_cache_headers(
                response, request.path, spa_prefixes=_SPA_PREFIXES
            )
        if request.path.startswith("/api/market/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    def _index():
        return send_from_directory(_operator_ui_dir(app), "index.html")

    @app.route("/api/nexus/ui-build")
    def nexus_ui_build():
        ui_dir = _operator_ui_dir(app)
        meta_path = ui_dir / "operator_ui_build.json"
        payload = {
            "ok": True,
            "read_only": True,
            "operator_ui_ready": operator_ui_ready(app),
            "build_marker": OPERATOR_BUILD_MARKER,
            "buildMarker": OPERATOR_BUILD_MARKER,
            "phase4_build_marker": PHASE4_BUILD_MARKER,
            "mvp22c_build_marker": MVP22C_BUILD_MARKER,
            "mvp22b_build_marker": MVP22B_BUILD_MARKER,
            "mvp22a_build_marker": MVP22A_BUILD_MARKER,
            "legacy_build_marker": LEGACY_BUILD_MARKER,
            "ui_style": "Product Simple View · Evidence-first",
            "ui_version": "PRODUCT-7",
            "public_name": "NEXUS — Live Market Intelligence",
            "legacy_nexus_path": "/nexus",
            "served_by": "nexus-web",
        }
        if meta_path.is_file():
            try:
                import json

                payload["sync_meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception as exc:
                payload["sync_meta_error"] = str(exc)
        return jsonify(payload)

    @app.route("/assets/<path:filename>")
    def operator_ui_assets(filename: str):
        if not operator_ui_ready(app):
            abort(404)
        assets_root = (_operator_ui_dir(app) / "assets").resolve()
        target = (assets_root / filename).resolve()
        if not str(target).startswith(str(assets_root)) or not target.is_file():
            abort(404)
        return send_from_directory(assets_root, filename)

    @app.route("/<path:path>")
    def operator_ui_spa_fallback(path: str):
        if path.startswith("api/") or path.startswith("static/"):
            abort(404)
        if path == "nexus" or path.startswith("nexus/"):
            abort(404)
        if not operator_ui_ready(app):
            abort(404)
        ui_dir = _operator_ui_dir(app)
        candidate = (ui_dir / path).resolve()
        if str(candidate).startswith(str(ui_dir.resolve())) and candidate.is_file():
            return send_from_directory(ui_dir, path)
        first = path.split("/", 1)[0]
        if first in _SPA_PREFIXES or path == "index.html":
            return _index()
        abort(404)

"""Serve Market Intelligence SPA from static/operator_ui (UI-DEPLOY-2).

Read-only static routing only. Does not touch trading / orders / ARM.
"""
from __future__ import annotations

from pathlib import Path

from flask import abort, jsonify, send_from_directory

OPERATOR_BUILD_MARKER = "NEXUS_UI_MVP22A_LIVE_MARKET_DATA"
LEGACY_BUILD_MARKER = "NEXUS_UI_MVP19_MARKET_INTELLIGENCE_76e8b60"
_SPA_PREFIXES = (
    "overview",
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


def _operator_ui_dir(app) -> Path:
    return Path(app.root_path) / "static" / "operator_ui"


def operator_ui_ready(app) -> bool:
    return (_operator_ui_dir(app) / "index.html").is_file()


def register_operator_ui_routes(app) -> None:
    """Mount SPA at / when static/operator_ui is present; leave /nexus for legacy."""

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
            "legacy_build_marker": LEGACY_BUILD_MARKER,
            "ui_style": "Live Market Intelligence",
            "ui_version": "MVP-22A",
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

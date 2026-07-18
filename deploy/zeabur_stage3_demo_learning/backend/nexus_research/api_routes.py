"""Flask routes for NEXUS Phase 5 Gate B — All-Market AI Review.

All endpoints: researchOnly=true, private_api=false, no secrets.
Cache-Control: no-store on all responses.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from flask import Blueprint, jsonify, request

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)


def _no_store(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def _err(msg: str, code: int = 500):
    resp = jsonify({"ok": False, "error": msg, "researchOnly": True})
    _no_store(resp)
    return resp, code


nexus_research_bp = Blueprint("nexus_research", __name__)


@nexus_research_bp.route("/api/nexus/runtime/status")
def runtime_status():
    try:
        from backend.nexus_research.runtime_supervisor import get_supervisor
        data = get_supervisor().status()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/events/status")
def events_status():
    try:
        from backend.nexus_research.domain_events import get_event_bus
        data = get_event_bus().status()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/review-cases")
def list_review_cases():
    try:
        from backend.nexus_research.review_cases import get_review_case_manager
        status_filter = request.args.get("status")
        symbol_filter = request.args.get("symbol")
        limit = min(int(request.args.get("limit", 50)), 200)
        mgr = get_review_case_manager()
        cases = mgr.list_cases(status=status_filter, symbol=symbol_filter, limit=limit)
        data = {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "cases": cases,
            "count": len(cases),
            "generatedAt": int(time.time() * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/review-cases/status")
def review_cases_status():
    try:
        from backend.nexus_research.review_cases import get_review_case_manager
        data = get_review_case_manager().status_summary()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/review-cases/<case_id>")
def get_review_case(case_id: str):
    try:
        from backend.nexus_research.review_cases import get_review_case_manager
        case = get_review_case_manager().get_case(case_id)
        if case is None:
            return _err("case not found", 404)
        payload = case.to_dict()
        decision = payload.get("decision") or {}
        assessments = decision.get("assessments") or []
        data = {
            "ok": True,
            "researchOnly": True,
            "case": payload,
            "roleAssessments": assessments,
            "decisionStatus": decision.get("decisionStatus"),
            "analysisMode": decision.get("analysisMode") or "RULES",
            "fabricatedChat": False,
        }
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/ai-reviews/status")
def ai_reviews_status():
    try:
        from backend.nexus_research.ai_review_cycle import get_ai_review_scheduler
        data = get_ai_review_scheduler().status()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/ai-reviews/sessions")
def ai_reviews_sessions():
    try:
        from backend.nexus_research.ai_review_cycle import get_ai_review_scheduler
        limit = min(int(request.args.get("limit", 20)), 100)
        sessions = get_ai_review_scheduler().list_sessions(limit=limit)
        data = {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "sessions": sessions,
            "count": len(sessions),
            "generatedAt": int(time.time() * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/ai-reviews/sessions/<session_id>")
def get_ai_review_session(session_id: str):
    try:
        from backend.nexus_research.ai_review_cycle import get_ai_review_scheduler
        session = get_ai_review_scheduler().get_session(session_id)
        if session is None:
            return _err("session not found", 404)
        data = {"ok": True, "researchOnly": True, "session": session}
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/decisions/status")
def decisions_status():
    try:
        from backend.nexus_research.storage import get_research_store
        store = get_research_store()
        decisions = store.query("research_decisions", limit=50)
        data = {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "recentDecisions": decisions,
            "count": len(decisions),
            "generatedAt": int(time.time() * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


def register_nexus_research_routes(app: "Flask") -> None:
    """Register all Phase 5 Gate B routes."""
    app.register_blueprint(nexus_research_bp)
    logger.info("[nexus_research] Phase 5 Gate B routes registered")

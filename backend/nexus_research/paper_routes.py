"""Flask routes for NEXUS Phase 6 Gate C — Paper Runtime API.

All endpoints: researchOnly=true, privateApi=false, Cache-Control: no-store.
No private API keys, no real orders, no real positions.

GET endpoints (read-only):
  /api/nexus/paper/status       — controller + mode + runtime state
  /api/nexus/paper/policy       — simulation policy audit + defaults
  /api/nexus/paper/cycles       — recent paper controller cycle records
  /api/nexus/paper/exits        — recent exit policy records
  /api/nexus/paper/shadow-runs  — recent SHADOW dry-run records

POST endpoints (research-only, researchOnly guard required):
  /api/nexus/paper/manual-close
    body: {researchOnly: true, positionId: string}
    Queue a sim position for manual research close on next controller tick.

  /api/nexus/ai-reviews/manual-validation
    body: {researchOnly: true}
    Trigger a manual AI review cycle session (tag: MANUAL_RESEARCH_VALIDATION).

  /api/nexus/review-cases/manual-research
    query: ?symbol=<BTCUSDT>
    Create a MANUAL_RESEARCH review case from live scanner candidate snapshot.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from flask import Blueprint, jsonify, request

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

_RESEARCH_ONLY_HEADERS = {"X-Research-Only": "true", "X-Private-Api": "false"}


def _no_store(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Research-Only"] = "true"
    response.headers["X-Private-Api"] = "false"
    return response


def _ok(data: dict) -> tuple:
    data.setdefault("researchOnly", True)
    data.setdefault("privateApi", False)
    return _no_store(jsonify(data)), 200


def _err(msg: str, code: int = 500) -> tuple:
    resp = jsonify({"ok": False, "error": msg, "researchOnly": True})
    return _no_store(resp), code


nexus_paper_bp = Blueprint("nexus_paper", __name__)


# ── GET: paper controller status ──────────────────────────────────────────────

@nexus_paper_bp.route("/api/nexus/paper/status")
def paper_status():
    try:
        from backend.nexus_research.paper_controller import get_paper_controller
        return _ok(get_paper_controller().status())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_paper_bp.route("/api/nexus/paper/policy")
def paper_policy():
    try:
        from backend.nexus_research.simulation_policy import get_simulation_policy
        return _ok(get_simulation_policy().status())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_paper_bp.route("/api/nexus/paper/cycles")
def paper_cycles():
    try:
        from backend.nexus_research.paper_controller import get_paper_controller
        limit = min(int(request.args.get("limit", 10)), 50)
        cycles = get_paper_controller().list_recent_cycles(limit=limit)
        return _ok({
            "ok": True,
            "cycles": cycles,
            "count": len(cycles),
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_paper_bp.route("/api/nexus/paper/exits")
def paper_exits():
    try:
        from backend.nexus_research.exit_policies import get_exit_policy_engine
        limit = min(int(request.args.get("limit", 50)), 200)
        exit_engine = get_exit_policy_engine()
        exits = exit_engine.list_exits(limit=limit)
        return _ok({
            "ok": True,
            "exits": exits,
            "count": len(exits),
            "status": exit_engine.status(),
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_paper_bp.route("/api/nexus/paper/shadow-runs")
def paper_shadow_runs():
    try:
        from backend.nexus_research.storage import get_research_store
        limit = min(int(request.args.get("limit", 50)), 200)
        runs = get_research_store().query("paper_shadow_runs", limit=limit)
        return _ok({
            "ok": True,
            "shadowRuns": runs,
            "count": len(runs),
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ── POST: manual close ────────────────────────────────────────────────────────

@nexus_paper_bp.route("/api/nexus/paper/manual-close", methods=["POST"])
def paper_manual_close():
    """Queue a sim position for manual research close.

    Body: {researchOnly: true, positionId: "<id>"}
    The controller exits the position on its next tick.
    """
    try:
        body = request.get_json(silent=True) or {}
        if not body.get("researchOnly"):
            return _err("researchOnly:true required in request body", 400)
        position_id = str(body.get("positionId") or "").strip()
        if not position_id:
            return _err("positionId required", 400)

        # Verify position exists in simulator
        from backend.nexus_research.simulator import get_simulator
        sim = get_simulator()
        open_positions = sim.list_open_positions()
        pos_ids = {p.get("positionId") for p in open_positions}
        if position_id not in pos_ids:
            return _err(f"position {position_id!r} not found in open positions", 404)

        from backend.nexus_research.exit_policies import get_exit_policy_engine
        get_exit_policy_engine().queue_manual_close(position_id)

        return _ok({
            "ok": True,
            "positionId": position_id,
            "queued": True,
            "note": "Position queued for manual research close on next controller tick",
            "researchOnly": True,
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ── POST: manual AI review validation ─────────────────────────────────────────

@nexus_paper_bp.route("/api/nexus/ai-reviews/manual-validation", methods=["POST"])
def ai_reviews_manual_validation():
    """Trigger a manual AI review cycle session.

    Body: {researchOnly: true}
    Tag: MANUAL_RESEARCH_VALIDATION
    """
    try:
        body = request.get_json(silent=True) or {}
        if not body.get("researchOnly"):
            return _err("researchOnly:true required in request body", 400)

        from backend.nexus_research.ai_review_cycle import get_ai_review_scheduler
        scheduler = get_ai_review_scheduler()
        session_id = scheduler.trigger_manual()

        session = scheduler.get_session(session_id)

        return _ok({
            "ok": True,
            "sessionId": session_id,
            "tag": "MANUAL_RESEARCH_VALIDATION",
            "session": session,
            "researchOnly": True,
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ── POST: manual research case from scanner snapshot ──────────────────────────

@nexus_paper_bp.route("/api/nexus/review-cases/manual-research", methods=["POST"])
def review_cases_manual_research():
    """Create a MANUAL_RESEARCH review case using live candidate snapshot from scanner.

    Query param: ?symbol=BTCUSDT
    Uses LIVE candidate snapshot from scanner (real public data only).
    Trigger: MANUAL_RESEARCH
    """
    try:
        symbol = (request.args.get("symbol") or "").strip().upper()
        if not symbol:
            return _err("symbol query param required", 400)

        # Load live candidate snapshot from scanner (public data only)
        candidate_snapshot: dict = {
            "symbol": symbol,
            "score": 60.0,
            "side": "LONG",
            "stage": "MANUAL",
            "source": "manual_research",
            "createdAtMs": int(time.time() * 1000),
            "researchOnly": True,
        }
        try:
            from backend.market.scanner.scanner_service import get_market_scanner
            scanner = get_market_scanner()
            candidates = scanner.get_candidates() if hasattr(scanner, "get_candidates") else []
            for c in candidates:
                sym = c.get("symbol") or c.get("ticker")
                if str(sym).upper() == symbol:
                    candidate_snapshot.update({
                        "score": c.get("score", 60.0),
                        "side": c.get("side", "LONG"),
                        "stage": c.get("stage", "MANUAL"),
                        "price": c.get("price") or c.get("lastPrice"),
                        "volume": c.get("volume"),
                        "liveSnapshot": True,
                    })
                    break
        except Exception as exc:  # noqa: BLE001
            candidate_snapshot["scannerError"] = str(exc)
            candidate_snapshot["liveSnapshot"] = False

        from backend.nexus_research.review_cases import (
            get_review_case_manager,
            TRIGGER_MANUAL_RESEARCH,
        )
        mgr = get_review_case_manager()
        direction = candidate_snapshot.get("side", "LONG")
        case = mgr.create_case(
            symbol=symbol,
            direction=direction,
            trigger=TRIGGER_MANUAL_RESEARCH,
            window="1h",
            candidate_snapshot=candidate_snapshot,
        )

        if case is None:
            return _ok({
                "ok": True,
                "caseId": None,
                "note": "Case not created (cooldown active or max active cases reached)",
                "symbol": symbol,
                "researchOnly": True,
                "generatedAt": int(time.time() * 1000),
            })

        return _ok({
            "ok": True,
            "caseId": case.case_id,
            "symbol": symbol,
            "trigger": TRIGGER_MANUAL_RESEARCH,
            "direction": direction,
            "candidateSnapshot": candidate_snapshot,
            "researchOnly": True,
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


def register_paper_routes(app: "Flask") -> None:
    """Register all Phase 6 Gate C paper runtime routes."""
    app.register_blueprint(nexus_paper_bp)
    # Add POST endpoints to stage3_readonly_web_app allowlist dynamically
    _update_stage3_allowlist(app)
    logger.info("[nexus_paper] Phase 6 Gate C paper routes registered")


def _update_stage3_allowlist(app: "Flask") -> None:
    """Extend the stage3 POST allowlist with paper routes if applicable."""
    try:
        import sys
        # Find the stage3_readonly_web_app module if loaded
        module = sys.modules.get("tools.research.stage3_readonly_web_app")
        if module is None:
            return
        allowlist = getattr(module, "_GATE_C_POST_ALLOWLIST", None)
        if isinstance(allowlist, set):
            allowlist.add("/api/nexus/paper/manual-close")
            allowlist.add("/api/nexus/ai-reviews/manual-validation")
            allowlist.add("/api/nexus/review-cases/manual-research")
    except Exception as exc:  # noqa: BLE001
        logger.debug("[nexus_paper] could not update stage3 allowlist: %s", exc)

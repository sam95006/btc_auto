"""Flask routes for NEXUS Phase 5 Gate C — Simulator / Risk / Reflection / Replay.

All endpoints: researchOnly=true, privateApi=false, Cache-Control: no-store.
No private API keys, no real orders, no real positions.

GET endpoints (safe, read-only status):
  /api/nexus/simulator/status
  /api/nexus/simulator/orders
  /api/nexus/simulator/positions
  /api/nexus/simulator/ledger
  /api/nexus/risk/status
  /api/nexus/risk/history
  /api/nexus/replay/status
  /api/nexus/replay/sessions/<session_id>
  /api/nexus/reflection/status
  /api/nexus/reflection/records
  /api/nexus/patch/status
  /api/nexus/patch/proposals
  /api/nexus/soak/status
  /api/nexus/soak/results

POST endpoints (research-only internal helpers, marked researchOnly):
  POST /api/nexus/simulator/order  — test helper only, researchOnly guard
  POST /api/nexus/soak/run         — trigger smoke soak, researchOnly guard
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from flask import Blueprint, jsonify, request

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

_RESEARCH_ONLY_HEADER = {"X-Research-Only": "true", "X-Private-Api": "false"}


def _no_store(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Research-Only"] = "true"
    response.headers["X-Private-Api"] = "false"
    return response


def _ok(data: dict) -> tuple:
    data.setdefault("researchOnly", True)
    data.setdefault("privateApi", False)
    resp = jsonify(data)
    return _no_store(resp), 200


def _err(msg: str, code: int = 500) -> tuple:
    resp = jsonify({"ok": False, "error": msg, "researchOnly": True})
    _no_store(resp)
    return resp, code


nexus_sim_bp = Blueprint("nexus_gate_c", __name__)


# ── Simulator ─────────────────────────────────────────────────────────────────

@nexus_sim_bp.route("/api/nexus/simulator/status")
def sim_status():
    try:
        from backend.nexus_research.simulator import get_simulator
        return _ok(get_simulator().status())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_sim_bp.route("/api/nexus/simulator/orders")
def sim_orders():
    try:
        from backend.nexus_research.simulator import get_simulator
        sim = get_simulator()
        symbol = request.args.get("symbol")
        state = request.args.get("state")
        limit = min(int(request.args.get("limit", 50)), 200)
        orders = sim.list_orders(symbol=symbol, state=state, limit=limit)
        return _ok({
            "ok": True,
            "orders": orders,
            "count": len(orders),
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_sim_bp.route("/api/nexus/simulator/positions")
def sim_positions():
    try:
        from backend.nexus_research.simulator import get_simulator
        sim = get_simulator()
        symbol = request.args.get("symbol")
        include_closed = request.args.get("closed", "false").lower() == "true"
        limit = min(int(request.args.get("limit", 50)), 200)
        open_pos = sim.list_open_positions(symbol=symbol)
        result: dict = {
            "ok": True,
            "openPositions": open_pos,
            "openCount": len(open_pos),
            "unrealisedPnl": sim.total_unrealised_pnl(),
            "generatedAt": int(time.time() * 1000),
        }
        if include_closed:
            closed_pos = sim.list_closed_positions(symbol=symbol, limit=limit)
            result["closedPositions"] = closed_pos
            result["closedCount"] = len(closed_pos)
            result["realisedPnl"] = sim.total_realised_pnl()
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_sim_bp.route("/api/nexus/simulator/ledger")
def sim_ledger():
    try:
        from backend.nexus_research.sim_ledger import get_sim_ledger
        from backend.nexus_research.simulator import get_simulator
        ledger = get_sim_ledger()
        sim = get_simulator()
        unrealised = sim.total_unrealised_pnl()
        limit = min(int(request.args.get("limit", 50)), 200)
        event_type_filter = request.args.get("eventType")
        snap = ledger.snapshot(unrealised_pnl=unrealised)
        events = ledger.recent_events(limit=limit, event_type=event_type_filter)
        return _ok({
            "ok": True,
            "snapshot": snap,
            "recentEvents": events,
            "eventCount": len(events),
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ── Research-only POST: submit a test order (guarded) ─────────────────────────

@nexus_sim_bp.route("/api/nexus/simulator/order", methods=["POST"])
def sim_submit_order():
    """POST — research-only test helper. Guarded by researchOnly check."""
    try:
        from backend.nexus_research.simulator import (
            get_simulator, ORDER_MARKET, ORDER_LIMIT, SIDE_LONG, SIDE_SHORT,
        )
        body = request.get_json(silent=True) or {}

        # Explicit researchOnly guard: reject if caller doesn't acknowledge
        if not body.get("researchOnly"):
            return _err("researchOnly:true required in request body", 400)

        symbol = str(body.get("symbol", "BTCUSDT"))
        side = str(body.get("side", SIDE_LONG))
        order_type = str(body.get("orderType", ORDER_MARKET))
        qty = float(body.get("qty", 0.001))
        limit_price = body.get("limitPrice")
        leverage = float(body.get("leverage", 5.0))

        if side not in (SIDE_LONG, SIDE_SHORT):
            return _err(f"invalid side: {side!r}", 400)
        if order_type not in (ORDER_MARKET, ORDER_LIMIT):
            return _err(f"invalid orderType: {order_type!r}", 400)
        if qty <= 0:
            return _err("qty must be positive", 400)

        sim = get_simulator()
        order_id = sim.submit_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=qty,
            limit_price=float(limit_price) if limit_price is not None else None,
            leverage=leverage,
        )
        return _ok({
            "ok": True,
            "orderId": order_id,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
            "researchOnly": True,
            "note": "simulated order only — no real exchange interaction",
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ── Risk ──────────────────────────────────────────────────────────────────────

@nexus_sim_bp.route("/api/nexus/risk/status")
def risk_status():
    try:
        from backend.nexus_research.risk_engine import get_risk_engine
        return _ok(get_risk_engine().status())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ── Replay ────────────────────────────────────────────────────────────────────

@nexus_sim_bp.route("/api/nexus/replay/status")
def replay_status():
    try:
        from backend.nexus_research.replay import get_replay_engine
        return _ok(get_replay_engine().status())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_sim_bp.route("/api/nexus/replay/sessions/<session_id>")
def get_replay_session(session_id: str):
    try:
        from backend.nexus_research.replay import get_replay_engine
        session = get_replay_engine().get_session(session_id)
        if session is None:
            return _err("session not found", 404)
        return _ok({"ok": True, "session": session.status_dict()})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ── Reflection ────────────────────────────────────────────────────────────────

@nexus_sim_bp.route("/api/nexus/reflection/status")
def reflection_status():
    try:
        from backend.nexus_research.reflection import get_reflection_analyst
        return _ok(get_reflection_analyst().status())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_sim_bp.route("/api/nexus/reflection/records")
def reflection_records():
    try:
        from backend.nexus_research.reflection import get_reflection_analyst
        symbol = request.args.get("symbol")
        limit = min(int(request.args.get("limit", 50)), 200)
        records = get_reflection_analyst().list_reflections(symbol=symbol, limit=limit)
        return _ok({
            "ok": True,
            "records": records,
            "count": len(records),
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ── Patch governance ──────────────────────────────────────────────────────────

@nexus_sim_bp.route("/api/nexus/patch/status")
def patch_status():
    try:
        from backend.nexus_research.patch_governance import get_patch_governance
        return _ok(get_patch_governance().status())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_sim_bp.route("/api/nexus/patch/proposals")
def patch_proposals():
    try:
        from backend.nexus_research.patch_governance import get_patch_governance
        state_filter = request.args.get("state")
        symbol_filter = request.args.get("symbol")
        limit = min(int(request.args.get("limit", 50)), 200)
        proposals = get_patch_governance().list_proposals(
            state=state_filter, symbol=symbol_filter, limit=limit
        )
        return _ok({
            "ok": True,
            "proposals": proposals,
            "count": len(proposals),
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


# ── Soak ──────────────────────────────────────────────────────────────────────

@nexus_sim_bp.route("/api/nexus/soak/status")
def soak_status():
    try:
        from backend.nexus_research.soak import get_soak_framework
        return _ok(get_soak_framework().status())
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_sim_bp.route("/api/nexus/soak/results")
def soak_results():
    try:
        from backend.nexus_research.soak import get_soak_framework
        limit = min(int(request.args.get("limit", 10)), 50)
        results = get_soak_framework().list_results(limit=limit)
        return _ok({
            "ok": True,
            "results": results,
            "count": len(results),
            "generatedAt": int(time.time() * 1000),
        })
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


@nexus_sim_bp.route("/api/nexus/soak/run", methods=["POST"])
def soak_run():
    """POST — trigger an isolated smoke soak. Research-only guard required."""
    try:
        from backend.nexus_research.soak import get_soak_framework, SOAK_SMOKE
        body = request.get_json(silent=True) or {}

        if not body.get("researchOnly"):
            return _err("researchOnly:true required in request body", 400)

        profile = str(body.get("profile", SOAK_SMOKE))
        framework = get_soak_framework()
        result = framework.run_soak(profile=profile, isolated=True)
        return _ok({"ok": True, "result": result.to_dict()})
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))


def register_gate_c_routes(app: "Flask") -> None:
    """Register all Phase 5 Gate C routes."""
    app.register_blueprint(nexus_sim_bp)
    logger.info("[nexus_gate_c] Phase 5 Gate C routes registered")

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
        view = request.args.get("view")
        limit = min(int(request.args.get("limit", 50)), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
        mgr = get_review_case_manager()
        cases = mgr.list_cases(
            status=status_filter,
            symbol=symbol_filter,
            limit=limit,
            view=view,
            offset=offset,
        )
        data = {
            "ok": True,
            "researchOnly": True,
            "privateApi": False,
            "view": view or "default",
            "cases": cases,
            "count": len(cases),
            "offset": offset,
            "generatedAt": int(time.time() * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/review-cases/sweep", methods=["POST"])
def review_cases_sweep():
    try:
        from backend.nexus_research.review_cases import get_review_case_manager
        metrics = get_review_case_manager().lifecycle_sweep(persist=True)
        data = {"ok": True, "researchOnly": True, "privateApi": False, "sweep": metrics}
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/config/effective")
def config_effective():
    """Phase 6.2 — redacted effective research config (no secrets)."""
    try:
        from backend.nexus_research.config import get_effective_config
        from backend.nexus_research.storage import get_research_store, is_storage_integrity_healthy
        from backend.nexus_research.runtime_supervisor import get_supervisor
        from backend.nexus_research.review_cases import get_review_case_manager

        store = get_research_store()
        profile = store.sqlite_runtime_profile()
        st = store.status() if hasattr(store, "status") else {}
        supervisor = get_supervisor().status()
        cases = get_review_case_manager().status_summary()

        runtime_context = {
            "durableClaim": bool(st.get("durableClaim", True)),
            "restartProof": bool(st.get("restartProof", True)),
            "storageHealthy": is_storage_integrity_healthy(profile.get("integrity_check")),
            "runtimeOwnerCount": 1 if supervisor.get("supervisorRunning") else 0,
            "schedulerOwnerCount": 1 if supervisor.get("supervisorRunning") else 0,
            "scannerOwnerCount": 1,
            "ledgerOwnerCount": 1,
            "naturalActiveCapacityAvailable": int(cases.get("capacityAvailable") or 0) > 0,
            "ledgerHealthy": True,
            "riskEngineHealthy": True,
            "capitalAllocatorHealthy": True,
            "simulatorHealthy": True,
        }
        try:
            from backend.market.scanner.scanner_service import get_market_scanner
            runtime_context["scannerOwnerCount"] = (
                1 if get_market_scanner().status().get("ok") is not False else 0
            )
        except Exception:  # noqa: BLE001
            runtime_context["scannerOwnerCount"] = 0

        data = get_effective_config(refresh=True, runtime_context=runtime_context)
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


@nexus_research_bp.route("/api/nexus/storage/status")
def storage_status():
    """Phase 6 Gate B: storage mode, durability claim, migration version (no secrets)."""
    try:
        from backend.nexus_research.storage import get_research_store
        data = get_research_store().status()
        data.update({"researchOnly": True, "privateApi": False})
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/storage/discovery")
def storage_discovery():
    """Phase 6 Gate B: env presence check + recommended mode (no secrets/values)."""
    try:
        from backend.nexus_research.storage_discovery import discover_storage
        data = {**discover_storage(), "researchOnly": True, "privateApi": False}
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/storage/probes")
def storage_probes_list():
    """List recent persistence probes (read-only)."""
    try:
        from backend.nexus_research.persistence_validation import list_probes

        rows = list_probes(limit=20)
        data = {
            "ok": True,
            "count": len(rows),
            "probes": rows,
            "researchOnly": True,
            "privateApi": False,
            "generatedAt": int(time.time() * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/storage/probes", methods=["POST"])
def storage_probes_create():
    """Create a PersistenceProbe — internal validation contract only."""
    try:
        body = request.get_json(silent=True) or {}
        if not body.get("researchOnly"):
            data = {"ok": False, "error": "researchOnly:true required", "researchOnly": True}
            resp = jsonify(data)
            _no_store(resp)
            return resp, 400
        if body.get("contract") != "NEXUS_PHASE61_PERSISTENCE_VALIDATION_V1":
            data = {
                "ok": False,
                "error": "contract NEXUS_PHASE61_PERSISTENCE_VALIDATION_V1 required",
                "researchOnly": True,
            }
            resp = jsonify(data)
            _no_store(resp)
            return resp, 400
        if body.get("validationLabel") != "PERSISTENCE_VALIDATION":
            data = {
                "ok": False,
                "error": "validationLabel PERSISTENCE_VALIDATION required",
                "researchOnly": True,
            }
            resp = jsonify(data)
            _no_store(resp)
            return resp, 400
        # Reject arbitrary user payloads — only allow empty or fixed note key.
        extra = body.get("payload")
        if extra is not None and not isinstance(extra, dict):
            data = {"ok": False, "error": "payload must be object or omitted", "researchOnly": True}
            resp = jsonify(data)
            _no_store(resp)
            return resp, 400
        if isinstance(extra, dict):
            allowed = {"note", "packId"}
            if set(extra.keys()) - allowed:
                data = {
                    "ok": False,
                    "error": "payload keys limited to note, packId",
                    "researchOnly": True,
                }
                resp = jsonify(data)
                _no_store(resp)
                return resp, 400

        from backend.nexus_research.persistence_validation import create_persistence_probe

        probe = create_persistence_probe(payload=extra if isinstance(extra, dict) else None)
        data = {
            "ok": True,
            "probe": probe,
            "researchOnly": True,
            "privateApi": False,
            "generatedAt": int(time.time() * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/storage/persistence-validation", methods=["POST"])
def storage_persistence_validation():
    """Write PERSISTENCE_VALIDATION dataset + pre-restart snapshot (V1 or V2)."""
    try:
        body = request.get_json(silent=True) or {}
        if not body.get("researchOnly"):
            data = {"ok": False, "error": "researchOnly:true required", "researchOnly": True}
            resp = jsonify(data)
            _no_store(resp)
            return resp, 400
        contract = str(body.get("contract") or "")
        validation_type = str(body.get("validationType") or "")
        round_id = str(body.get("validationRound") or body.get("round") or "V1")

        if validation_type != "PERSISTENCE_VALIDATION":
            data = {
                "ok": False,
                "error": "validationType PERSISTENCE_VALIDATION required",
                "researchOnly": True,
            }
            resp = jsonify(data)
            _no_store(resp)
            return resp, 400

        if round_id in ("V2", "PHASE61_RESTART_PROOF_V2"):
            if contract != "NEXUS_PHASE61_PERSISTENCE_VALIDATION_V2":
                data = {
                    "ok": False,
                    "error": "contract NEXUS_PHASE61_PERSISTENCE_VALIDATION_V2 required for V2",
                    "researchOnly": True,
                }
                resp = jsonify(data)
                _no_store(resp)
                return resp, 400
            from backend.nexus_research.persistence_validation import (
                run_persistence_validation_pack_v2,
            )

            snap = run_persistence_validation_pack_v2()
        else:
            if contract != "NEXUS_PHASE61_PERSISTENCE_VALIDATION_V1":
                data = {
                    "ok": False,
                    "error": "contract NEXUS_PHASE61_PERSISTENCE_VALIDATION_V1 required",
                    "researchOnly": True,
                }
                resp = jsonify(data)
                _no_store(resp)
                return resp, 400
            from backend.nexus_research.persistence_validation import (
                run_persistence_validation_pack,
            )

            snap = run_persistence_validation_pack()

        data = {
            "ok": True,
            "snapshot": snap,
            "readyForControlledRestart": bool(
                snap.get("readyForControlledRestart")
                or snap.get("readyForSecondControlledRestart")
            ),
            "researchOnly": True,
            "privateApi": False,
            "paperModeEnabled": False,
            "generatedAt": int(time.time() * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/storage/pre-restart-snapshot")
def storage_pre_restart_snapshot():
    """Return the latest saved pre-restart snapshot marker, if any."""
    try:
        from backend.nexus_research.storage import get_research_store

        store = get_research_store()
        markers = store.query("persistence_validation_markers", limit=50)
        snap = None
        for m in reversed(markers):
            mid = str(m.get("marker_id") or m.get("markerId") or "")
            if mid.startswith("pre-restart-snapshot:"):
                snap = m.get("payload") or m
                break
        data = {
            "ok": True,
            "found": snap is not None,
            "snapshot": snap,
            "researchOnly": True,
            "privateApi": False,
            "generatedAt": int(time.time() * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/storage/recovery-verify", methods=["POST"])
def storage_recovery_verify():
    """Gate B: verify original PERSISTENCE_VALIDATION IDs survived restart."""
    try:
        body = request.get_json(silent=True) or {}
        if not body.get("researchOnly"):
            data = {"ok": False, "error": "researchOnly:true required", "researchOnly": True}
            resp = jsonify(data)
            _no_store(resp)
            return resp, 400
        if body.get("contract") != "NEXUS_PHASE61_PERSISTENCE_VALIDATION_V1":
            data = {
                "ok": False,
                "error": "contract NEXUS_PHASE61_PERSISTENCE_VALIDATION_V1 required",
                "researchOnly": True,
            }
            resp = jsonify(data)
            _no_store(resp)
            return resp, 400

        from backend.nexus_research.persistence_validation import verify_restart_recovery

        if body.get("ledger_account_id") or body.get("validation_round") == "PHASE61_RESTART_PROOF_V2":
            from backend.nexus_research.persistence_validation import (
                verify_v2_durable_ledger_recovery,
            )

            report = verify_v2_durable_ledger_recovery(body)
        else:
            report = verify_restart_recovery(body)
        data = {**report, "researchOnly": True, "privateApi": False}
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/review-engine/status")
def review_engine_status():
    """Phase 6 Gate D: review engine mode + provider status."""
    try:
        from backend.nexus_research.review_engine import get_review_engine
        data = get_review_engine().status()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/performance/summary")
def performance_summary():
    """Phase 6 Gate D: performance summary for all streams."""
    try:
        from backend.nexus_research.performance_service import get_performance_service
        data = get_performance_service().summary()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/performance/by-sector")
def performance_by_sector():
    try:
        from backend.nexus_research.performance_service import get_performance_service
        data = get_performance_service().by_sector()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/performance/by-regime")
def performance_by_regime():
    try:
        from backend.nexus_research.performance_service import get_performance_service
        data = get_performance_service().by_regime()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/performance/by-side")
def performance_by_side():
    try:
        from backend.nexus_research.performance_service import get_performance_service
        data = get_performance_service().by_side()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/performance/risk-blocks")
def performance_risk_blocks():
    try:
        from backend.nexus_research.performance_service import get_performance_service
        data = get_performance_service().risk_blocks()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/performance/calibration")
def performance_calibration():
    try:
        from backend.nexus_research.performance_service import get_performance_service
        data = get_performance_service().calibration()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


@nexus_research_bp.route("/api/nexus/soak/live/status")
def live_soak_status():
    """Phase 6 Gate D: live soak + phased marker status."""
    try:
        from backend.nexus_research.live_soak import get_live_soak_framework
        data = get_live_soak_framework().status()
    except Exception as exc:  # noqa: BLE001
        data = {"ok": False, "error": str(exc), "researchOnly": True}
    resp = jsonify(data)
    _no_store(resp)
    return resp


def register_nexus_research_routes(app: "Flask") -> None:
    """Register all Phase 5 / Phase 6 Gate B + Gate D routes."""
    app.register_blueprint(nexus_research_bp)
    logger.info("[nexus_research] Phase 6 Gate D routes registered")

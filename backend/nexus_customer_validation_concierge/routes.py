"""Flask routes for PUB2-G Customer Validation Concierge App (local/staging)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.nexus_customer_validation_concierge.constants import API_PREFIX
from backend.nexus_customer_validation_concierge.hard_bans import require_local_staging
from backend.nexus_customer_validation_concierge.service import ConciergeAppService, error_body

_SERVICE: ConciergeAppService | None = None
PACKAGE_DIR = Path(__file__).resolve().parent


def get_service(workspace: Path | str | None = None) -> ConciergeAppService:
    global _SERVICE
    if workspace is not None:
        return ConciergeAppService(workspace)
    if _SERVICE is None:
        _SERVICE = ConciergeAppService()
    return _SERVICE


def reset_service_for_tests(workspace: Path | str | None = None) -> ConciergeAppService:
    global _SERVICE
    _SERVICE = ConciergeAppService(workspace)
    return _SERVICE


def _json_payload(request: Any) -> dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def register_customer_validation_concierge_routes(app: Any, workspace: Path | str | None = None) -> None:
    """Mount Concierge validation workflow routes + Founder local UI."""
    from flask import Response, jsonify, request, send_from_directory

    if workspace is not None:
        reset_service_for_tests(workspace)

    prefix = API_PREFIX

    def _no_store(resp: Response) -> Response:
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-NEXUS-Lane"] = "PUB2-G"
        resp.headers["X-NEXUS-Concierge"] = "local-staging"
        resp.headers["X-NEXUS-Exchange-Write"] = "false"
        resp.headers["X-NEXUS-Live-Billing"] = "false"
        return resp

    @app.before_request
    def _concierge_env_guard():
        if not request.path.startswith(prefix) and request.path not in (
            "/concierge-validation",
            "/concierge-validation/",
        ):
            return None
        try:
            require_local_staging()
        except Exception as exc:  # noqa: BLE001
            body, code = error_body(exc)
            return _no_store(jsonify(body)), code
        return None

    @app.get("/concierge-validation")
    @app.get("/concierge-validation/")
    def concierge_ui():
        return send_from_directory(PACKAGE_DIR / "static", "index.html")

    @app.get(f"{prefix}/meta")
    def concierge_meta():
        return _no_store(jsonify(get_service().meta()))

    @app.get(f"{prefix}/counters")
    def concierge_counters():
        return _no_store(jsonify(get_service().counters()))

    @app.get(f"{prefix}/spine")
    def concierge_spine():
        return _no_store(jsonify(get_service().spine()))

    @app.get(f"{prefix}/catalogs")
    def concierge_catalogs():
        return _no_store(jsonify(get_service().catalogs()))

    @app.get(f"{prefix}/three-pass")
    def concierge_three_pass():
        return _no_store(jsonify(get_service().three_pass_proof()))

    def _post(handler_name: str):
        def view():
            try:
                handler = getattr(get_service(), handler_name)
                body = handler(_json_payload(request))
                return _no_store(jsonify(body))
            except Exception as exc:  # noqa: BLE001
                body, code = error_body(exc)
                return _no_store(jsonify(body)), code

        view.__name__ = f"concierge_{handler_name}"
        return view

    app.add_url_rule(f"{prefix}/enroll", view_func=_post("enroll"), methods=["POST"])
    app.add_url_rule(f"{prefix}/steps/consent", view_func=_post("step_consent"), methods=["POST"])
    app.add_url_rule(
        f"{prefix}/steps/interview/start",
        view_func=_post("step_interview_start"),
        methods=["POST"],
    )
    app.add_url_rule(
        f"{prefix}/steps/interview/complete",
        view_func=_post("step_interview_complete"),
        methods=["POST"],
    )
    app.add_url_rule(
        f"{prefix}/steps/problem-ranking",
        view_func=_post("step_problem_ranking"),
        methods=["POST"],
    )
    app.add_url_rule(
        f"{prefix}/steps/watchlist-onboarding",
        view_func=_post("step_watchlist_onboarding"),
        methods=["POST"],
    )
    app.add_url_rule(
        f"{prefix}/steps/decision-object-delivery",
        view_func=_post("step_decision_object_delivery"),
        methods=["POST"],
    )
    app.add_url_rule(
        f"{prefix}/steps/weekly-review",
        view_func=_post("step_weekly_review"),
        methods=["POST"],
    )
    app.add_url_rule(
        f"{prefix}/steps/retention",
        view_func=_post("step_retention"),
        methods=["POST"],
    )
    app.add_url_rule(
        f"{prefix}/steps/willingness-to-pay",
        view_func=_post("step_willingness_to_pay"),
        methods=["POST"],
    )
    app.add_url_rule(
        f"{prefix}/steps/objections",
        view_func=_post("step_objections"),
        methods=["POST"],
    )
    app.add_url_rule(
        f"{prefix}/steps/pilot-conversion",
        view_func=_post("step_pilot_conversion"),
        methods=["POST"],
    )

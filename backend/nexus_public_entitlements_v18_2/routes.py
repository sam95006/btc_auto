"""Flask routes — public entitlements (read-only authority)."""
from __future__ import annotations

from flask import Flask, Response, jsonify, request

from backend.nexus_public_entitlements_v18_2.authority import (
    PUBLIC_ENTITLEMENT_AUTHORITY,
    EntitlementRequiredError,
    normalize_plan,
)
from backend.nexus_public_entitlements_v18_2.capability_registry import PUBLIC_CAPABILITY_REGISTRY
from backend.nexus_public_entitlements_v18_2.constants import HARD_BANS, PACKAGE, SCHEMA
from backend.nexus_public_entitlements_v18_2.dto import navigation_contract_v18_2, public_product_meta
from backend.nexus_public_entitlements_v18_2.hard_bans import run_entitlement_scans
from backend.nexus_public_entitlements_v18_2.policy_matrix import policy_snapshot


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["X-NEXUS-Entitlements"] = "read-only"
    resp.headers["X-NEXUS-Customer-Trading"] = "false"
    return resp


def register_public_entitlements_v18_2_routes(app: Flask) -> None:
    prefix = "/api/public/entitlements/v18_2"
    v1 = "/v1/public/entitlements/v18_2"

    @app.before_request
    def _reject_mutations():
        path = request.path or ""
        if not (path.startswith(prefix) or path.startswith(v1)):
            return None
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        if request.method == "POST" and path.endswith("/check"):
            return None
        return _no_store(jsonify({"ok": False, "error": "method_not_allowed", "read_only": True})), 405

    def _plan_from_request() -> str:
        header = request.headers.get("X-Nexus-Plan")
        arg = request.args.get("plan")
        return normalize_plan(header or arg or "VISITOR")

    def _register_routes(base: str) -> None:
        @app.get(f"{base}/meta")
        def meta():
            body = {
                "ok": True,
                "schema": SCHEMA,
                "package": PACKAGE,
                "hard_bans": sorted(HARD_BANS),
                "single_capability_registry_count": 1,
                "single_entitlement_authority_count": 1,
                "product": public_product_meta(),
            }
            return _no_store(jsonify(body))

        @app.get(f"{base}/capabilities")
        def capabilities():
            return _no_store(jsonify({"ok": True, **PUBLIC_CAPABILITY_REGISTRY.snapshot()}))

        @app.get(f"{base}/policy")
        def policy():
            return _no_store(jsonify({"ok": True, **policy_snapshot()}))

        @app.get(f"{base}/me")
        def me():
            plan = _plan_from_request()
            org_role = request.args.get("org_role")
            dto = PUBLIC_ENTITLEMENT_AUTHORITY.build_dto(
                plan=plan,
                entitlement_source="session",
                org_role=org_role,
            )
            nav = navigation_contract_v18_2(include_organization=plan == "ENTERPRISE")
            return _no_store(jsonify({"ok": True, "entitlement": dto, "navigation": nav}))

        @app.post(f"{base}/check")
        def check():
            payload = request.get_json(silent=True) or {}
            plan = normalize_plan(payload.get("plan") or _plan_from_request())
            cap = str(payload.get("capability_id") or "").strip()
            org_role = payload.get("org_role")
            try:
                PUBLIC_ENTITLEMENT_AUTHORITY.require_capability(plan, cap, org_role=org_role)
            except EntitlementRequiredError as exc:
                return _no_store(jsonify(exc.body)), exc.status
            except Exception as exc:  # noqa: BLE001
                return _no_store(
                    jsonify(
                        {
                            "ok": False,
                            "error": "POLICY_DENIED",
                            "message": str(exc),
                        }
                    )
                ), 403
            return _no_store(
                jsonify(
                    {
                        "ok": True,
                        "granted": True,
                        "plan": plan,
                        "capability_id": cap,
                    }
                )
            )

        @app.get(f"{base}/navigation-contract")
        def nav_contract():
            plan = _plan_from_request()
            body = navigation_contract_v18_2(include_organization=plan == "ENTERPRISE")
            return _no_store(jsonify({"ok": True, **body}))

        @app.get(f"{base}/passes")
        def passes():
            from pathlib import Path

            root = Path(app.root_path).parent
            scans = run_entitlement_scans(root)
            return _no_store(jsonify({"ok": True, "scans": scans}))

    _register_routes(prefix)
    _register_routes(v1)

"""Flask routes — closed beta invite + access + ops visibility."""
from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify, request

from backend.nexus_closed_beta.ops import get_product_ops
from backend.nexus_closed_beta.partner_inventory import partner_api_inventory
from backend.nexus_closed_beta.service import ClosedBetaError, get_closed_beta_service
from backend.nexus_paid_beta_retention.auth_gate import (
    auth_required_body,
    extract_bearer_token,
    resolve_account_id,
)


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["X-NEXUS-Closed-Beta"] = "v18_2_22"
    resp.headers["X-NEXUS-Member-Execution"] = "0"
    return resp


def _require_account() -> tuple[str | None, Any]:
    token = extract_bearer_token(
        {k: str(v) for k, v in request.headers.items()},
        request.get_json(silent=True) or {},
    )
    account_id = resolve_account_id(token)
    if not account_id:
        return None, (_no_store(jsonify(auth_required_body())), 401)
    return account_id, None


def register_closed_beta_routes(app: Flask) -> None:
    prefix = "/api/nexus/public/closed-beta"
    svc = get_closed_beta_service()

    @app.get(f"{prefix}/foundation")
    def closed_beta_foundation():
        return _no_store(jsonify(svc.foundation_status()))

    @app.post(f"{prefix}/invites")
    def closed_beta_create_invite():
        body = request.get_json(silent=True) or {}
        admin_key = str(
            request.headers.get("X-NEXUS-Closed-Beta-Admin")
            or body.get("admin_key")
            or ""
        )
        try:
            result = svc.create_invite(
                admin_key=admin_key,
                email_hint=str(body.get("email_hint") or "") or None,
                ttl_seconds=int(body.get("ttl_seconds") or 7 * 24 * 3600),
                actor=str(body.get("actor") or "founder_admin"),
            )
            return _no_store(jsonify(result))
        except ClosedBetaError as exc:
            return _no_store(jsonify({"ok": False, "error": str(exc)})), 403

    @app.post(f"{prefix}/invites/redeem")
    def closed_beta_redeem():
        account_id, err = _require_account()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        try:
            result = svc.redeem_invite(
                account_id=account_id,
                invite_code=str(body.get("invite_code") or body.get("code") or ""),
            )
            return _no_store(jsonify(result))
        except ClosedBetaError as exc:
            return _no_store(jsonify({"ok": False, "error": str(exc)})), 400

    @app.post(f"{prefix}/invites/revoke")
    def closed_beta_revoke():
        body = request.get_json(silent=True) or {}
        admin_key = str(
            request.headers.get("X-NEXUS-Closed-Beta-Admin")
            or body.get("admin_key")
            or ""
        )
        try:
            result = svc.revoke_invite(
                admin_key=admin_key,
                invite_id=str(body.get("invite_id") or "") or None,
                account_id=str(body.get("account_id") or "") or None,
                actor=str(body.get("actor") or "founder_admin"),
            )
            return _no_store(jsonify(result))
        except ClosedBetaError as exc:
            return _no_store(jsonify({"ok": False, "error": str(exc)})), 403

    @app.get(f"{prefix}/me")
    def closed_beta_me():
        account_id, err = _require_account()
        if err:
            return err
        return _no_store(jsonify({"ok": True, "beta_access": svc.member_access_snapshot(account_id)}))

    @app.get(f"{prefix}/audit")
    def closed_beta_audit():
        body_key = request.args.get("admin_key") or ""
        admin_key = str(request.headers.get("X-NEXUS-Closed-Beta-Admin") or body_key or "")
        from backend.nexus_closed_beta.service import _admin_key_ok

        if not _admin_key_ok(admin_key):
            return _no_store(jsonify({"ok": False, "error": "admin_key_invalid"})), 403
        limit = min(100, max(1, int(request.args.get("limit", 40))))
        return _no_store(jsonify({"ok": True, "audit": svc.store.list_audit(limit=limit)}))

    @app.get(f"{prefix}/ops")
    def closed_beta_ops():
        return _no_store(jsonify(get_product_ops().snapshot()))

    @app.get(f"{prefix}/partner-inventory")
    def closed_beta_partner_inventory():
        return _no_store(jsonify({"ok": True, **partner_api_inventory()}))

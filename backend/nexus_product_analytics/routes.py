"""Product analytics routes — authenticated write, aggregate read."""
from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from backend.nexus_paid_beta_retention.auth_gate import (
    auth_required_body,
    extract_bearer_token,
    resolve_account_id,
)
from backend.nexus_product_analytics.events import (
    PRODUCT_EVENT_NAMES,
    get_analytics_store,
    record_event,
)


def register_product_analytics_routes(app: Flask) -> None:
    prefix = "/api/nexus/public/analytics"

    @app.get(f"{prefix}/contract")
    def analytics_contract():
        return jsonify(
            {
                "ok": True,
                "events": sorted(PRODUCT_EVENT_NAMES),
                "external_platform": False,
                "pii_policy": "no_passwords_tokens_secrets",
            }
        )

    @app.post(f"{prefix}/event")
    def analytics_event():
        token = extract_bearer_token(
            {k: str(v) for k, v in request.headers.items()},
            request.get_json(silent=True) or {},
        )
        account_id = resolve_account_id(token)
        # Allow anonymous radar/symbol opens; bind account when session present.
        body = request.get_json(silent=True) or {}
        name = str(body.get("name") or "")
        props = body.get("props") if isinstance(body.get("props"), dict) else {}
        try:
            result = record_event(name, account_id=account_id, props=props)
            return jsonify(result)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

    @app.get(f"{prefix}/summary")
    def analytics_summary():
        token = extract_bearer_token(
            {k: str(v) for k, v in request.headers.items()},
            request.get_json(silent=True) or {},
        )
        account_id = resolve_account_id(token)
        if not account_id:
            return jsonify(auth_required_body(reason="analytics_summary_requires_session")), 401
        store = get_analytics_store()
        return jsonify(
            {
                "ok": True,
                "counts": store.counts(),
                "recent": store.list_events(account_id=account_id, limit=30),
            }
        )

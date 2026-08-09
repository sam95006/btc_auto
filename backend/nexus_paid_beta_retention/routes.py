"""Flask routes — paid-beta retention foundation."""
from __future__ import annotations

from typing import Any

from flask import Flask, Response, jsonify, request

from backend.nexus_paid_beta_retention.alert_events import get_anti_spam
from backend.nexus_paid_beta_retention.auth_gate import (
    auth_required_body,
    extract_bearer_token,
    resolve_account_id,
)
from backend.nexus_paid_beta_retention.notifications import get_notification_center
from backend.nexus_paid_beta_retention.onboarding import get_onboarding_store
from backend.nexus_paid_beta_retention.service import (
    enrich_watchlist,
    foundation_status,
    ingest_alert,
    since_last_visit,
)
from backend.nexus_paid_beta_retention.watchlist_store import get_watchlist_store


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["X-NEXUS-Retention"] = "v18_2_22"
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


def register_paid_beta_retention_routes(app: Flask) -> None:
    prefix = "/api/nexus/public/retention"

    @app.get(f"{prefix}/foundation")
    def retention_foundation():
        return _no_store(jsonify(foundation_status()))

    @app.get(f"{prefix}/auth-census")
    def retention_auth_census():
        from backend.nexus_paid_beta_retention.auth_census import auth_commercial_census

        return _no_store(jsonify({"ok": True, **auth_commercial_census()}))

    @app.get(f"{prefix}/billing-readiness")
    def retention_billing_readiness():
        from backend.nexus_paid_beta_retention.billing_readiness import billing_readiness

        return _no_store(jsonify(billing_readiness()))

    @app.get(f"{prefix}/watchlist")
    def retention_watchlist_list():
        account_id, err = _require_account()
        if err:
            return err
        return _no_store(jsonify({"ok": True, **enrich_watchlist(account_id)}))

    @app.post(f"{prefix}/watchlist/add")
    def retention_watchlist_add():
        account_id, err = _require_account()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        try:
            result = get_watchlist_store().add(
                account_id,
                str(body.get("symbol") or ""),
                asset_class=str(body.get("asset_class") or "CRYPTO"),
            )
            # Emit watchlist event through anti-spam → notification center.
            ingest_alert(
                account_id,
                event_type="WATCHLIST_EVENT",
                symbol=str(body.get("symbol") or ""),
                severity="INFO",
                headline=f"Added {str(body.get('symbol') or '').upper()} to watchlist",
                source="watchlist",
            )
            try:
                from backend.nexus_product_analytics.events import record_event

                record_event(
                    "watchlist_added",
                    account_id=account_id,
                    props={"symbol": str(body.get("symbol") or "").upper()},
                )
            except Exception:
                pass
            return _no_store(jsonify({"ok": True, **enrich_watchlist(account_id), "mutated": result}))
        except ValueError as exc:
            return _no_store(jsonify({"ok": False, "error": str(exc)})), 400

    @app.post(f"{prefix}/watchlist/remove")
    def retention_watchlist_remove():
        account_id, err = _require_account()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        try:
            get_watchlist_store().remove(
                account_id,
                str(body.get("symbol") or ""),
                asset_class=str(body.get("asset_class") or "CRYPTO"),
            )
            try:
                from backend.nexus_product_analytics.events import record_event

                record_event(
                    "watchlist_removed",
                    account_id=account_id,
                    props={"symbol": str(body.get("symbol") or "").upper()},
                )
            except Exception:
                pass
            return _no_store(jsonify({"ok": True, **enrich_watchlist(account_id)}))
        except Exception as exc:
            try:
                from backend.nexus_closed_beta.ops import record_ops

                record_ops("watchlist_persistence_failures", detail=str(exc))
            except Exception:
                pass
            return _no_store(jsonify({"ok": False, "error": "watchlist_remove_failed"})), 500

    @app.get(f"{prefix}/notifications")
    def retention_notifications():
        account_id, err = _require_account()
        if err:
            return err
        limit = min(100, max(1, int(request.args.get("limit", 40))))
        return _no_store(jsonify({"ok": True, **get_notification_center().list_for(account_id, limit=limit)}))

    @app.post(f"{prefix}/notifications/read")
    def retention_notifications_read():
        account_id, err = _require_account()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        try:
            result = get_notification_center().mark_read(account_id, str(body.get("id") or ""))
            if result.get("ok"):
                try:
                    from backend.nexus_product_analytics.events import record_event

                    record_event(
                        "notification_read",
                        account_id=account_id,
                        props={"id": str(body.get("id") or "")},
                    )
                except Exception:
                    pass
            return _no_store(jsonify(result)), (200 if result.get("ok") else 404)
        except Exception as exc:
            try:
                from backend.nexus_closed_beta.ops import record_ops

                record_ops("notification_failures", detail=str(exc))
            except Exception:
                pass
            return _no_store(jsonify({"ok": False, "error": "notification_read_failed"})), 500

    @app.get(f"{prefix}/alert-prefs")
    def retention_alert_prefs():
        account_id, err = _require_account()
        if err:
            return err
        return _no_store(jsonify({"ok": True, "prefs": get_anti_spam().prefs_for(account_id)}))

    @app.post(f"{prefix}/alert-prefs")
    def retention_alert_prefs_set():
        account_id, err = _require_account()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        prefs = get_anti_spam().set_prefs(account_id, body)
        return _no_store(jsonify({"ok": True, "prefs": prefs}))

    @app.post(f"{prefix}/alerts/ingest")
    def retention_alert_ingest():
        account_id, err = _require_account()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        result = ingest_alert(
            account_id,
            event_type=str(body.get("type") or body.get("event_type") or "WATCHLIST_EVENT"),
            symbol=str(body.get("symbol") or ""),
            severity=str(body.get("severity") or "MEDIUM"),
            headline=str(body.get("headline") or "Alert"),
            metric=body.get("metric") if isinstance(body.get("metric"), dict) else {},
            source=str(body.get("source") or "api"),
            link=body.get("link"),
        )
        return _no_store(jsonify(result))

    @app.get(f"{prefix}/since-last-visit")
    def retention_since_last_visit():
        account_id, err = _require_account()
        if err:
            return err
        return _no_store(jsonify({"ok": True, **since_last_visit(account_id)}))

    @app.get(f"{prefix}/onboarding")
    def retention_onboarding():
        account_id, err = _require_account()
        if err:
            return err
        return _no_store(jsonify({"ok": True, **get_onboarding_store().status(account_id)}))

    @app.post(f"{prefix}/onboarding/step")
    def retention_onboarding_step():
        account_id, err = _require_account()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        try:
            status = get_onboarding_store().complete_step(account_id, str(body.get("step_id") or ""))
            return _no_store(jsonify({"ok": True, **status}))
        except ValueError as exc:
            return _no_store(jsonify({"ok": False, "error": str(exc)})), 400

    @app.post(f"{prefix}/onboarding/dismiss")
    def retention_onboarding_dismiss():
        account_id, err = _require_account()
        if err:
            return err
        return _no_store(jsonify({"ok": True, **get_onboarding_store().dismiss(account_id)}))

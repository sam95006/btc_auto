"""Corporate platform HTTP routes: public API + owner bootstrap + admin/RBAC/CMS.

Public endpoints serve PUBLISHED CMS content + safe live public market data with
provenance/freshness. Admin endpoints are backend-authorized (session + scope),
CSRF-protected on mutations, rate-limited, and audited. No Founder private
trading data is reachable here.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from flask import Flask, Response, jsonify, request

from backend.nexus_corporate.content import SLUGS
from backend.nexus_corporate.market import build_showcase
from backend.nexus_corporate.repository import CorporateRepository

REPO_CONFIG_KEY = "NEXUS_CORPORATE_REPO"
MARKET_SNAPSHOT_CONFIG_KEY = "NEXUS_CORPORATE_MARKET_SNAPSHOT"

SESSION_HEADER = "X-Corp-Session"
CSRF_HEADER = "X-Corp-CSRF"
# Allow-listed, non-identifying product analytics events.
ANALYTICS_EVENTS = frozenset({
    "page_view", "cta_primary", "cta_personal", "cta_enterprise",
    "personal_interest", "enterprise_interest", "contact_submit",
})
# Browser-managed session (HttpOnly) + readable double-submit CSRF cookie.
SESSION_COOKIE = "corp_session"
CSRF_COOKIE = "corp_csrf"
SESSION_MAX_AGE = 12 * 3600


def _set_session_cookies(resp: Response, session_id: str, csrf: str) -> Response:
    # HttpOnly session (JS can never read it) + Secure + SameSite=None so it is
    # sent on the cross-origin Corporate→Core requests. The CSRF cookie is
    # readable by JS for the double-submit header.
    resp.set_cookie(SESSION_COOKIE, session_id, max_age=SESSION_MAX_AGE, httponly=True,
                    secure=True, samesite="None", path="/")
    resp.set_cookie(CSRF_COOKIE, csrf, max_age=SESSION_MAX_AGE, httponly=False,
                    secure=True, samesite="None", path="/")
    return resp


def _clear_session_cookies(resp: Response) -> Response:
    resp.set_cookie(SESSION_COOKIE, "", max_age=0, httponly=True, secure=True, samesite="None", path="/")
    resp.set_cookie(CSRF_COOKIE, "", max_age=0, secure=True, samesite="None", path="/")
    return resp


def _session_id_from_request() -> str:
    # Cookie is authoritative for browsers; header is a fallback for API/tests.
    return request.cookies.get(SESSION_COOKIE) or request.headers.get(SESSION_HEADER, "")

# Minimal in-process rate limiter (per ip+bucket). Hardened store = CORPORATE-2.
_RL: dict[tuple[str, str], list[float]] = {}


def _rate_limited(bucket: str, ip: str, *, limit: int, window: float = 60.0) -> bool:
    now = time.monotonic()
    key = (bucket, ip or "unknown")
    hits = [t for t in _RL.get(key, []) if now - t < window]
    hits.append(now)
    _RL[key] = hits
    return len(hits) > limit


def _json(payload: dict[str, Any], status: int = 200) -> Response:
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _services(app: Flask) -> dict[str, Any]:
    return dict(app.config.get("NEXUS_PRODUCT_ALPHA_SERVICES") or {})


def _repo(app: Flask) -> Optional[CorporateRepository]:
    repo = app.config.get(REPO_CONFIG_KEY)
    if repo is not None:
        return repo
    pool = _services(app).get("pool")
    if pool is None:
        return None
    repo = CorporateRepository(pool)
    app.config[REPO_CONFIG_KEY] = repo
    return repo


def _snapshot_service(app: Flask):
    svc = app.config.get(MARKET_SNAPSHOT_CONFIG_KEY)
    if svc is not None:
        return svc
    try:
        from backend.nexus_product_backend.market_snapshot import build_public_market_snapshot_service

        svc = build_public_market_snapshot_service()
        app.config[MARKET_SNAPSHOT_CONFIG_KEY] = svc
        return svc
    except Exception:  # noqa: BLE001
        return None


def _client_ip() -> str:
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()


def register_corporate_routes(app: Flask) -> None:
    # ================= PUBLIC API =================
    @app.get("/api/corporate/v1/status")
    def corp_status():
        repo = _repo(app)
        return _json({
            "service": "nexus-corporate",
            "availability": "READY" if repo is not None else "DEGRADED",
            "backend": "ready" if repo is not None else "no_pool",
            "market_source": "ready" if _snapshot_service(app) is not None else "unavailable",
            "owner_bootstrap": ("closed" if (repo and repo.bootstrap_closed()) else "open") if repo else "unknown",
        })

    def _published(slug: str) -> Response:
        repo = _repo(app)
        if repo is None:
            return _json({"slug": slug, "availability": "UNAVAILABLE", "reason": "backend_unavailable"}, 503)
        body = repo.get_published(slug)
        if body is None:
            return _json({"slug": slug, "availability": "UNAVAILABLE", "reason": "not_found"}, 404)
        return _json({"slug": slug, "availability": "READY", "source": "cms", "data": body})

    @app.get("/api/corporate/v1/site")
    def corp_site():
        return _published("site")

    @app.get("/api/corporate/v1/home")
    def corp_home():
        return _published("home")

    @app.get("/api/corporate/v1/products")
    def corp_products():
        return _published("products")

    @app.get("/api/corporate/v1/products/personal")
    def corp_products_personal():
        return _published("products/personal")

    @app.get("/api/corporate/v1/products/enterprise")
    def corp_products_enterprise():
        return _published("products/enterprise")

    @app.get("/api/corporate/v1/pricing")
    def corp_pricing():
        return _published("pricing")

    @app.get("/api/corporate/v1/security")
    def corp_security():
        return _published("security")

    @app.get("/api/corporate/v1/about")
    def corp_about():
        return _published("about")

    @app.get("/api/corporate/v1/content/<path:slug>")
    def corp_content(slug: str):
        return _published(slug)

    @app.get("/api/corporate/v1/showcase")
    def corp_showcase():
        repo = _repo(app)
        cfg = (repo.get_published("showcase") if repo else None) or {"symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]}
        return _json({"availability": "READY", "source": "cms", "config": cfg})

    @app.get("/api/corporate/v1/market")
    def corp_market():
        repo = _repo(app)
        cfg = (repo.get_published("showcase") if repo else None) or {}
        symbols = tuple(cfg.get("symbols") or ("BTCUSDT", "ETHUSDT", "SOLUSDT"))
        return _json(build_showcase(_snapshot_service(app), symbols))

    @app.post("/api/corporate/v1/contact")
    def corp_contact():
        if _rate_limited("contact", _client_ip(), limit=5):
            return _json({"error": "rate_limited"}, 429)
        repo = _repo(app)
        if repo is None:
            return _json({"error": "backend_unavailable"}, 503)
        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip()
        if "@" not in email:
            return _json({"error": "invalid_email", "classification": "BAD_REQUEST"}, 400)
        lead_id = repo.add_lead(name=str(body.get("name") or ""), email=email,
                                company=str(body.get("company") or ""), message=str(body.get("message") or ""),
                                kind=str(body.get("kind") or "contact"))
        repo.add_audit(admin_id=None, action="lead.create", target=email, ip=_client_ip())
        return _json({"ok": True, "lead_id": lead_id})

    # Privacy-conscious first-party analytics. Allow-listed event names only, no
    # PII, no fingerprinting. Stored in the audit log (backend-collected); the
    # admin Analytics view reads only what was actually recorded (never fabricated).
    @app.post("/api/corporate/v1/analytics/event")
    def corp_analytics_event():
        if _rate_limited("analytics", _client_ip(), limit=60):
            return _json({"ok": True}, 202)  # silently drop; never error the page
        repo = _repo(app)
        if repo is None:
            return _json({"ok": True}, 202)
        body = request.get_json(silent=True) or {}
        event = str(body.get("event") or "").strip()
        if event not in ANALYTICS_EVENTS:
            return _json({"error": "unknown_event", "classification": "BAD_REQUEST"}, 400)
        path = str(body.get("path") or "")[:120]
        label = str(body.get("label") or "")[:64]
        repo.add_audit(admin_id=None, action=f"analytics.{event}", target=path, meta={"label": label} if label else None)
        return _json({"ok": True})

    # ================= OWNER BOOTSTRAP =================
    @app.post("/owner/setup")
    def owner_setup():
        if _rate_limited("owner_setup", _client_ip(), limit=5):
            return _json({"error": "rate_limited"}, 429)
        repo = _repo(app)
        if repo is None:
            return _json({"error": "backend_unavailable"}, 503)
        # Server-authoritative one-time gate.
        if repo.bootstrap_closed():
            repo.add_audit(admin_id=None, action="owner.bootstrap_rejected", ip=_client_ip())
            return _json({"error": "owner_bootstrap_closed", "classification": "FORBIDDEN"}, 403)
        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip()
        password = str(body.get("password") or "")
        try:
            admin = repo.create_owner(email=email, password=password,
                                      display_name=str(body.get("display_name") or ""), ip=_client_ip())
        except PermissionError:
            return _json({"error": "owner_bootstrap_closed", "classification": "FORBIDDEN"}, 403)
        except ValueError as exc:
            return _json({"error": str(exc), "classification": "BAD_REQUEST"}, 400)
        # Auto-login the new owner via a hardened session cookie.
        session = repo.login(email=email, password=password, ip=_client_ip())
        resp = _json({"ok": True, "owner": {"admin_id": admin["admin_id"], "email": admin["email"], "role": "OWNER"},
                      "csrf_token": session["csrf_token"]})
        return _set_session_cookies(resp, session["session_id"], session["csrf_token"])

    # ================= ADMIN AUTH =================
    @app.post("/admin/login")
    def admin_login():
        if _rate_limited("admin_login", _client_ip(), limit=10):
            return _json({"error": "rate_limited"}, 429)
        repo = _repo(app)
        if repo is None:
            return _json({"error": "backend_unavailable"}, 503)
        body = request.get_json(silent=True) or {}
        try:
            session = repo.login(email=str(body.get("email") or ""), password=str(body.get("password") or ""),
                                 ip=_client_ip())
        except PermissionError as exc:
            return _json({"error": str(exc), "classification": "UNAUTHORIZED"}, 401)
        resp = _json({"ok": True, "admin": session["admin"], "csrf_token": session["csrf_token"]})
        return _set_session_cookies(resp, session["session_id"], session["csrf_token"])

    @app.post("/admin/logout")
    def admin_logout():
        repo = _repo(app)
        if repo is not None:
            repo.revoke_session(_session_id_from_request())
        return _clear_session_cookies(_json({"ok": True}))

    @app.get("/admin/session")
    def admin_session():
        ctx = _auth(app)
        if ctx is None:
            return _json({"authenticated": False}, 401)
        # Return the session's CSRF token so a cross-origin frontend can rehydrate
        # its double-submit header after a page reload. This is safe: it is only
        # returned to a request already bearing the valid HttpOnly session cookie,
        # and the response body is unreadable by non-allowlisted origins under the
        # exact-origin CORS policy (a cross-site attacker can send the cookie but
        # cannot read this body to echo the token).
        return _json({"authenticated": True, "email": ctx["email"], "role": ctx["role"],
                      "permissions": sorted(ctx["permissions"]), "csrf_token": ctx["csrf_token"]})

    # ================= ADMIN (protected) =================
    @app.get("/admin/overview")
    def admin_overview():
        ctx = _guard(app, "status.read")
        if isinstance(ctx, Response):
            return ctx
        repo = _repo(app)
        return _json({"availability": "READY", "owner_bootstrap": "closed" if repo.bootstrap_closed() else "open",
                      "content_sections": len(repo.list_content()), "leads": len(repo.list_leads(limit=1)),
                      "note": "Business metrics are backend-collected; unavailable metrics are shown as unavailable."})

    @app.get("/admin/content")
    def admin_content_list():
        ctx = _guard(app, "content.read")
        if isinstance(ctx, Response):
            return ctx
        return _json({"content": _repo(app).list_content()})

    @app.get("/admin/content/<path:slug>")
    def admin_content_get(slug: str):
        ctx = _guard(app, "content.read")
        if isinstance(ctx, Response):
            return ctx
        item = _repo(app).get_content(slug)
        if item is None:
            return _json({"error": "unknown_slug"}, 404)
        return _json(item)

    @app.put("/admin/content/<path:slug>")
    def admin_content_save(slug: str):
        ctx = _guard(app, "content.write", csrf=True)
        if isinstance(ctx, Response):
            return ctx
        body = request.get_json(silent=True) or {}
        data = body.get("data")
        if not isinstance(data, dict):
            return _json({"error": "data_object_required", "classification": "BAD_REQUEST"}, 400)
        _repo(app).save_draft(slug=slug, body=data, actor_id=ctx["admin_id"])
        return _json({"ok": True, "slug": slug, "status": "DRAFT"})

    @app.post("/admin/content/<path:slug>/publish")
    def admin_content_publish(slug: str):
        ctx = _guard(app, "content.publish", csrf=True)
        if isinstance(ctx, Response):
            return ctx
        try:
            result = _repo(app).publish(slug=slug, actor_id=ctx["admin_id"])
        except ValueError:
            return _json({"error": "unknown_slug"}, 404)
        return _json({"ok": True, **result})

    @app.get("/admin/analytics")
    def admin_analytics():
        ctx = _guard(app, "analytics.read")
        if isinstance(ctx, Response):
            return ctx
        # Real counts from the audit log — backend-collected, never fabricated.
        rows = _repo(app).list_audit(limit=500)
        counts: dict[str, int] = {}
        for r in rows:
            act = str(r.get("action") or "")
            if act.startswith("analytics."):
                counts[act[len("analytics."):]] = counts.get(act[len("analytics."):], 0) + 1
        total = sum(counts.values())
        return _json({
            "availability": "READY" if total else "UNAVAILABLE",
            "note": "First-party events collected in the audit log (recent window). No PII, no fingerprinting.",
            "total": total,
            "events": [{"event": e, "count": counts[e]} for e in sorted(counts)],
        })

    @app.get("/admin/preview/<path:slug>")
    def admin_preview(slug: str):
        # Authenticated draft preview — returns the DRAFT body shaped like the
        # public content envelope. Drafts are NEVER exposed on the public API.
        ctx = _guard(app, "content.read")
        if isinstance(ctx, Response):
            return ctx
        item = _repo(app).get_content(slug)
        if item is None:
            return _json({"slug": slug, "availability": "UNAVAILABLE", "reason": "unknown_slug"}, 404)
        draft = item.get("draft") if isinstance(item.get("draft"), dict) else item.get("published")
        return _json({"slug": slug, "availability": "READY", "source": "draft", "data": draft or {}})

    @app.get("/admin/settings/<path:key>")
    def admin_setting_get(key: str):
        ctx = _guard(app, "settings.read")
        if isinstance(ctx, Response):
            return ctx
        return _json({"key": key, "value": _repo(app).get_setting(key)})

    @app.put("/admin/settings/<path:key>")
    def admin_setting_set(key: str):
        ctx = _guard(app, "settings.write", csrf=True)
        if isinstance(ctx, Response):
            return ctx
        body = request.get_json(silent=True) or {}
        value = body.get("value")
        if not isinstance(value, dict):
            return _json({"error": "value_object_required", "classification": "BAD_REQUEST"}, 400)
        _repo(app).set_setting(key, value)
        _repo(app).add_audit(admin_id=ctx["admin_id"], action="settings.write", target=key)
        return _json({"ok": True, "key": key})

    @app.get("/admin/leads")
    def admin_leads():
        ctx = _guard(app, "leads.read")
        if isinstance(ctx, Response):
            return ctx
        return _json({"leads": _repo(app).list_leads()})

    @app.get("/admin/audit")
    def admin_audit():
        ctx = _guard(app, "audit.read")
        if isinstance(ctx, Response):
            return ctx
        return _json({"audit": _repo(app).list_audit()})

    @app.post("/admin/admins")
    def admin_create_admin():
        ctx = _guard(app, "admins.write", csrf=True)
        if isinstance(ctx, Response):
            return ctx
        body = request.get_json(silent=True) or {}
        try:
            created = _repo(app).create_admin(email=str(body.get("email") or ""), password=str(body.get("password") or ""),
                                               display_name=str(body.get("display_name") or ""),
                                               role=str(body.get("role") or "EDITOR"), actor_id=ctx["admin_id"])
        except ValueError as exc:
            return _json({"error": str(exc), "classification": "BAD_REQUEST"}, 400)
        return _json({"ok": True, "admin": created})


def _auth(app: Flask) -> Optional[dict[str, Any]]:
    repo = _repo(app)
    if repo is None:
        return None
    return repo.resolve_session(_session_id_from_request())


def _guard(app: Flask, scope: str, *, csrf: bool = False):
    """Return the admin context, or a Response (401/403) if not authorized."""
    ctx = _auth(app)
    if ctx is None:
        return _json({"error": "unauthorized", "classification": "UNAUTHORIZED"}, 401)
    if csrf:
        provided = request.headers.get(CSRF_HEADER, "")
        import hmac as _hmac

        if not provided or not _hmac.compare_digest(provided, ctx.get("csrf_token") or ""):
            return _json({"error": "csrf_failed", "classification": "FORBIDDEN"}, 403)
    if scope not in ctx["permissions"]:
        return _json({"error": "permission_denied", "classification": "FORBIDDEN", "required": scope}, 403)
    return ctx

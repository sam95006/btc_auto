from __future__ import annotations

import secrets
from typing import Any

from flask import Flask

from backend.nexus_corporate.content import DEFAULT_CONTENT
from backend.nexus_corporate.passwords import hash_password, verify_password
from backend.nexus_corporate.permissions import OWNER_PERMISSIONS
from backend.nexus_corporate.routes import (
    MARKET_SNAPSHOT_CONFIG_KEY,
    REPO_CONFIG_KEY,
    _RL,
    register_corporate_routes,
)

EDITOR_PERMS = {"website.read", "content.read", "content.write", "leads.read", "status.read"}


class FakeRepo:
    """In-memory Corporate repository double implementing the route surface."""

    def __init__(self):
        self.admins: dict[str, dict[str, Any]] = {}
        self.by_email: dict[str, str] = {}
        self.sessions: dict[str, dict[str, Any]] = {}
        self.published: dict[str, Any] = {}
        self.drafts: dict[str, Any] = {}
        self.versions: dict[str, int] = {}
        self.leads: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self._closed = False

    def _perms(self, role):
        return set(OWNER_PERMISSIONS) if role == "OWNER" else set(EDITOR_PERMS)

    def bootstrap_closed(self):
        return self._closed or any(a["role"] == "OWNER" for a in self.admins.values())

    def add_audit(self, *, admin_id, action, target="", meta=None, ip=""):
        self.audit.append({"admin_id": admin_id, "action": action, "target": target})

    def _mk_admin(self, email, password, display_name, role):
        if "@" not in email:
            raise ValueError("invalid_email")
        algo, salt, digest = hash_password(password)
        aid = f"adm_{secrets.token_hex(6)}"
        self.admins[aid] = {"admin_id": aid, "email": email.lower(), "display_name": display_name,
                            "salt": salt, "hash": digest, "role": role}
        self.by_email[email.lower()] = aid
        return {"admin_id": aid, "email": email.lower(), "role": role, "display_name": display_name}

    def create_owner(self, *, email, password, display_name="", ip=""):
        if self.bootstrap_closed():
            raise PermissionError("closed")
        a = self._mk_admin(email.strip(), password, display_name, "OWNER")
        self._closed = True
        return a

    def create_admin(self, *, email, password, display_name, role, actor_id):
        if role not in ("OWNER", "EDITOR"):
            raise ValueError("unknown_role")
        return self._mk_admin(email.strip(), password, display_name, role)

    def login(self, *, email, password, ip=""):
        aid = self.by_email.get((email or "").strip().lower())
        a = self.admins.get(aid or "")
        if not a or not verify_password(password, a["salt"], a["hash"]):
            raise PermissionError("invalid_credentials")
        sid = f"sess_{secrets.token_hex(8)}"
        csrf = secrets.token_urlsafe(16)
        self.sessions[sid] = {"admin_id": aid, "csrf": csrf, "role": a["role"], "email": a["email"]}
        return {"session_id": sid, "csrf_token": csrf,
                "admin": {"admin_id": aid, "email": a["email"], "role": a["role"], "display_name": a["display_name"]}}

    def resolve_session(self, sid):
        s = self.sessions.get(sid or "")
        if not s:
            return None
        return {"admin_id": s["admin_id"], "csrf_token": s["csrf"], "email": s["email"], "role": s["role"],
                "permissions": self._perms(s["role"])}

    def revoke_session(self, sid):
        self.sessions.pop(sid or "", None)

    def get_published(self, slug):
        return self.published.get(slug) or DEFAULT_CONTENT.get(slug)

    def get_content(self, slug):
        if slug in self.drafts or slug in self.published or slug in DEFAULT_CONTENT:
            return {"slug": slug, "draft": self.drafts.get(slug, DEFAULT_CONTENT.get(slug, {})),
                    "published": self.published.get(slug, DEFAULT_CONTENT.get(slug)),
                    "published_version": self.versions.get(slug, 1)}
        return None

    def save_draft(self, *, slug, body, actor_id):
        self.drafts[slug] = body

    def publish(self, *, slug, actor_id):
        if slug not in self.drafts and slug not in DEFAULT_CONTENT:
            raise ValueError("unknown_slug")
        self.published[slug] = self.drafts.get(slug, DEFAULT_CONTENT.get(slug))
        self.versions[slug] = self.versions.get(slug, 0) + 1
        return {"slug": slug, "published_version": self.versions[slug]}

    def list_content(self):
        return [{"slug": s, "status": "PUBLISHED", "published_version": 1} for s in DEFAULT_CONTENT]

    def add_lead(self, *, name, email, company="", message="", kind="contact"):
        lid = f"lead_{secrets.token_hex(6)}"
        self.leads.append({"lead_id": lid, "email": email})
        return lid

    def list_leads(self, limit=100):
        return list(self.leads)

    def list_audit(self, limit=100):
        return list(self.audit)

    def __init_settings(self):
        if not hasattr(self, "settings"):
            self.settings: dict[str, Any] = {}

    def get_setting(self, key):
        self.__init_settings()
        return self.settings.get(key)

    def set_setting(self, key, value):
        self.__init_settings()
        self.settings[key] = value


class FakeSnapshot:
    def __init__(self, status=200):
        self.status = status

    def snapshot(self):
        if self.status != 200:
            return {"symbols": [], "fallback": "unavailable"}, 503
        return ({"server_timestamp": "2026-08-31T00:00:00Z", "fallback": "none", "symbols": [
            {"symbol": "BTCUSDT", "current_price": 60000.0, "change_24h_percent": 2.5, "high_24h": 61000, "low_24h": 59000,
             "provider_timestamp": "2026-08-31T00:00:00Z", "freshness": "FRESH"},
            {"symbol": "ETHUSDT", "current_price": 3000.0, "change_24h_percent": 3.1, "high_24h": 3100, "low_24h": 2900,
             "provider_timestamp": "2026-08-31T00:00:00Z", "freshness": "FRESH"},
            {"symbol": "SOLUSDT", "current_price": 150.0, "change_24h_percent": 1.2, "high_24h": 156, "low_24h": 149,
             "provider_timestamp": "2026-08-31T00:00:00Z", "freshness": "FRESH"},
        ]}, 200)


def _app(*, market_status=200):
    _RL.clear()  # reset the shared in-process rate limiter between tests
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config[REPO_CONFIG_KEY] = FakeRepo()
    app.config[MARKET_SNAPSHOT_CONFIG_KEY] = FakeSnapshot(status=market_status)
    register_corporate_routes(app)
    return app


def _owner(c):
    r = c.post("/owner/setup", json={"email": "owner@nexus.test", "password": "OwnerPass12345", "display_name": "Owner"})
    return r


# --------------------------------------------------------------------------
# Owner bootstrap
# --------------------------------------------------------------------------

def test_owner_bootstrap_first_succeeds_second_rejected():
    app = _app(); c = app.test_client()
    r1 = _owner(c)
    assert r1.status_code == 200 and r1.get_json()["owner"]["role"] == "OWNER"
    # Second attempt is server-rejected (not frontend hiding).
    r2 = c.post("/owner/setup", json={"email": "attacker@x.test", "password": "AttackerPass123"})
    assert r2.status_code == 403 and r2.get_json()["error"] == "owner_bootstrap_closed"


def test_owner_bootstrap_password_too_short_rejected():
    app = _app(); c = app.test_client()
    r = c.post("/owner/setup", json={"email": "o@x.test", "password": "short"})
    assert r.status_code == 400


def test_status_reports_bootstrap_state():
    app = _app(); c = app.test_client()
    assert c.get("/api/corporate/v1/status").get_json()["owner_bootstrap"] == "open"
    _owner(c)
    assert c.get("/api/corporate/v1/status").get_json()["owner_bootstrap"] == "closed"


# --------------------------------------------------------------------------
# Auth + RBAC + CSRF
# --------------------------------------------------------------------------

def test_login_wrong_password_401():
    app = _app(); c = app.test_client(); _owner(c)
    r = c.post("/admin/login", json={"email": "owner@nexus.test", "password": "WrongPass12345"})
    assert r.status_code == 401


def test_admin_requires_session_and_permission():
    app = _app()
    # A fresh client with NO cookie is unauthenticated.
    assert app.test_client().get("/admin/content").status_code == 401
    # The owner-setup client carries the HttpOnly session cookie → authorized.
    c = app.test_client(); _owner(c)
    assert c.get("/admin/content").status_code == 200  # OWNER has content.read


def test_editor_cannot_publish_but_owner_can():
    app = _app(); c = app.test_client(); csrf = _owner_csrf(c)
    c.post("/admin/admins", headers={"X-Corp-CSRF": csrf},
           json={"email": "editor@nexus.test", "password": "EditorPass12345", "role": "EDITOR"})
    # Log in as the editor (replaces the session cookie on this client).
    ed = app.test_client()
    lr = ed.post("/admin/login", json={"email": "editor@nexus.test", "password": "EditorPass12345"})
    ecsrf = lr.get_json()["csrf_token"]
    assert ed.put("/admin/content/about", headers={"X-Corp-CSRF": ecsrf}, json={"data": {"title": "x"}}).status_code == 200
    pub = ed.post("/admin/content/about/publish", headers={"X-Corp-CSRF": ecsrf})
    assert pub.status_code == 403 and pub.get_json()["required"] == "content.publish"


def test_mutation_requires_csrf():
    app = _app(); c = app.test_client(); _owner(c)
    # Cookie session present but NO CSRF header -> 403.
    r = c.put("/admin/content/about", json={"data": {"t": 1}})
    assert r.status_code == 403 and r.get_json()["error"] == "csrf_failed"


def test_session_cookie_is_httponly_secure_samesite():
    app = _app(); c = app.test_client()
    r = _owner_raw(c)
    cookies = r.headers.get_all("Set-Cookie")
    sess = [x for x in cookies if x.startswith("corp_session=")][0]
    assert "HttpOnly" in sess and "Secure" in sess and "SameSite=None" in sess
    # The CSRF cookie is readable (double-submit) — not HttpOnly.
    csrf = [x for x in cookies if x.startswith("corp_csrf=")][0]
    assert "HttpOnly" not in csrf and "Secure" in csrf


def test_session_survives_reload_and_logout_revokes():
    app = _app(); c = app.test_client(); csrf = _owner_csrf(c)
    # "Reload": a fresh request on the same client (cookie persists) stays authed.
    assert c.get("/admin/session").get_json()["authenticated"] is True
    assert c.get("/admin/content").status_code == 200
    c.post("/admin/logout", headers={"X-Corp-CSRF": csrf})
    assert c.get("/admin/content").status_code == 401  # session revoked + cookie cleared


def test_admin_session_returns_csrf_for_cross_origin_rehydration():
    # On a cross-origin deployment the readable corp_csrf cookie is host-scoped to
    # the API origin and invisible to the frontend, so the frontend rehydrates the
    # double-submit token from /admin/session after a reload. That token must be
    # present and must actually satisfy the CSRF guard on a mutation.
    app = _app(); c = app.test_client()
    _owner(c)
    sess = c.get("/admin/session").get_json()
    assert sess["authenticated"] is True and sess["role"] == "OWNER"
    rehydrated = sess.get("csrf_token")
    assert isinstance(rehydrated, str) and rehydrated
    # A mutation using ONLY the token from /admin/session (not the login body) works.
    assert c.put("/admin/content/about", headers={"X-Corp-CSRF": rehydrated},
                 json={"data": {"title": "Rehydrated"}}).status_code == 200
    # And a wrong token is still rejected (guard intact).
    assert c.put("/admin/content/about", headers={"X-Corp-CSRF": "wrong"},
                 json={"data": {"title": "Nope"}}).status_code == 403


# --------------------------------------------------------------------------
# CMS draft/publish + public published-only
# --------------------------------------------------------------------------

def test_cms_draft_publish_and_public_reads_published():
    app = _app(); c = app.test_client(); csrf = _owner_csrf(c)
    c.put("/admin/content/about", headers={"X-Corp-CSRF": csrf}, json={"data": {"title": "New About", "vision": "V"}})
    pub = c.post("/admin/content/about/publish", headers={"X-Corp-CSRF": csrf})
    assert pub.status_code == 200 and pub.get_json()["published_version"] == 1
    got = c.get("/api/corporate/v1/about").get_json()
    assert got["availability"] == "READY" and got["data"]["title"] == "New About"


def test_public_endpoints_serve_seed_defaults():
    app = _app(); c = app.test_client()
    for path in ("/api/corporate/v1/site", "/api/corporate/v1/home", "/api/corporate/v1/pricing"):
        j = c.get(path).get_json()
        assert j["availability"] == "READY" and j["source"] == "cms" and isinstance(j["data"], dict)


# --------------------------------------------------------------------------
# Live market showcase — real data path + honest unavailable
# --------------------------------------------------------------------------

def test_market_showcase_backend_computed_with_provenance():
    app = _app(); c = app.test_client()
    j = c.get("/api/corporate/v1/market").get_json()
    assert j["availability"] == "READY" and j["source"] == "binance_usdm_public"
    assert j["regime"]["value"] in ("RISK_ON", "RISK_OFF", "NEUTRAL")
    assert all("price" in s for s in j["symbols"])
    assert j["updated_at"] and j["freshness"] in ("FRESH", "STALE")


def test_market_showcase_unavailable_no_fabrication():
    app = _app(market_status=503); c = app.test_client()
    j = c.get("/api/corporate/v1/market").get_json()
    assert j["availability"] == "UNAVAILABLE"
    for s in j["symbols"]:
        assert "price" not in s and s["availability"] == "UNAVAILABLE"


def test_contact_lead_validation():
    app = _app(); c = app.test_client()
    assert c.post("/api/corporate/v1/contact", json={"email": "bad"}).status_code == 400
    assert c.post("/api/corporate/v1/contact", json={"email": "a@b.test", "message": "hi"}).status_code == 200


# --------------------------------------------------------------------------
# CORPORATE-2: analytics, preview, settings
# --------------------------------------------------------------------------

def test_analytics_event_allowlist_and_recording():
    app = _app(); c = app.test_client()
    assert c.post("/api/corporate/v1/analytics/event", json={"event": "cta_primary", "path": "/"}).status_code == 200
    # unknown events are rejected, never recorded
    assert c.post("/api/corporate/v1/analytics/event", json={"event": "evil_track"}).status_code == 400
    # owner can read the backend-collected summary
    csrf = _owner_csrf(c)
    assert csrf  # session established
    summary = c.get("/admin/analytics").get_json()
    assert summary["availability"] == "READY"
    assert any(e["event"] == "cta_primary" and e["count"] >= 1 for e in summary["events"])


def test_admin_preview_requires_auth_and_returns_draft():
    app = _app(); c = app.test_client()
    # unauthenticated preview is refused
    fresh = app.test_client()
    assert fresh.get("/admin/preview/about").status_code == 401
    csrf = _owner_csrf(c)
    c.put("/admin/content/about", headers={"X-Corp-CSRF": csrf}, json={"data": {"title": "Draft only"}})
    prev = c.get("/admin/preview/about").get_json()
    assert prev["availability"] == "READY" and prev["source"] == "draft"
    assert prev["data"]["title"] == "Draft only"
    # ...and the draft is NOT visible on the public API (still old/default)
    pub = c.get("/api/corporate/v1/about").get_json()
    assert pub["data"].get("title") != "Draft only"


def test_market_brief_is_deterministic_and_labelled():
    app = _app(); c = app.test_client()
    j = c.get("/api/corporate/v1/brief").get_json()
    assert j["availability"] == "READY"
    assert j["generator"] == "deterministic_rule_based"  # honest: NOT AI-generated
    assert j["source"] == "binance_usdm_public"
    assert isinstance(j["summary"], list) and j["summary"]
    assert set(j["data_used"]) == {"BTC", "ETH", "SOL"}


def test_market_brief_unavailable_no_fabrication():
    app = _app(market_status=503); c = app.test_client()
    j = c.get("/api/corporate/v1/brief").get_json()
    assert j["availability"] == "UNAVAILABLE"
    assert "summary" not in j  # nothing invented


def test_events_feed_real_observations_and_persist():
    app = _app(); c = app.test_client()
    j = c.get("/api/corporate/v1/events").get_json()
    assert j["availability"] == "READY" and j["source"] == "binance_usdm_public"
    # current-state observations are always populated from real live data
    assert isinstance(j["observations"], list) and j["observations"]
    assert all("text" in o and "ts" in o for o in j["observations"])
    # stable data across two polls yields no fabricated transitions
    j2 = c.get("/api/corporate/v1/events").get_json()
    assert j2["transitions"] == []


def test_admin_settings_get_set_requires_csrf():
    app = _app(); c = app.test_client(); csrf = _owner_csrf(c)
    # mutation without CSRF is refused
    assert c.put("/admin/settings/site.meta", json={"value": {"a": 1}}).status_code == 403
    assert c.put("/admin/settings/site.meta", headers={"X-Corp-CSRF": csrf}, json={"value": {"a": 1}}).status_code == 200
    got = c.get("/admin/settings/site.meta").get_json()
    assert got["value"] == {"a": 1}
    # non-object value rejected
    assert c.put("/admin/settings/x", headers={"X-Corp-CSRF": csrf}, json={"value": "nope"}).status_code == 400


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _owner_raw(c):
    return c.post("/owner/setup", json={"email": "owner@nexus.test", "password": "OwnerPass12345", "display_name": "Owner"})


def _owner_csrf(c):
    return _owner(c).get_json()["csrf_token"]

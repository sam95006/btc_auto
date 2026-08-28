"""HTTP routes for member email verification and password reset.

These endpoints extend the existing product-alpha member surface. They are all
POST (no state-changing GET), emit ``Cache-Control: no-store``, and are guarded
by a lightweight per-IP+route rate limit. Verification and reset flows are
token-based (the one-time token is the authority), so they intentionally do not
require a session CSRF token — they run before/without an authenticated session.

Nothing here logs a raw token, password, or provider secret.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Optional

from flask import Flask, Response, jsonify, request

from backend.nexus_product_backend.email_auth import MemberEmailService
from backend.nexus_product_backend.email_provider import build_email_provider

EMAIL_SERVICE_CONFIG_KEY = "NEXUS_MEMBER_EMAIL_SERVICE"
EMAIL_VERIFICATION_ENFORCED_CONFIG_KEY = "NEXUS_EMAIL_VERIFICATION_ENFORCED"
FRONTEND_BASE_CONFIG_KEY = "NEXUS_MEMBER_FRONTEND_BASE_URL"
RATE_LIMITER_CONFIG_KEY = "NEXUS_MEMBER_EMAIL_RATE_LIMITER"

DEFAULT_FRONTEND_BASE = "https://nexus-member-preview-v18-2-1.zeabur.app"
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW_SECONDS = 60.0


class _RateLimiter:
    """Minimal in-memory sliding-window limiter keyed by route+client."""

    def __init__(self, max_events: int = RATE_LIMIT_MAX, window: float = RATE_LIMIT_WINDOW_SECONDS) -> None:
        self._max = int(max_events)
        self._window = float(window)
        self._lock = threading.RLock()
        self._events: dict[str, list[float]] = {}

    def allow(self, key: str, *, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        with self._lock:
            bucket = [t for t in self._events.get(key, []) if now - t < self._window]
            if len(bucket) >= self._max:
                self._events[key] = bucket
                return False
            bucket.append(now)
            self._events[key] = bucket
            return True


def _services(app: Flask) -> dict[str, Any]:
    return dict(app.config.get("NEXUS_PRODUCT_ALPHA_SERVICES") or {})


def _json_no_store(payload: dict[str, Any], status: int = 200) -> Response:
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def build_member_email_service(app: Flask) -> MemberEmailService:
    """Build (and cache) the MemberEmailService bound to the app's repo/auth."""
    cached = app.config.get(EMAIL_SERVICE_CONFIG_KEY)
    if isinstance(cached, MemberEmailService):
        return cached
    services = _services(app)
    repo = services.get("repo")
    auth = services.get("auth")
    hasher = getattr(auth, "_hasher", None)

    def hash_password(raw: str) -> str:
        if hasher is not None:
            return hasher.hash(raw)
        # Fallback should never be used in production wiring; kept non-plaintext.
        import hashlib

        return "sha256$" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    frontend_base = (
        app.config.get(FRONTEND_BASE_CONFIG_KEY)
        or os.getenv("NEXUS_PUBLIC_WEB_BASE_URL")
        or os.getenv("NEXUS_MEMBER_FRONTEND_BASE_URL")
        or DEFAULT_FRONTEND_BASE
    )
    provider = build_email_provider()
    service = MemberEmailService(
        repo,
        hash_password=hash_password,
        provider=provider,
        frontend_base_url=frontend_base,
    )
    app.config[EMAIL_SERVICE_CONFIG_KEY] = service
    return service


def _limiter(app: Flask) -> _RateLimiter:
    limiter = app.config.get(RATE_LIMITER_CONFIG_KEY)
    if not isinstance(limiter, _RateLimiter):
        limiter = _RateLimiter()
        app.config[RATE_LIMITER_CONFIG_KEY] = limiter
    return limiter


def _client_key(route: str) -> str:
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    return f"{route}:{ip}"


def register_member_email_routes(app: Flask) -> None:
    """Attach the email verification and password reset endpoints."""

    def _rate_limited(route: str) -> Optional[Response]:
        if not _limiter(app).allow(_client_key(route)):
            return _json_no_store(
                {"error": "rate_limited", "classification": "RATE_LIMITED"}, 429
            )
        return None

    def _delivery_state(delivery: Optional[dict[str, Any]]) -> dict[str, Any]:
        # Surface only non-sensitive audit fields; make provider-unconfigured
        # state explicit rather than pretending a send happened.
        if not delivery:
            return {"delivery_status": "UNKNOWN"}
        return {
            "delivery_status": delivery.get("status"),
            "delivery_provider": delivery.get("provider"),
            "delivery_attempted": bool(delivery.get("attempts", 0)) or delivery.get("delivered", False),
            "email_provider_configured": delivery.get("provider") != "null",
        }

    @app.post("/api/v1/product/auth/verify-email")
    def product_verify_email():
        limited = _rate_limited("verify-email")
        if limited is not None:
            return limited
        body = request.get_json(silent=True) or {}
        token = str(body.get("token") or "")
        result = build_member_email_service(app).verify_email(raw_token=token)
        return _json_no_store(
            {"ok": result.ok, "code": result.code, "message": result.message}, result.status_code
        )

    @app.post("/api/v1/product/auth/resend-verification")
    def product_resend_verification():
        limited = _rate_limited("resend-verification")
        if limited is not None:
            return limited
        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip().lower()
        result = build_member_email_service(app).resend_verification(email=email)
        payload = {"ok": True, "code": result.code, "message": result.message}
        payload.update(_delivery_state(result.delivery))
        return _json_no_store(payload, result.status_code)

    @app.post("/api/v1/product/auth/forgot-password")
    def product_forgot_password():
        limited = _rate_limited("forgot-password")
        if limited is not None:
            return limited
        body = request.get_json(silent=True) or {}
        email = str(body.get("email") or "").strip().lower()
        result = build_member_email_service(app).forgot_password(email=email)
        # Always generic; never reveals whether the account exists.
        return _json_no_store({"ok": True, "code": result.code, "message": result.message}, 200)

    @app.post("/api/v1/product/auth/reset-password")
    def product_reset_password():
        limited = _rate_limited("reset-password")
        if limited is not None:
            return limited
        body = request.get_json(silent=True) or {}
        token = str(body.get("token") or "")
        new_password = body.get("new_password")
        if not isinstance(new_password, str):
            new_password = ""
        result = build_member_email_service(app).reset_password(
            raw_token=token, new_password=new_password
        )
        payload = {"ok": result.ok, "code": result.code, "message": result.message}
        if result.ok:
            payload["sessions_revoked"] = result.revoked_sessions
        return _json_no_store(payload, result.status_code)

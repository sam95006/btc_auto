"""Minimal API-only Flask application for nexus-api-staging.

This deliberately excludes the monorepo's legacy UI, scanner, and trading route
registrations.  It only exposes product-alpha, health, and public realtime
contracts, with database-backed auth/entitlement/RBAC/audit services.
"""
from __future__ import annotations

import os

from flask import Flask, jsonify
from flask import request

from backend.nexus_persistence_pg.pool import PostgresPool
from backend.nexus_persistence_pg.runtime import PostgresRuntimeConfig
from backend.nexus_product_backend.audit_alpha import ProductAuditAlphaService
from backend.nexus_product_backend.auth_alpha import AuthAlphaService
from backend.nexus_product_backend.entitlement_alpha import EntitlementAlphaService
from backend.nexus_product_backend.rbac_alpha import RbacAlphaService
from backend.nexus_product_backend.repository import ProductRepository
from backend.nexus_product_backend.routes import register_product_alpha_routes
from backend.nexus_public_realtime_transport.routes import register_public_realtime_routes


def _provision_staging_seed(services: dict[str, object]) -> None:
    """Create/update no identity automatically; only provision an explicit staging seed once."""
    if not (
        os.getenv("NEXUS_STAGING_SESSION_BOOTSTRAP", "").strip().lower() == "true"
        and (os.getenv("NEXUS_ENV") or "").strip().lower() == "staging"
    ):
        return
    email = os.getenv("NEXUS_STAGING_SEED_EMAIL", "").strip().lower()
    password = os.getenv("NEXUS_STAGING_SEED_PASSWORD", "")
    repo = services.get("repo")
    auth = services.get("auth")
    if not email or len(password) < 12 or not repo or not auth:
        return
    existing = repo.get_account_by_email(email)
    account_id = existing["account_id"] if existing else auth.register(email, password)["account_id"]
    repo.grant_entitlement(account_id, "ADVANCED")
    repo.bind_role(account_id, "role_member")
    repo.profile(account_id)
    repo.member_preferences(account_id)
    repo.notification_preferences(account_id)


def _product_services() -> dict[str, object]:
    cfg = PostgresRuntimeConfig.from_env()
    if not cfg.enabled or not cfg.database_url:
        return {}
    pool = PostgresPool(cfg.database_url)
    pool.open()
    repo = ProductRepository(pool)
    auth = AuthAlphaService(repo)
    return {
        "pool": pool,
        "repo": repo,
        "auth": auth,
        "entitlement": EntitlementAlphaService(repo, auth),
        "rbac": RbacAlphaService(repo, auth),
        "audit": ProductAuditAlphaService(repo),
    }


def _allowed_origins() -> set[str]:
    return {
        origin.strip().rstrip("/")
        for origin in (os.getenv("NEXUS_CORS_ALLOWED_ORIGINS") or "").split(",")
        if origin.strip().startswith("https://")
    }


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["NEXUS_PRODUCT_ALPHA_SERVICES"] = _product_services()
    # Never enable the seed-login route by default or on arbitrary environments.
    app.config["NEXUS_STAGING_SESSION_BOOTSTRAP"] = (
        os.getenv("NEXUS_STAGING_SESSION_BOOTSTRAP", "").strip().lower() == "true"
        and (os.getenv("NEXUS_ENV") or os.getenv("NEXUS_DEPLOYMENT_ENV") or "").strip().lower() == "staging"
    )
    app.config["NEXUS_STAGING_MEMBER_AUTH_ENABLED"] = (
        os.getenv("NEXUS_STAGING_MEMBER_AUTH_ENABLED", "").strip().lower() == "true"
        and (os.getenv("NEXUS_ENV") or os.getenv("NEXUS_DEPLOYMENT_ENV") or "").strip().lower() == "staging"
    )
    app.config["NEXUS_STAGING_REGISTRATION_ENABLED"] = (
        os.getenv("NEXUS_STAGING_REGISTRATION_ENABLED", "").strip().lower() == "true"
        and (os.getenv("NEXUS_ENV") or os.getenv("NEXUS_DEPLOYMENT_ENV") or "").strip().lower() == "staging"
    )
    _provision_staging_seed(app.config["NEXUS_PRODUCT_ALPHA_SERVICES"])

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "OK",
                "service": "nexus-api-staging",
                "execution_controls": False,
                "runtime_binding": "UNAVAILABLE",
            }
        )

    register_product_alpha_routes(app)
    register_public_realtime_routes(app)

    @app.after_request
    def staging_cors(response):
        """Allow only explicitly configured HTTPS staging origins."""
        origin = (request.headers.get("Origin") or "").rstrip("/")
        if origin and origin in _allowed_origins():
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, X-Nexus-Session, X-Nexus-CSRF"
            )
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    return app


app = create_app()

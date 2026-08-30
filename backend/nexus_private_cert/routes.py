"""Authenticated read-only certification endpoint for the private runtime.

Exposes exactly one control action: run the PRIVATE-ENV-2 read-only
certification and return a strict redacted result. It is impossible to submit,
cancel, amend, or mutate any order/position through this route — the certifier
performs only read-only calls. Authorization uses an existing runtime control
secret; the token value is never returned or logged.
"""

from __future__ import annotations

import hmac
import os
from typing import Any

from flask import Flask, Response, jsonify, request

from backend.nexus_private_cert.certifier import run_certification

CONTROL_HEADER = "X-Nexus-Control"
# Primary auth matches the service-wide validation guard:
#   Authorization: Bearer <NEXUS_VALIDATION_CONTROL_TOKEN>
# X-Nexus-Control (either control secret) is a local/testing fallback.
PRIMARY_CONTROL_ENV = "NEXUS_VALIDATION_CONTROL_TOKEN"
CONTROL_ENV_KEYS = ("NEXUS_VALIDATION_CONTROL_TOKEN", "NEXUS_BOUNDED_SESSION_CONTROL_SECRET")


def _bearer_token(header_value: str) -> str:
    parts = (header_value or "").strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return ""


def _json_no_store(payload: dict[str, Any], status: int = 200) -> Response:
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _authorized(provided: str) -> bool:
    provided = provided or ""
    if not provided:
        return False
    for key in CONTROL_ENV_KEYS:
        expected = os.environ.get(key) or ""
        if expected and hmac.compare_digest(provided, expected):
            return True
    return False


def _control_configured() -> bool:
    return any(os.environ.get(k) for k in CONTROL_ENV_KEYS)


def _get_pool(app: Flask) -> Any:
    services = dict(app.config.get("NEXUS_PRODUCT_ALPHA_SERVICES") or {})
    pool = services.get("pool")
    if pool is not None:
        return pool
    pool = app.config.get("NEXUS_PRIVATE_CERT_POOL")
    if pool is not None:
        return pool
    # Canonical private binding: the certified trading runtime connects its
    # durable ledger via PostgresPool(NEXUS_POSTGRES_URL) directly. The
    # certifier reads the SAME source-of-truth over the Zeabur private network,
    # independent of the product-alpha NEXUS_PG_RUNTIME_ENABLED gate (which the
    # private service keeps false). No second DB, no public networking, no DSN
    # exposure — the connection string is read from env and never returned.
    dsn = (os.environ.get("NEXUS_POSTGRES_URL") or os.environ.get("DATABASE_URL") or "").strip()
    if not dsn:
        return None
    try:
        from backend.nexus_persistence_pg.pool import PostgresPool

        pool = PostgresPool(dsn)
        pool.open()
        app.config["NEXUS_PRIVATE_CERT_POOL"] = pool
        return pool
    except Exception:  # noqa: BLE001
        return None


def register_private_cert_routes(app: Flask) -> None:
    @app.post("/api/v1/private/cert/run")
    def private_cert_run():
        if not _control_configured():
            # Fail-closed: without a control secret the endpoint is inert.
            return _json_no_store({"error": "control_secret_not_configured"}, 503)
        # Accept Authorization: Bearer <token> (guard contract) or X-Nexus-Control.
        provided = _bearer_token(request.headers.get("Authorization", "")) or request.headers.get(CONTROL_HEADER, "")
        if not _authorized(provided):
            return _json_no_store({"error": "unauthorized"}, 401)
        result = run_certification(pool=_get_pool(app))
        if result.get("blocked_reason") == "SAFETY_BLOCK":
            return _json_no_store(result, 403)
        return _json_no_store(result, 200 if result.get("private_env2_pass") else 409)

    @app.get("/api/v1/private/cert/health")
    def private_cert_health():
        # Non-secret liveness of the certifier route (no credentialed calls).
        return _json_no_store(
            {
                "certifier": "ready",
                "control_secret_configured": _control_configured(),
                "read_only": True,
            }
        )

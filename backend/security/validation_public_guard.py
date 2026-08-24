from __future__ import annotations

import hmac
import logging
import os
from typing import Final

from flask import Flask, jsonify, request


CONTROL_TOKEN_ENV: Final[str] = "NEXUS_VALIDATION_CONTROL_TOKEN"
GUARD_ENV: Final[str] = "NEXUS_VALIDATION_PUBLIC_GUARD"

_TRUE_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_AUTO_VALUES: Final[frozenset[str]] = frozenset({"auto", "detect", "validation"})
_STATE_CHANGING_METHODS: Final[frozenset[str]] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_QUERY_TOKEN_KEYS: Final[frozenset[str]] = frozenset(
    {"token", "control_token", "api_token", "authorization", "auth"}
)

PUBLIC_GET_ALLOWLIST: Final[frozenset[str]] = frozenset(
    {
        "/health",
        "/api/nexus/fee-policy",
        "/api/nexus/market/status",
        "/api/nexus/demo-execution/account",
        "/api/nexus/control-plane/overview",
        "/api/nexus/demo-execution/status",
    }
)

logger = logging.getLogger(__name__)


def _env_true(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in _TRUE_VALUES


def _validation_runtime_detected() -> bool:
    markers = " ".join(
        (os.environ.get(k) or "")
        for k in (
            "SERVICE_NAME",
            "ZEABUR_SERVICE_NAME",
            "NEXUS_SERVICE_NAME",
            "NEXUS_VALIDATION_SERVICE_NAME",
            "NEXUS_VALIDATION_BOOT",
        )
    ).lower()
    return "validation" in markers and ("demo" in markers or "bybit" in markers)


def validation_public_guard_enabled() -> bool:
    raw = (os.environ.get(GUARD_ENV) or "").strip().lower()
    if raw in _TRUE_VALUES:
        return True
    if raw in _AUTO_VALUES:
        return _validation_runtime_detected()
    return False


def is_public_get_allowed(path: str, method: str) -> bool:
    method = method.upper()
    return method in {"GET", "HEAD"} and path in PUBLIC_GET_ALLOWLIST


def _extract_bearer_token(header_value: str) -> tuple[str, str]:
    parts = (header_value or "").strip().split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        return "", "malformed_authorization"
    return parts[1].strip(), ""


def request_has_valid_control_auth() -> tuple[bool, str]:
    expected = (os.environ.get(CONTROL_TOKEN_ENV) or "").strip()
    if not expected:
        return False, "control_token_not_configured"
    token, err = _extract_bearer_token(request.headers.get("Authorization", ""))
    if err:
        return False, err
    if not hmac.compare_digest(token, expected):
        return False, "control_token_invalid"
    return True, ""


def _deny(reason: str):
    logger.warning(
        "validation_public_guard_denied method=%s path=%s reason=%s",
        request.method,
        request.path,
        reason,
    )
    response = jsonify(
        {
            "ok": False,
            "error": "VALIDATION_PUBLIC_GUARD_DENIED",
            "reason": reason,
            "control_token_required": True,
        }
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Nexus-Validation-Public-Guard"] = "denied"
    return response, 403


def install_validation_public_guard(app: Flask) -> None:
    if app.config.get("NEXUS_VALIDATION_PUBLIC_GUARD_INSTALLED"):
        return
    app.config["NEXUS_VALIDATION_PUBLIC_GUARD_INSTALLED"] = True

    @app.before_request
    def _validation_public_guard():
        if not validation_public_guard_enabled():
            return None
        if any(key.lower() in _QUERY_TOKEN_KEYS for key in request.args.keys()):
            return _deny("query_token_rejected")
        if is_public_get_allowed(request.path, request.method):
            return None
        ok, reason = request_has_valid_control_auth()
        if not ok:
            return _deny(reason)
        return None

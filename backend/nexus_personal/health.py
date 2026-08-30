"""Personal closed-beta health contract (PERSONAL-2).

Aggregates the minimum dependency signals a Personal closed-beta needs and
reports an honest overall status. It NEVER reports "healthy" while a critical
dependency is unavailable. Member-safe: exposes only coarse dependency status,
never secrets, connection strings, or provider credentials.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from flask import Flask

from backend.nexus_billing.routes import SUBSCRIPTION_REPO_CONFIG_KEY

# Dependencies whose absence must prevent an overall "healthy".
CRITICAL = ("api", "auth", "market_source")

FRONTEND_ARTIFACT_CONFIG_KEY = "NEXUS_PERSONAL_FRONTEND_ARTIFACT"


def _services(app: Flask) -> dict[str, Any]:
    return dict(app.config.get("NEXUS_PRODUCT_ALPHA_SERVICES") or {})


def _ok(detail: str = "") -> dict[str, Any]:
    return {"status": "ok", "detail": detail}


def _unavailable(detail: str = "") -> dict[str, Any]:
    return {"status": "unavailable", "detail": detail}


def _unknown(detail: str = "") -> dict[str, Any]:
    return {"status": "unknown", "detail": detail}


def _frontend_artifact_status(app: Flask) -> dict[str, Any]:
    path = app.config.get(FRONTEND_ARTIFACT_CONFIG_KEY) or os.getenv("NEXUS_PERSONAL_FRONTEND_ARTIFACT")
    if not path:
        # The API process does not necessarily co-host the static artifact.
        return _unknown("artifact_path_not_configured")
    index = Path(str(path)) / "index.html"
    return _ok(str(index)) if index.is_file() else _unavailable("index_html_missing")


def _db_status(app: Flask) -> dict[str, Any]:
    pool = _services(app).get("pool")
    if pool is None:
        return _unavailable("no_pool")
    try:
        readiness = pool.readiness()
    except Exception as exc:  # noqa: BLE001
        return _unavailable(f"readiness_error:{type(exc).__name__}")
    return _ok() if readiness.get("ready") else _unavailable(str(readiness.get("reason") or "not_ready"))


def closed_beta_health(app: Flask) -> tuple[dict[str, Any], int]:
    # Imported lazily to avoid a circular import at module load.
    from backend.nexus_personal.routes import _market_adapter

    auth_ok = _services(app).get("auth") is not None
    billing_ok = bool(app.config.get(SUBSCRIPTION_REPO_CONFIG_KEY)) or _services(app).get("pool") is not None
    market_ok = _market_adapter(app) is not None

    dependencies: dict[str, dict[str, Any]] = {
        "api": _ok(),
        "auth": _ok() if auth_ok else _unavailable("auth_service_missing"),
        "billing": _ok() if billing_ok else _unavailable("billing_state_unavailable"),
        "market_source": _ok() if market_ok else _unavailable("market_adapter_unbound"),
        "data_freshness": _ok("known_on_fetch") if market_ok else _unknown("no_market_source"),
        "database": _db_status(app),
        "frontend_artifact": _frontend_artifact_status(app),
    }

    critical_down = [name for name in CRITICAL if dependencies[name]["status"] != "ok"]
    any_unavailable = any(dep["status"] == "unavailable" for dep in dependencies.values())

    if critical_down:
        overall = "unavailable"
        http = 503
    elif any_unavailable:
        overall = "degraded"
        http = 200
    else:
        overall = "healthy"
        http = 200

    return (
        {
            "data_class": "MEMBER_SAFE_HEALTH",
            "product": "personal_market_intelligence",
            "overall": overall,
            "critical_unavailable": critical_down,
            "dependencies": dependencies,
        },
        http,
    )

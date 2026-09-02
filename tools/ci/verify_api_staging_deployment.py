#!/usr/bin/env python3
"""Redacted HTTPS verification for deployed nexus-api-staging.

The expected browser Origin for the CORS check is NOT hard-coded to a specific
environment. It is supplied by the workflow via PERSONAL_STAGING_ORIGIN so the
verifier follows the real product architecture (the canonical Personal staging
origin) instead of a retired Member Preview host. Absent/invalid origin fails
closed. The verifier also proves that Workstream-B routes are actually serving.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

RE_DSN = re.compile(r"postgres(?:ql)?://\S+", re.I)
# Canonical Personal staging origin — the browser origin the deployed API must
# allow. Read from the environment (workflow-configurable); no retired
# member-preview origin is baked in.
EXPECTED_ORIGIN_ENV = "PERSONAL_STAGING_ORIGIN"
_ORIGIN_RE = re.compile(r"^https://[a-z0-9.-]+\.zeabur\.app$", re.I)


def _expected_origin() -> str:
    origin = (os.environ.get(EXPECTED_ORIGIN_ENV) or "").strip().rstrip("/")
    if not _ORIGIN_RE.match(origin):
        # Fail closed: never fall back to a hard-coded environment origin.
        print(json.dumps({"ok": False, "error": "invalid_or_missing_PERSONAL_STAGING_ORIGIN",
                          "value": origin}))
        raise SystemExit(2)
    return origin


def _request(url: str, *, method: str = "GET", headers: dict[str, str] | None = None):
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers, method=method)
    return urllib.request.urlopen(req, timeout=30)


def _fetch(url: str) -> dict:
    with _request(url) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    raw = RE_DSN.sub("<REDACTED>", raw)
    return json.loads(raw)


def _status_and_body(url: str) -> tuple[int, dict | None]:
    """GET a URL, returning (status_code, parsed_json_or_None) without raising on
    4xx/5xx so route-existence can be asserted (401 exists, 404 missing)."""
    try:
        with _request(url) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        try:
            return resp.status, json.loads(RE_DSN.sub("<REDACTED>", raw))
        except json.JSONDecodeError:
            return resp.status, None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except urllib.error.URLError:
        return 0, None


def _options_headers(url: str, origin: str) -> dict[str, str]:
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type, X-Nexus-Session, X-Nexus-CSRF",
    }
    with _request(url, method="OPTIONS", headers=headers) as resp:
        return {key.lower(): value for key, value in resp.headers.items()}


def _catalog_contract_ok(catalog: dict | None) -> bool:
    """The canonical Personal commercial contract must be intact."""
    if not isinstance(catalog, dict):
        return False
    commercial = catalog.get("commercial") or {}
    if commercial.get("annual_discount_pct") != 20:
        return False
    trial = commercial.get("trial") or {}
    if trial.get("code") != "STARTER_TRIAL_30D" or trial.get("days") != 30 or trial.get("auto_charge") is not False:
        return False
    by_code = {p.get("code"): p for p in (commercial.get("plans") or []) if isinstance(p, dict)}
    for code in ("free", "starter", "pro", "advanced", "enterprise"):
        if code not in by_code:
            return False
    prices = {"starter": 19, "pro": 39, "advanced": 79}
    for code, monthly in prices.items():
        if by_code[code].get("monthly_usd") != monthly:
            return False
    if by_code["enterprise"].get("contact_sales") is not True:
        return False
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_api_staging_deployment.py <base_url>", file=sys.stderr)
        return 2
    origin = _expected_origin()  # fails closed if absent/invalid
    base = sys.argv[1].rstrip("/")
    try:
        health = _fetch(f"{base}/health")
        product = _fetch(f"{base}/api/v1/product/health")
        readiness = _fetch(f"{base}/api/v1/product/readiness")
        auth_foundation = _fetch(f"{base}/api/v1/product/auth/foundation")
        capabilities = _fetch(f"{base}/api/v1/product/capabilities")
        snapshot = _fetch(f"{base}/api/v1/market/snapshot")
        history = _fetch(f"{base}/api/v1/market/history?symbol=BTCUSDT&interval=1h&limit=2")
        rankings = _fetch(f"{base}/api/v1/market/rankings?metric=gainers&limit=2")
        cors_headers = _options_headers(f"{base}/api/v1/member/session", origin)
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}))
        return 1

    # Workstream-B route activation markers (durable proof the B code is serving).
    catalog_status, catalog_body = _status_and_body(f"{base}/api/v1/personal/catalog")
    market_state_status, _ = _status_and_body(f"{base}/api/v1/personal/market-state")
    subscription_status, _ = _status_and_body(f"{base}/api/v1/personal/subscription")

    pg = product.get("postgres") or {}
    shadow = product.get("shadow_readonly") or {}
    cors_allow_headers = cors_headers.get("access-control-allow-headers", "")
    out = {
        "ok": True,
        "expected_origin": origin,
        "health_status": health.get("status"),
        "postgres_status": pg.get("status"),
        "postgres_configured": pg.get("configured"),
        "postgres_connected": pg.get("connected"),
        "runtime_binding": shadow.get("binding"),
        "readiness_ready": readiness.get("ready"),
        "readiness_checks": readiness.get("checks"),
        "auth_foundation_status": auth_foundation.get("status"),
        "inline_verification_token_allowed_in_production": auth_foundation.get(
            "inline_verification_token_allowed_in_production"
        ),
        "cors_origin_allowed": cors_headers.get("access-control-allow-origin") == origin,
        "cors_csrf_header_allowed": "x-nexus-csrf" in cors_allow_headers.lower(),
        "cors_session_header_allowed": "x-nexus-session" in cors_allow_headers.lower(),
        "capabilities_ok": (capabilities.get("validation") or {}).get("ok"),
        "market_snapshot_class": snapshot.get("data_class"),
        "market_history_symbol": history.get("symbol"),
        "market_rankings_class": rankings.get("classification"),
        # Workstream-B activation markers.
        "personal_catalog_status": catalog_status,
        "personal_catalog_contract_ok": _catalog_contract_ok(catalog_body),
        "personal_market_state_status": market_state_status,
        "personal_subscription_status": subscription_status,
    }
    print(json.dumps(out))

    if not readiness.get("ready"):
        return 1
    if shadow.get("binding") != "UNAVAILABLE":
        return 1
    if (capabilities.get("validation") or {}).get("ok") is not True:
        return 1
    if auth_foundation.get("inline_verification_token_allowed_in_production") is not False:
        return 1
    if cors_headers.get("access-control-allow-origin") != origin:
        return 1
    if "x-nexus-csrf" not in cors_allow_headers.lower():
        return 1
    if "x-nexus-session" not in cors_allow_headers.lower():
        return 1
    if snapshot.get("data_class") != "LIVE_READ_ONLY":
        return 1
    if history.get("symbol") != "BTCUSDT":
        return 1
    if rankings.get("classification") != "LIVE_API":
        return 1
    # Workstream-B routes must be live and honest.
    if catalog_status != 200 or not _catalog_contract_ok(catalog_body):
        return 1
    if market_state_status == 404:  # route must exist (data may be honestly unavailable)
        return 1
    if subscription_status == 404:  # 401 (auth required) proves the route exists; 404 does not
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

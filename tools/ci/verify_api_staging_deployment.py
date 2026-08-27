#!/usr/bin/env python3
"""Redacted HTTPS verification for deployed nexus-api-staging."""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request

RE_DSN = re.compile(r"postgres(?:ql)?://\S+", re.I)
MEMBER_PREVIEW_ORIGIN = "https://nexus-member-preview-v18-2-1.zeabur.app"


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


def _options_headers(url: str) -> dict[str, str]:
    headers = {
        "Origin": MEMBER_PREVIEW_ORIGIN,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Content-Type, X-Nexus-CSRF",
    }
    with _request(url, method="OPTIONS", headers=headers) as resp:
        return {key.lower(): value for key, value in resp.headers.items()}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_api_staging_deployment.py <base_url>", file=sys.stderr)
        return 2
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
        cors_headers = _options_headers(f"{base}/api/v1/member/session")
    except (urllib.error.URLError, json.JSONDecodeError, KeyError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__}))
        return 1
    pg = product.get("postgres") or {}
    shadow = product.get("shadow_readonly") or {}
    cors_allow_headers = cors_headers.get("access-control-allow-headers", "")
    out = {
        "ok": True,
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
        "cors_origin_allowed": cors_headers.get("access-control-allow-origin") == MEMBER_PREVIEW_ORIGIN,
        "cors_csrf_header_allowed": "x-nexus-csrf" in cors_allow_headers.lower(),
        "capabilities_ok": (capabilities.get("validation") or {}).get("ok"),
        "market_snapshot_class": snapshot.get("data_class"),
        "market_history_symbol": history.get("symbol"),
        "market_rankings_class": rankings.get("classification"),
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
    if cors_headers.get("access-control-allow-origin") != MEMBER_PREVIEW_ORIGIN:
        return 1
    if "x-nexus-csrf" not in cors_allow_headers.lower():
        return 1
    if snapshot.get("data_class") != "LIVE_READ_ONLY":
        return 1
    if history.get("symbol") != "BTCUSDT":
        return 1
    if rankings.get("classification") != "LIVE_API":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

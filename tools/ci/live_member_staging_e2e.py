"""HTTPS-only staging member-state E2E without printing credentials or cookies."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar


BASE = os.environ.get("NEXUS_API_BASE_URL", "https://nexus-api-staging.zeabur.app").rstrip("/")
EMAIL = os.environ["NEXUS_STAGING_SEED_EMAIL"]
PASSWORD = os.environ["NEXUS_STAGING_SEED_PASSWORD"]


def request(path: str, method: str = "GET", body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    request_headers = {"Accept": "application/json"}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    request_headers.update(headers or {})
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method, headers=request_headers)
    try:
        with OPENER.open(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def require(status: int, expected: int, label: str) -> dict:
    if status != expected:
        raise AssertionError(f"{label}: expected {expected}, got {status}")
    return {}


JAR = CookieJar()
OPENER = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(JAR))


def main() -> int:
    checks: dict[str, bool] = {}
    status, _ = request("/api/v1/member/session/login", "POST", {"email": EMAIL, "password": PASSWORD})
    require(status, 200, "seeded_login")
    checks["seeded_login"] = True

    status, session = request("/api/v1/member/session")
    require(status, 200, "seeded_session")
    checks["seeded_session"] = bool(session.get("staging_only"))

    symbol = "BTCUSDT"
    request("/api/v1/member/watchlist", "DELETE", {"symbol": symbol})
    status, added = request("/api/v1/member/watchlist", "POST", {"symbol": symbol})
    require(status, 200, "watchlist_add")
    status, loaded = request("/api/v1/member/watchlist")
    require(status, 200, "watchlist_refresh")
    checks["watchlist_add_persist"] = symbol in added.get("symbols", []) and symbol in loaded.get("symbols", [])
    status, removed = request("/api/v1/member/watchlist", "DELETE", {"symbol": symbol})
    require(status, 200, "watchlist_remove")
    status, loaded = request("/api/v1/member/watchlist")
    require(status, 200, "watchlist_remove_refresh")
    checks["watchlist_remove_persist"] = symbol not in removed.get("symbols", []) and symbol not in loaded.get("symbols", [])

    preferences = {"market_digest": True, "risk_notice": False, "e2e_marker": "staging"}
    status, saved = request("/api/v1/member/preferences", "PUT", preferences)
    require(status, 200, "preferences_save")
    status, loaded = request("/api/v1/member/preferences")
    require(status, 200, "preferences_refresh")
    checks["preferences_persist"] = loaded.get("preferences") == saved.get("preferences")

    notifications = {
        "in_app_enabled": True,
        "market_alerts_enabled": True,
        "email_enabled": False,
        "muted_symbols": [],
    }
    status, saved = request("/api/v1/member/notification-preferences", "PATCH", notifications)
    require(status, 200, "alert_state_save")
    status, loaded = request("/api/v1/member/notification-preferences")
    require(status, 200, "alert_state_refresh")
    checks["alert_state_persist"] = loaded.get("preferences") == saved.get("preferences")

    status, entitlements = request("/api/v1/member/entitlements")
    require(status, 200, "membership_read")
    checks["membership_live_member_db"] = entitlements.get("classification") == "LIVE_MEMBER_DB"

    status, _ = request("/api/v1/member/session/logout", "POST")
    require(status, 200, "session_revoke")
    status, _ = request("/api/v1/member/session")
    checks["revoked_session_denied"] = status == 401

    if not all(checks.values()):
        raise AssertionError(f"failed_checks:{[key for key, value in checks.items() if not value]}")
    print(json.dumps({"ok": True, "checks": checks, "credentials": "not_printed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

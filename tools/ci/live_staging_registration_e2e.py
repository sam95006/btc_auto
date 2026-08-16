"""HTTPS staging registration E2E; never prints credentials, cookies, or account IDs."""
from __future__ import annotations

import json
import secrets
import urllib.error
import urllib.request
from http.cookiejar import CookieJar


BASE = "https://nexus-api-staging.zeabur.app/api/v1"


def request(opener, path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json", "Origin": "https://nexus-member-preview-v18-2-1.zeabur.app"}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        with opener.open(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode() or "{}")


def need(status: int, expected: int, name: str) -> None:
    if status != expected:
        raise AssertionError(f"{name}:{status}")


def main() -> int:
    nonce = secrets.token_hex(12)
    email = f"member-e2e-{nonce}@invalid.example"
    password = f"Temporary-{nonce}-Member!"
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    payload = {
        "display_name": "Registration E2E",
        "email": email,
        "password": password,
        "confirm_password": password,
        # These must be ignored by the server.
        "role": "FOUNDER",
        "tier": "ENTERPRISE",
        "permissions": ["org.owner"],
    }
    status, registered = request(opener, "/member/registration", "POST", payload)
    need(status, 201, "member_registration")
    assert registered.get("role") == "MEMBER" and registered.get("tier") == "FREE"
    status, duplicate = request(opener, "/member/registration", "POST", payload)
    need(status, 409, "duplicate_email")
    assert duplicate.get("error") == "email_already_registered"
    status, _ = request(opener, "/member/watchlist", "POST", {"symbol": "BTCUSDT"})
    need(status, 200, "watchlist_add")
    status, saved = request(opener, "/member/preferences", "PUT", {"registration_e2e": True})
    need(status, 200, "preferences_save")
    status, founder = request(opener, "/founder/operator")
    need(status, 403, "member_founder_denial")
    status, _ = request(opener, "/member/session/logout", "POST")
    need(status, 200, "logout")
    status, _ = request(opener, "/member/session", "GET")
    need(status, 401, "logout_denial")
    status, _ = request(opener, "/member/session/login", "POST", {"email": email, "password": password})
    need(status, 200, "registered_login")
    status, watchlist = request(opener, "/member/watchlist")
    need(status, 200, "watchlist_persistence")
    status, preferences = request(opener, "/member/preferences")
    need(status, 200, "preferences_persistence")
    assert "BTCUSDT" in watchlist.get("symbols", [])
    assert preferences.get("preferences") == saved.get("preferences")
    print(json.dumps({
        "ok": True,
        "NORMAL_MEMBER_RBAC_E2E_PASS": True,
        "REGISTERED_MEMBER_PERSISTENCE_PASS": True,
        "REGISTRATION_SECURITY_BOUNDARY_PASS": True,
        "credentials": "not_printed",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

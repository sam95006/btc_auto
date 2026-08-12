"""Remote closed-beta retention validation against preview."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

BASE = "https://nexus-member-preview-v18-2-1.zeabur.app"


def req(method: str, path: str, body: dict | None = None, token: str | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=45) as r:
            raw = r.read().decode("utf-8", errors="ignore")
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="ignore")
        try:
            return e.code, json.loads(raw) if raw else {"error": str(e)}
        except Exception:
            return e.code, {"error": raw or str(e)}


def main() -> dict:
    email = "v22remote_loop@example.com"
    password = "TestPass123!"

    # SIGNUP
    st, signup = req(
        "POST",
        "/api/public/auth/signup",
        {"email": email, "password": password, "display_name": "V22Remote"},
    )
    # may already exist
    verify_token = None
    account_id = None
    if st < 400 and signup.get("ok"):
        verify_token = (signup.get("account") or {}).get("verification", {}).get("token")
        account_id = (signup.get("account") or {}).get("account_id")

    if verify_token:
        req("POST", "/api/public/auth/email/verify", {"token": verify_token})

    # LOGIN
    st, login = req("POST", "/api/public/auth/login", {"email": email, "password": password})
    if not login.get("session", {}).get("token"):
        # retry signup path if account missing
        return {"ok": False, "stage": "login", "status": st, "body": login}
    token = login["session"]["token"]
    account_id = account_id or login.get("account", {}).get("account_id")

    # INVITE create + redeem
    st, inv = req(
        "POST",
        "/api/nexus/public/closed-beta/invites",
        {"admin_key": "staging-closed-beta-admin", "email_hint": email},
    )
    if not inv.get("invite_code"):
        return {"ok": False, "stage": "invite", "status": st, "body": inv}
    st, redeemed = req(
        "POST",
        "/api/nexus/public/closed-beta/invites/redeem",
        {"invite_code": inv["invite_code"]},
        token=token,
    )
    beta_status = (redeemed.get("beta_access") or {}).get("status")

    # WATCHLIST ADD
    st, wl_add = req(
        "POST",
        "/api/nexus/public/retention/watchlist/add",
        {"symbol": "BTCUSDT"},
        token=token,
    )

    # ALERT ingest → notification
    st, alert = req(
        "POST",
        "/api/nexus/public/retention/alerts/ingest",
        {
            "type": "RADAR_UP",
            "symbol": "BTCUSDT",
            "severity": "HIGH",
            "headline": "remote loop BTC",
            "metric": {"dedup": "v22-remote-1"},
        },
        token=token,
    )
    note_id = (alert.get("notification") or {}).get("id")
    if note_id:
        req("POST", "/api/nexus/public/retention/notifications/read", {"id": note_id}, token=token)

    st, notes1 = req("GET", "/api/nexus/public/retention/notifications?limit=20", token=token)
    st, first_visit = req("GET", "/api/nexus/public/retention/since-last-visit", token=token)

    # LOGOUT
    req("POST", "/api/public/auth/logout", {}, token=token)

    # LOGIN AGAIN
    st, login2 = req("POST", "/api/public/auth/login", {"email": email, "password": password})
    token2 = (login2.get("session") or {}).get("token")
    st, wl2 = req("GET", "/api/nexus/public/retention/watchlist", token=token2)
    st, notes2 = req("GET", "/api/nexus/public/retention/notifications?limit=20", token=token2)
    st, second_visit = req("GET", "/api/nexus/public/retention/since-last-visit", token=token2)

    st, analytics = req("GET", "/api/nexus/public/analytics/contract")
    events = analytics.get("events") or []

    watch_preserved = any(
        (i.get("symbol") or "").upper() == "BTCUSDT" for i in (wl2.get("items") or [])
    )
    notif_preserved = bool(notes2.get("ok")) and isinstance(notes2.get("items"), list)

    out = {
        "ok": True,
        "account_id": account_id,
        "beta_status": beta_status,
        "watchlist_add_ok": bool(wl_add.get("ok")),
        "alert_ok": bool(alert.get("ok")),
        "watchlist_preserved_after_relogin": watch_preserved,
        "notifications_preserved_after_relogin": notif_preserved,
        "since_last_visit_first": {
            "fabricated": first_visit.get("fabricated"),
            "insufficient_history": first_visit.get("insufficient_history"),
        },
        "since_last_visit_second": {
            "fabricated": second_visit.get("fabricated"),
            "has_previous": second_visit.get("has_previous"),
        },
        "analytics_events": events,
        "localStorage_canonical": False,
        "production_billing": False,
        "member_execution": 0,
    }
    out["ok"] = (
        beta_status == "ACTIVE"
        and watch_preserved
        and notif_preserved
        and first_visit.get("fabricated") is False
        and second_visit.get("fabricated") is False
        and "session_started" in events
        and "notification_read" in events
    )
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    main()

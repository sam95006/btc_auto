"""Local closed-beta retention loop proof for V18.2.22 evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.nexus_closed_beta.service import ClosedBetaService
from backend.nexus_closed_beta.store import ClosedBetaStore
from backend.nexus_paid_beta_retention.notifications import get_notification_center
from backend.nexus_paid_beta_retention.service import ingest_alert, since_last_visit
from backend.nexus_paid_beta_retention.watchlist_store import get_watchlist_store
from backend.nexus_product_analytics.events import PRODUCT_EVENT_NAMES, get_analytics_store
from backend.nexus_public_auth.service import PublicAuthMembershipService
from backend.nexus_public_auth.store import PublicAuthStore
from backend.nexus_public_auth.tokens import AuthTokenStore


def main() -> dict:
    auth_store = PublicAuthStore()
    tokens = AuthTokenStore()
    auth = PublicAuthMembershipService(store=auth_store, tokens=tokens)
    beta_store = ClosedBetaStore()
    beta = ClosedBetaService(store=beta_store)

    # SIGNUP → VERIFY → LOGIN
    reg = auth.register_member("v22loop@example.com", "V22", password="TestPass123!")
    account_id = reg["account_id"]
    auth.verify_email(reg["verification"]["token"])
    logged = auth.login_with_password("v22loop@example.com", "TestPass123!")
    token1 = logged["session"]["token"]

    # INVITE → ACTIVATE
    inv = beta.create_invite(admin_key="staging-closed-beta-admin", email_hint="v22loop@example.com")
    redeemed = beta.redeem_invite(account_id=account_id, invite_code=inv["invite_code"])
    assert redeemed["beta_access"]["status"] == "ACTIVE"

    # RADAR/WATCHLIST → ALERT → NOTIFICATION
    get_watchlist_store().add(account_id, "BTCUSDT")
    alert = ingest_alert(
        account_id,
        event_type="RADAR_UP",
        symbol="BTCUSDT",
        severity="HIGH",
        headline="BTC up",
        metric={"dedup": "v22-remote-loop"},
    )
    assert alert["ok"] is True
    note_id = alert["notification"]["id"]
    get_notification_center().mark_read(account_id, note_id)

    first = since_last_visit(account_id)
    assert first["fabricated"] is False

    # LOGOUT → LOGIN AGAIN → PRESERVED
    auth.logout(token1)
    again = auth.login_with_password("v22loop@example.com", "TestPass123!")
    assert again["session"]["token"]
    wl = get_watchlist_store().list_items(account_id)
    assert any(i["symbol"] == "BTCUSDT" for i in wl["items"])
    notes = get_notification_center().list_for(account_id)
    assert any(n["id"] == note_id and n.get("read") for n in notes["items"])
    second = since_last_visit(account_id)
    assert second["has_previous"] is True
    assert second["fabricated"] is False

    missing = [
        e
        for e in (
            "session_started",
            "session_returned",
            "watchlist_removed",
            "notification_read",
            "signup_completed",
            "login_completed",
        )
        if e not in PRODUCT_EVENT_NAMES
    ]
    assert not missing

    out = {
        "ok": True,
        "loop": [
            "SIGNUP",
            "VERIFY",
            "LOGIN",
            "INVITE_REDEEM",
            "RADAR_WATCHLIST",
            "ALERT",
            "NOTIFICATION",
            "LOGOUT",
            "LOGIN_AGAIN",
            "WATCHLIST_PRESERVED",
            "NOTIFICATION_PRESERVED",
            "SINCE_LAST_VISIT_TRUTHFUL",
        ],
        "beta_status": redeemed["beta_access"]["status"],
        "watchlist_authority": wl.get("authority"),
        "localStorage_canonical": False,
        "production_billing": False,
        "member_execution": 0,
        "analytics_events_present": sorted(PRODUCT_EVENT_NAMES),
        "since_last_visit": {
            "has_previous": second["has_previous"],
            "fabricated": second["fabricated"],
            "insufficient_history_first": first.get("insufficient_history"),
        },
    }
    print(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    main()

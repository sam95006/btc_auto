#!/usr/bin/env python3
"""Narrow, READ-ONLY authenticated Workstream-B E2E against Personal staging.

This runs the SAME normal login path the product uses (the real
``POST /api/v1/member/session/login`` endpoint) with a NORMAL member account,
then exercises authenticated read endpoints to prove the authenticated runtime
truth. It NEVER:

  * uses a Founder session / Founder claim / bootstrap / fake / hard-coded token;
  * injects a cookie manually or bypasses authentication;
  * touches PostgreSQL directly (no DB port, no direct query);
  * prints the email, password, cookie, session id, Authorization/CSRF header,
    account_id, the raw registration timestamp, or the DB URL.

Session material (the ``nexus_session`` cookie + CSRF token) lives ONLY in the
process's in-memory cookie jar / a local variable for the lifetime of the run;
nothing is written to disk and nothing sensitive is logged. Only sanitized
non-sensitive markers and fields are printed.

Inputs (from the GitHub ``staging-personal-e2e`` Environment, via env vars):

  NEXUS_STAGING_E2E_EMAIL       normal member email
  NEXUS_STAGING_E2E_PASSWORD    that member's password
  NEXUS_PERSONAL_E2E_API_ORIGIN API origin (optional; sane staging default)

Fails closed (exit 1 + ``AUTHENTICATED_WORKSTREAM_B_E2E=no``) on any deviation.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

DEFAULT_API_ORIGIN = "https://nexus-api-staging.zeabur.app"

# Canonical Starter-trial contract truth (mirrors backend/nexus_platform:
# STARTER_TRIAL_30D — 30 days, no auto-charge, paid-else-free on expiry). The
# live catalog is asserted against these so a silent backend drift fails closed.
EXPECTED_TRIAL_DAYS = 30
EXPECTED_ON_EXPIRY = "paid_else_free"

# Canonical Personal plan codes + the separate Enterprise (contact-sales) tier.
EXPECTED_PERSONAL_PLANS = ("free", "starter", "pro", "advanced")
ENTERPRISE_CODE = "enterprise"
# Enterprise is a SEPARATE product / contact-sales surface — it is NEVER a valid
# Personal effective plan, so it is deliberately excluded from the paid allowlist.
PAID_PLANS = ("starter", "pro", "advanced")

# Exact Starter-trial length (registration origin -> +30 days).
TRIAL_LENGTH = timedelta(days=EXPECTED_TRIAL_DAYS)


class E2EError(Exception):
    """A fatal, fail-closed E2E deviation (message is always non-sensitive)."""


# --------------------------------------------------------------------------- #
# Pure validators (no network / no secrets) — imported by tests.
# --------------------------------------------------------------------------- #
def validate_trial_truth(effective_plan: str, trial: dict, trial_contract: dict) -> None:
    """Assert the LIVE subscription is internally consistent with the canonical
    Starter-trial contract, derived from the account's registration origin.

    Proves (without any DB access) the rules the task requires:
      * 30-day Starter trial, auto_charge=False, expiry => paid-else-free;
      * paid wins (PAID => effective is the paid plan, trial inactive);
      * active trial => Starter with days_remaining in (0, 30] and an end date;
      * expired trial with no paid plan => Free.
    Raises E2EError on any inconsistency; UNAVAILABLE is treated as unverifiable
    (fail closed) because trial truth could not be established.
    """
    if trial_contract.get("days") != EXPECTED_TRIAL_DAYS:
        raise E2EError("trial_contract_days_not_30")
    if trial_contract.get("on_expiry") != EXPECTED_ON_EXPIRY:
        raise E2EError("trial_contract_on_expiry_not_paid_else_free")
    if trial_contract.get("auto_charge") is not False:
        raise E2EError("trial_contract_auto_charge_not_false")

    # Enterprise is a separate product and must NEVER be a Personal effective plan.
    if effective_plan == ENTERPRISE_CODE:
        raise E2EError("enterprise_is_not_a_personal_effective_plan")

    state = trial.get("state")
    active = bool(trial.get("trial_active"))
    days_remaining = trial.get("days_remaining")

    if state == "PAID":
        if active:
            raise E2EError("paid_state_but_trial_active")
        if effective_plan not in PAID_PLANS or effective_plan == "free":
            raise E2EError("paid_state_effective_plan_not_paid")
        if trial.get("plan") and effective_plan != trial.get("plan"):
            raise E2EError("paid_state_effective_plan_mismatch")
    elif state == "TRIAL":
        if not active:
            raise E2EError("trial_state_not_active")
        if effective_plan != "starter":
            raise E2EError("trial_state_effective_plan_not_starter")
        if not isinstance(days_remaining, int) or not (0 < days_remaining <= EXPECTED_TRIAL_DAYS):
            raise E2EError("trial_state_days_remaining_out_of_range")
        if not trial.get("trial_ends_at"):
            raise E2EError("trial_state_missing_end_date")
    elif state == "TRIAL_EXPIRED":
        if active:
            raise E2EError("expired_state_but_trial_active")
        if effective_plan != "free":
            raise E2EError("expired_trial_effective_plan_not_free")
        if days_remaining not in (0, None):
            raise E2EError("expired_trial_days_remaining_nonzero")
    elif state == "FREE":
        if active:
            raise E2EError("free_state_but_trial_active")
        if effective_plan != "free":
            raise E2EError("free_state_effective_plan_not_free")
    else:  # UNAVAILABLE or unknown -> trial truth could not be established.
        raise E2EError(f"trial_state_unverifiable:{state}")


def _parse_aware(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp to a timezone-AWARE datetime (naive => UTC).
    Returns None if the value is missing or unparseable."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def validate_registration_anchor(session_created_at: Any, trial: dict) -> None:
    """Prove the LIVE trial is anchored to the account's ORIGINAL registration
    timestamp — WITHOUT any DB access. For a trial-bearing account:

        trial.trial_started_at == session.created_at   (same instant)
        trial.trial_ends_at - trial.trial_started_at == exactly 30 days

    Raises E2EError (fail closed) if any timestamp is missing/unparseable or the
    values are inconsistent. Only instants are compared; nothing is returned or
    printed (the raw timestamps must never be logged)."""
    registered = _parse_aware(session_created_at)
    if registered is None:
        raise E2EError("anchor_session_created_at_missing")
    started = _parse_aware(trial.get("trial_started_at"))
    ends = _parse_aware(trial.get("trial_ends_at"))
    if started is None or ends is None:
        raise E2EError("anchor_trial_timestamps_missing")
    if started != registered:
        raise E2EError("anchor_trial_start_ne_registration")
    if (ends - started) != TRIAL_LENGTH:
        raise E2EError("anchor_interval_not_30_days")


def validate_membership_catalog(catalog: dict) -> None:
    """Assert the canonical plan catalog: Free/Starter/Pro/Advanced present and
    Enterprise present-but-separate (contact-sales, not a self-serve Personal
    price tier). Raises E2EError otherwise."""
    commercial = catalog.get("commercial") or {}
    plans = commercial.get("plans") or []
    by_code = {str(p.get("code")): p for p in plans if isinstance(p, dict)}
    for code in EXPECTED_PERSONAL_PLANS:
        if code not in by_code:
            raise E2EError(f"catalog_missing_plan:{code}")
    ent = by_code.get(ENTERPRISE_CODE)
    if ent is None:
        raise E2EError("catalog_missing_enterprise")
    if not ent.get("contact_sales"):
        raise E2EError("enterprise_not_contact_sales")
    if ent.get("monthly_usd") is not None or ent.get("monthly_usd_cents") is not None:
        raise E2EError("enterprise_has_self_serve_price")


def sanitized_subscription_view(effective_plan: str, trial: dict, trial_contract: dict) -> dict:
    """The ONLY subscription fields safe to log. Deliberately excludes
    trial_started_at / created_at (which would reveal the raw registration
    timestamp) and every credential/identity field."""
    return {
        "effective_plan": effective_plan,
        "trial_active": bool(trial.get("trial_active")),
        "trial_state": trial.get("state"),
        "days_remaining": trial.get("days_remaining"),
        "trial_ends_at": trial.get("trial_ends_at"),
        "auto_charge": trial_contract.get("auto_charge"),
    }


# --------------------------------------------------------------------------- #
# HTTP (in-memory cookie jar; nothing sensitive logged).
# --------------------------------------------------------------------------- #
def _build_opener() -> urllib.request.OpenerDirector:
    jar = http.cookiejar.CookieJar()  # in-memory only; never persisted to disk
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _request(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    *,
    json_body: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> tuple[int, dict]:
    data = None
    hdrs = {"Accept": "application/json"}
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with opener.open(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        status = exc.code
    except urllib.error.URLError as exc:
        raise E2EError(f"network_error:{type(exc).__name__}")
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {}
    return status, payload


# --------------------------------------------------------------------------- #
# Live E2E.
# --------------------------------------------------------------------------- #
def run() -> int:
    origin = (os.getenv("NEXUS_PERSONAL_E2E_API_ORIGIN") or DEFAULT_API_ORIGIN).strip().rstrip("/")
    email = (os.getenv("NEXUS_STAGING_E2E_EMAIL") or "").strip().lower()
    password = os.getenv("NEXUS_STAGING_E2E_PASSWORD") or ""
    if not email or not password:
        print("E2E_MISSING_INPUTS=yes")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1

    opener = _build_opener()

    # 1) NORMAL member login through the real product endpoint.
    status, body = _request(
        opener, "POST", f"{origin}/api/v1/member/session/login",
        json_body={"email": email, "password": password},
    )
    if status == 404:
        print("MEMBER_AUTH_DISABLED=yes")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1
    if status != 200:
        print(f"NORMAL_MEMBER_LOGIN=no login_http={status}")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1
    csrf_token = str(body.get("csrf_token") or "")  # in-memory only; never printed
    print("NORMAL_MEMBER_LOGIN=yes")

    # 2) Authenticated subscription (200 + non-sensitive truth).
    status, sub = _request(opener, "GET", f"{origin}/api/v1/personal/subscription")
    print(f"AUTHENTICATED_SUBSCRIPTION_HTTP={status}")
    if status != 200:
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1
    effective_plan = str(sub.get("effective_plan") or "")
    trial = sub.get("trial") or {}
    trial_contract = sub.get("trial_contract") or {}
    try:
        validate_trial_truth(effective_plan, trial, trial_contract)
    except E2EError as exc:
        print(f"TRIAL_TRUTH_VALID=no reason={exc}")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1
    print("TRIAL_TRUTH_VALID=yes")
    print("AUTO_CHARGE_FALSE=" + ("yes" if trial_contract.get("auto_charge") is False else "no"))
    print("SUBSCRIPTION_SANITIZED=" + json.dumps(sanitized_subscription_view(effective_plan, trial, trial_contract)))
    if trial_contract.get("auto_charge") is not False:
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1

    # 2b) LIVE trial registration-anchor proof (no DB): the trial must start at
    #     the account's ORIGINAL registration timestamp and last exactly 30 days.
    #     session.created_at comes from the authenticated member session identity;
    #     trial_started_at / trial_ends_at from the subscription. Raw values are
    #     never printed.
    s_session, sess_body = _request(opener, "GET", f"{origin}/api/v1/member/session")
    if s_session != 200:
        print(f"TRIAL_REGISTRATION_ANCHOR_VALID=no session_http={s_session}")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1
    session_created_at = (sess_body.get("session") or {}).get("created_at")
    try:
        validate_registration_anchor(session_created_at, trial)
    except E2EError as exc:
        print(f"TRIAL_REGISTRATION_ANCHOR_VALID=no reason={exc}")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1
    print("TRIAL_REGISTRATION_ANCHOR_VALID=yes")

    # 3) Authenticated Personal Home / API access (member session + per-member
    #    features, the Home's plan/feature source).
    s_feat, feat = _request(opener, "GET", f"{origin}/api/v1/personal/features")
    home_ok = (
        s_feat == 200
        and str(feat.get("effective_plan_code") or "") == effective_plan
    )
    print("PERSONAL_HOME_AUTHENTICATED=" + ("yes" if home_ok else "no"))
    if not home_ok:
        print(f"(session_http={s_session} features_http={s_feat})")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1

    # 4) Membership catalog (Free/Starter/Pro/Advanced; Enterprise separate).
    s_cat, catalog = _request(opener, "GET", f"{origin}/api/v1/personal/catalog")
    if s_cat != 200:
        print(f"MEMBERSHIP_CATALOG_VALID=no catalog_http={s_cat}")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1
    try:
        validate_membership_catalog(catalog)
    except E2EError as exc:
        print(f"MEMBERSHIP_CATALOG_VALID=no reason={exc}")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1
    print("MEMBERSHIP_CATALOG_VALID=yes")
    print("ENTERPRISE_SEPARATE=yes")

    # 5) View Mode does NOT grant authorization. A spoofed view-mode hint (header
    #    + query) must NOT change the backend-authoritative effective plan or the
    #    entitled feature set.
    spoof_headers = {"X-Nexus-View-Mode": "pro"}
    spoof_qs = "?view=advanced&view_mode=pro&plan=advanced"
    _, sub2 = _request(
        opener, "GET", f"{origin}/api/v1/personal/subscription{spoof_qs}", headers=spoof_headers
    )
    _, feat2 = _request(
        opener, "GET", f"{origin}/api/v1/personal/features{spoof_qs}", headers=spoof_headers
    )
    def _entitled(f: dict) -> list[str]:
        return sorted(x.get("key") for x in (f.get("features") or []) if x.get("entitled"))
    view_neutral = (
        str(sub2.get("effective_plan") or "") == effective_plan
        and str(feat2.get("effective_plan_code") or "") == effective_plan
        and _entitled(feat2) == _entitled(feat)
    )
    print("VIEW_MODE_AUTH_NEUTRAL=" + ("yes" if view_neutral else "no"))
    if not view_neutral:
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1

    # 6) Session cleanup: logout (cookie session => CSRF required), then confirm
    #    the session is truly revoked (subscription returns 401).
    s_logout, _ = _request(
        opener, "POST", f"{origin}/api/v1/member/session/logout",
        headers={"X-Nexus-CSRF": csrf_token} if csrf_token else None,
    )
    s_after, _ = _request(opener, "GET", f"{origin}/api/v1/personal/subscription")
    cleanup_ok = s_logout == 200 and s_after == 401
    print("SESSION_CLEANUP=" + ("yes" if cleanup_ok else "no"))
    if not cleanup_ok:
        print(f"(logout_http={s_logout} post_logout_subscription_http={s_after})")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1

    print("AUTHENTICATED_WORKSTREAM_B_E2E=yes")
    return 0


def main() -> int:
    try:
        return run()
    except E2EError as exc:
        print(f"E2E_FATAL={exc}")
        print("AUTHENTICATED_WORKSTREAM_B_E2E=no")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

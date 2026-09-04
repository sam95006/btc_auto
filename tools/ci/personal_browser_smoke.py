#!/usr/bin/env python3
"""Narrow, CORRECTNESS-ONLY authenticated Personal browser smoke (Playwright).

Loads the REAL Personal web app at two viewports (desktop 1440x900 + mobile
390x844) and, using the SAME protected-Environment normal-member credentials,
verifies the authenticated runtime end-to-end in a real browser:

  login visible -> real UI login -> authenticated /app -> session survives reload
  -> authenticated membership/plans surface -> Personal plans Free/Starter/Pro/
  Advanced -> Enterprise separate (never a Personal effective plan) -> no Founder
  Private / trading-execution UI -> logout -> /app redirects back to /login.

This is CORRECTNESS ONLY. It makes NO judgement about commercial visual quality
(that redesign is NEXUS-EXPERIENCE-1C). It never prints the email / password /
cookie / session id, never writes session storage to disk, and creates a fresh
incognito context per viewport.

Inputs (env, from the staging-personal-e2e Environment):
  NEXUS_STAGING_E2E_EMAIL / NEXUS_STAGING_E2E_PASSWORD  normal-member creds
  NEXUS_PERSONAL_E2E_WEB_ORIGIN                         web origin (optional)
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

DEFAULT_WEB_ORIGIN = "https://nexus-personal-staging.zeabur.app"

VIEWPORTS = [
    ("PERSONAL_DESKTOP_RUNTIME", 1440, 900, False),
    ("PERSONAL_MOBILE_RUNTIME", 390, 844, True),
]

PERSONAL_PLAN_TESTIDS = ("plan-free", "plan-starter", "plan-pro", "plan-advanced")

# Founder-private / trading-execution surface that must NEVER appear in Personal.
#
# Two-tier screening avoids false positives while still catching real leaks:
#  * TEXT terms are specific phrases that never occur in legitimate Personal
#    copy — safe to match anywhere in the rendered text.
#  * CONTROL terms are trading-action verbs that DO appear inside safe prose
#    (the disclaimer "本平台不下單" contains 下單; open-interest data "未平倉"
#    contains 平倉), so they are matched ONLY as the accessible name of an
#    actionable control (button / link) — the real execution-UI leak vector.
FORBIDDEN_TEXT_TERMS = (
    "bybit", "mainnet", "api secret", "founder private", "私有核心",
    "order entry", "buy order", "sell order", "long position",
    "short position", "position size",
)
FORBIDDEN_CONTROL_TERMS = (
    "下單", "做多", "做空", "槓桿", "倉位", "平倉", "掛單",
    "買入", "賣出", "leverage",
)


class SmokeFail(Exception):
    """A fail-closed browser-smoke deviation (message is always non-sensitive)."""


def assert_no_founder_or_execution_ui(page) -> None:
    """Fail closed if any Founder-Private / trading-execution surface leaks onto
    the currently-rendered Personal page. Run per key page (Home + Membership),
    not a full-site crawl.

    TEXT terms are matched in the page text; CONTROL terms are matched only as the
    accessible name of an actionable button/link, so safe disclaimer prose
    ("本平台不下單") and market data ("未平倉" open interest) never false-trip."""
    body_text = (page.locator("body").inner_text() or "").lower()
    for term in FORBIDDEN_TEXT_TERMS:
        if term.lower() in body_text:
            raise SmokeFail(f"forbidden_text_present:{term}")
    for term in FORBIDDEN_CONTROL_TERMS:
        if (page.get_by_role("button", name=term).count() > 0
                or page.get_by_role("link", name=term).count() > 0):
            raise SmokeFail(f"forbidden_control_present:{term}")


def _run_viewport(browser, origin: str, email: str, password: str,
                  width: int, height: int, is_mobile: bool) -> None:
    context = browser.new_context(
        viewport={"width": width, "height": height},
        has_touch=is_mobile,
        is_mobile=is_mobile,
    )
    page = context.new_page()
    try:
        # 1) /login (cache-bust to sidestep any stale SPA index).
        page.goto(f"{origin}/login?cb=smoke", wait_until="networkidle", timeout=45000)

        # 2) email + password inputs are visible (viewport-agnostic).
        email_input = page.locator('input[type="email"]:visible').first
        pw_input = page.locator('input[type="password"]:visible').first
        email_input.wait_for(state="visible", timeout=20000)
        pw_input.wait_for(state="visible", timeout=20000)

        # 3) log in through the REAL UI (values never logged).
        email_input.fill(email)
        pw_input.fill(password)
        page.locator('button[type="submit"]:visible').first.click()

        # 4) authenticated /app.
        page.wait_for_url("**/app", timeout=45000)

        # 5) reload /app and confirm the session persists.
        page.reload(wait_until="networkidle", timeout=45000)
        # 6) did NOT bounce back to /login.
        if "/login" in page.url:
            raise SmokeFail("session_did_not_persist_after_reload")
        if not page.url.rstrip("/").endswith("/app"):
            raise SmokeFail(f"unexpected_url_after_reload:{_path(page.url)}")
        # 6b) Founder/trading boundary must hold on the authenticated Home too.
        page.wait_for_load_state("networkidle", timeout=45000)
        assert_no_founder_or_execution_ui(page)

        # 7) authenticated membership / plans surface.
        page.goto(f"{origin}/app/membership", wait_until="networkidle", timeout=45000)
        if "/login" in page.url:
            raise SmokeFail("membership_redirected_to_login")

        # 8) Personal plans Free/Starter/Pro/Advanced present INSIDE the Personal
        #    plan grid.
        grid = page.locator('[data-testid="personal-plan-grid"]').first
        grid.wait_for(state="visible", timeout=20000)
        for testid in PERSONAL_PLAN_TESTIDS:
            grid.locator(f'[data-testid="{testid}"]').first.wait_for(state="visible", timeout=20000)
        # The Personal grid must contain EXACTLY those four Personal plans.
        plan_count = grid.locator('[data-testid^="plan-"]').count()
        if plan_count != len(PERSONAL_PLAN_TESTIDS):
            raise SmokeFail(f"personal_grid_plan_count_{plan_count}_not_{len(PERSONAL_PLAN_TESTIDS)}")
        if grid.locator('[data-testid="plan-enterprise"]').count() != 0:
            raise SmokeFail("enterprise_inside_personal_plan_grid")

        # 9) Enterprise contact surface exists OUTSIDE the Personal plan grid, and
        #    Enterprise is never the current Personal effective plan.
        if page.locator('[data-testid="enterprise-band"]').count() == 0:
            raise SmokeFail("enterprise_band_missing")
        if page.locator('[data-testid="personal-plan-grid"] [data-testid="enterprise-band"]').count() != 0:
            raise SmokeFail("enterprise_band_inside_personal_grid")
        if page.locator('[data-testid="personal-plan-grid"] [data-testid="enterprise-contact"]').count() != 0:
            raise SmokeFail("enterprise_contact_inside_personal_grid")
        page.locator('[data-testid="enterprise-contact"]').first.wait_for(state="visible", timeout=20000)
        current = page.locator('[data-testid="current-subscription"]').first
        current.wait_for(state="visible", timeout=20000)
        current_text = (current.inner_text() or "").lower()
        if "enterprise" in current_text or "企業" in current_text:
            raise SmokeFail("enterprise_presented_as_personal_effective_plan")

        # 10) no Founder Private / trading-execution UI on the membership surface.
        assert_no_founder_or_execution_ui(page)

        # 11) logout through the real UI (account page).
        page.goto(f"{origin}/app/account", wait_until="networkidle", timeout=45000)
        page.get_by_role("button", name="登出").first.click()
        page.wait_for_url("**/login", timeout=45000)

        # 12) revisit /app -> must redirect to /login (session revoked).
        page.goto(f"{origin}/app", wait_until="networkidle", timeout=45000)
        if "/login" not in page.url:
            # Fall back to confirming the login form is what renders.
            if page.locator('input[type="password"]:visible').count() == 0:
                raise SmokeFail("post_logout_app_not_redirected_to_login")
    except PWTimeout as exc:
        raise SmokeFail(f"timeout:{_first_line(str(exc))}")
    finally:
        context.close()


def _path(url: str) -> str:
    # URL path only (never query/creds) for a safe error label.
    try:
        from urllib.parse import urlparse

        return urlparse(url).path or "/"
    except Exception:  # noqa: BLE001
        return "?"


def _first_line(text: str) -> str:
    return (text.splitlines() or ["?"])[0][:80]


def main() -> int:
    origin = (os.getenv("NEXUS_PERSONAL_E2E_WEB_ORIGIN") or DEFAULT_WEB_ORIGIN).strip().rstrip("/")
    email = (os.getenv("NEXUS_STAGING_E2E_EMAIL") or "").strip()
    password = os.getenv("NEXUS_STAGING_E2E_PASSWORD") or ""
    if not email or not password:
        print("SMOKE_MISSING_INPUTS=yes")
        print("PERSONAL_BROWSER_SMOKE=no")
        return 1

    ok = True
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        try:
            for marker, width, height, is_mobile in VIEWPORTS:
                try:
                    _run_viewport(browser, origin, email, password, width, height, is_mobile)
                    print(f"{marker}=yes")
                except SmokeFail as exc:
                    print(f"{marker}=no reason={exc}")
                    ok = False
        finally:
            browser.close()

    print("PERSONAL_BROWSER_SMOKE=" + ("yes" if ok else "no"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

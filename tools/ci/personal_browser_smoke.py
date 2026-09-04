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
FORBIDDEN_UI_TERMS = (
    "下單", "做多", "做空", "槓桿", "倉位", "平倉", "掛單",
    "buy order", "sell order", "long position", "short position",
    "leverage", "order entry", "position size", "founder", "私有核心",
    "bybit", "mainnet", "api key", "api secret",
)


class SmokeFail(Exception):
    """A fail-closed browser-smoke deviation (message is always non-sensitive)."""


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

        # 7) authenticated membership / plans surface.
        page.goto(f"{origin}/app/membership", wait_until="networkidle", timeout=45000)
        if "/login" in page.url:
            raise SmokeFail("membership_redirected_to_login")

        # 8) Personal plans Free/Starter/Pro/Advanced present.
        for testid in PERSONAL_PLAN_TESTIDS:
            page.locator(f'[data-testid="{testid}"]').first.wait_for(state="visible", timeout=20000)

        # 9) Enterprise is separate (contact-sales, disabled) and NOT the current
        #    effective plan.
        page.locator('[data-testid="enterprise-contact"]').first.wait_for(state="visible", timeout=20000)
        current = page.locator('[data-testid="current-subscription"]').first
        current.wait_for(state="visible", timeout=20000)
        current_text = (current.inner_text() or "").lower()
        if "enterprise" in current_text or "企業" in current_text:
            raise SmokeFail("enterprise_presented_as_personal_effective_plan")

        # 10) no Founder Private / trading-execution UI anywhere on the surface.
        body_text = (page.locator("body").inner_text() or "").lower()
        for term in FORBIDDEN_UI_TERMS:
            if term.lower() in body_text:
                raise SmokeFail(f"forbidden_ui_term_present:{term}")

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

"""Review demo mode gate — labelled fixtures only; prod flavor blocked."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewDemoSession:
    active: bool
    banner: str
    source_lineage: str
    billing_ui: str


ALLOWED_FLAVORS = frozenset({"dev", "staging"})


def activate_review_demo(*, flavor: str, env_flag: bool, deep_link_token_ok: bool) -> ReviewDemoSession:
    if flavor not in ALLOWED_FLAVORS:
        return ReviewDemoSession(
            active=False,
            banner="",
            source_lineage="",
            billing_ui="Billing disabled",
        )
    if not (env_flag or deep_link_token_ok):
        return ReviewDemoSession(
            active=False,
            banner="",
            source_lineage="",
            billing_ui="Billing disabled",
        )
    return ReviewDemoSession(
        active=True,
        banner="DEMO PREVIEW · NOT LIVE DATA · NOT INVESTMENT ADVICE",
        source_lineage="demo_fixture",
        billing_ui="Billing disabled",
    )


def assert_no_live_mixing(session: ReviewDemoSession, widget_source: str) -> bool:
    if not session.active:
        return widget_source != "demo_fixture_unlabelled"
    return widget_source == "demo_fixture"

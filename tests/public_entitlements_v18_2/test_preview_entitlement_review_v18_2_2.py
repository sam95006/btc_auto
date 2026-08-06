"""V18.2.2 preview entitlement review isolation tests."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.nexus_public_entitlements_v18_2.hard_bans import run_entitlement_scans

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = ROOT / "frontend" / "src"


def test_preview_entitlement_override_not_in_prod_flag():
    text = (FRONTEND_SRC / "member" / "previewEntitlementReview.ts").read_text(encoding="utf-8")
    assert "previewEntitlementOverrideAvailableInProd(): boolean" in text
    assert "return false" in text


def test_preview_founder_capability_count_zero():
    text = (FRONTEND_SRC / "member" / "previewEntitlementReview.ts").read_text(encoding="utf-8")
    assert "previewFounderCapabilityCount" in text
    assert re.search(r"return 0", text)


def test_no_production_query_string_research_grant():
    """No URL query param that grants RESEARCH plan to all users."""
    bad = re.compile(
        r"searchParams\.get\([\"'](?:plan|membership|tier)[\"']\)",
        re.IGNORECASE,
    )
    hits: list[str] = []
    for path in list(FRONTEND_SRC.rglob("*.ts")) + list(FRONTEND_SRC.rglob("*.tsx")):
        if "previewMembershipReviewState" in path.name or "MembershipEntitlementReviewPage" in path.name:
            continue
        content = path.read_text(encoding="utf-8")
        if bad.search(content) and "RESEARCH" in content:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_review_route_registered():
    app_tsx = (FRONTEND_SRC / "app" / "ActualPanelV1821App.tsx").read_text(encoding="utf-8")
    assert 'path="/review"' in app_tsx
    assert "MembershipReviewEntryGuard" in app_tsx
    root_app = (FRONTEND_SRC / "App.tsx").read_text(encoding="utf-8")
    assert 'rest === "review"' in root_app or 'rest === "/review"' in root_app


def test_preview_review_guard_requires_build_flag():
    text = (FRONTEND_SRC / "member" / "previewEntitlementReview.ts").read_text(encoding="utf-8")
    assert "VITE_PREVIEW_ENTITLEMENT_REVIEW" in text
    assert "isPreviewEntitlementReviewBuildEnabled" in text


def test_founder_routes_not_on_review_page():
    review = (
        FRONTEND_SRC / "pages" / "actual_panel" / "MembershipEntitlementReviewPage.tsx"
    ).read_text(encoding="utf-8")
    assert "/founder/" not in review


def test_entitlement_scans_acceptance():
    scans = run_entitlement_scans(ROOT)
    assert scans["member_execution_control_count"] == 0
    assert scans["production_billing"] is False

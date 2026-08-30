"""Source-level assertions for the PERSONAL-1 frontend product surface.

There is no TS test runner in this repo, so these guard the member-safe
contract of the personal Intelligence page at the source level: it reflects the
backend's authoritative decisions, never imports the Founder tree, and never
carries trading-execution / routing / ARM / position-sizing controls.
"""
from __future__ import annotations

import re
from pathlib import Path

FE = Path("frontend") / "src" / "member_platform_v1"
PAGE = FE / "pages" / "IntelligencePages.tsx"
API = FE / "services" / "stagingApi.ts"
INDEX = FE / "index.tsx"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _imports_founder(src: str) -> bool:
    for line in src.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("import") or stripped.startswith("export")):
            continue
        if re.search(r'["\'][^"\']*founder[^"\']*["\']', stripped, re.IGNORECASE):
            return True
    return False


def test_intelligence_page_exists_and_is_routed() -> None:
    assert PAGE.exists()
    idx = _read(INDEX)
    assert "IntelligencePage" in idx
    assert 'path="intelligence"' in idx


def test_intelligence_page_uses_backend_personal_endpoints() -> None:
    src = _read(PAGE)
    for fn in (
        "getPersonalFeatures",
        "runPersonalAnalysis",
        "runPersonalReport",
        "getPersonalWatchlist",
        "getPersonalHistory",
        "getPersonalSignals",
        "getPersonalRisk",
        "newIdempotencyKey",
    ):
        assert fn in src, fn


def test_intelligence_page_renders_gating_states() -> None:
    src = _read(PAGE)
    # locked / upgrade / usage / unavailable states must all be present.
    assert "LockedCard" in src and "升級解鎖" in src
    assert "本期額度已用完" in src  # 429 metered exhaustion
    assert "已達方案上限" in src  # 409 capacity
    assert "未扣除額度" in src  # 503 unavailable, no charge
    assert "unavailable" in src.lower()


def test_intelligence_page_has_no_founder_import() -> None:
    assert _imports_founder(_read(PAGE)) is False


def test_intelligence_page_is_member_safe_no_trading_controls() -> None:
    src = _read(PAGE).lower()
    for banned in (
        "orderexecutor",
        "order-router",
        "routing-edit",
        "arm-control",
        "position_siz",
        "/trade",
        "/orders",
        "provider_customer_id",
        "provider_subscription_id",
    ):
        assert banned not in src, banned


def test_staging_api_exposes_personal_client() -> None:
    src = _read(API)
    for fn in (
        "export async function getPersonalFeatures",
        "export async function runPersonalAnalysis",
        "export async function runPersonalReport",
        "export async function getPersonalWatchlist",
        "export async function addPersonalWatchlist",
        "export async function removePersonalWatchlist",
        "export async function getPersonalHistory",
        "export async function getPersonalSignals",
        "export async function getPersonalRisk",
        "export function newIdempotencyKey",
    ):
        assert fn in src, fn
    # Metered POSTs must send an idempotency key so retries do not double-charge.
    assert "idempotency_key" in src
    # PERSONAL-2: real-data provenance + closed-beta health client.
    assert "export async function getPersonalClosedBetaHealth" in src
    assert "PersonalProvenance" in src and "PersonalHistory" in src


def test_intelligence_page_shows_real_provenance_and_freshness() -> None:
    src = _read(PAGE)
    # Truthful data states: freshness badge + provenance + real history points.
    assert "FreshnessBadge" in src and "ProvenanceLine" in src
    assert "provenance" in src
    assert "history-points" in src  # real record count, not a static claim
    # Risk is now a member-safe descriptor panel bound to real volatility.
    assert "risk-level" in src and "非交易建議" in src
    # Truthful states enumerated: loading / available / unavailable.
    assert '"loading"' in src and '"unavailable"' in src

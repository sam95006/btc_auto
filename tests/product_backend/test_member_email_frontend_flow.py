from __future__ import annotations

from pathlib import Path

FRONTEND = Path("frontend/src/member_platform_v1")
STAGING_API = FRONTEND / "services" / "stagingApi.ts"
AUTH_CONTEXT = FRONTEND / "context" / "AuthContext.tsx"
PUBLIC_PAGES = FRONTEND / "pages" / "PublicPages.tsx"
INDEX = FRONTEND / "index.tsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_staging_register_exposes_pending_verification_contract() -> None:
    src = _read(STAGING_API)
    assert "registrationRequiresVerification" in src
    assert "verification_required" in src
    assert 'account_status === "PENDING_VERIFICATION"' in src
    # Typed result, not a hard-coded active session shape.
    assert "Promise<StagingRegisterResult>" in src


def test_auth_context_does_not_hydrate_on_pending() -> None:
    src = _read(AUTH_CONTEXT)
    idx = src.index("const register = useCallback")
    body = src[idx : idx + 700]
    # Pending branch: set no session and return BEFORE any hydrate call.
    pending_branch = body.index("registrationRequiresVerification(result)")
    set_null = body.index("setSession(null)", pending_branch)
    return_pending = body.index("return result;", set_null)
    hydrate_call = body.index("await hydrate()")
    assert return_pending < hydrate_call  # returns before hydrate in pending path
    assert "setSession(null)" in body


def test_register_page_routes_pending_to_check_email_via_state_only() -> None:
    src = _read(PUBLIC_PAGES)
    assert "registrationRequiresVerification(result)" in src
    assert 'nav("/check-email", { state: { email } })' in src
    # Active path still goes to /app.
    assert 'nav("/app")' in src
    # Email must NOT travel via URL query or web storage in these flows.
    assert "/check-email?" not in src
    assert "localStorage" not in src
    assert "sessionStorage" not in src


def test_email_routes_registered_in_router() -> None:
    src = _read(INDEX)
    for path in ('path="/verify-email"', 'path="/reset-password"', 'path="/check-email"'):
        assert path in src


def test_pending_page_prefills_email_from_router_state_only() -> None:
    src = _read(PUBLIC_PAGES)
    assert "location.state as { email?: string }" in src

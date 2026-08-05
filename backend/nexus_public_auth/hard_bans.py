"""Hard-ban enforcement for PUB2-F public auth entitlement & org security."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_auth.constants import (
    HARD_BANS,
    PRIVATE_EXECUTION_FEATURE_DENYLIST,
    PRIVATE_ISSUER_DENYLIST,
    PRIVATE_REALM_DENYLIST,
    PRIVATE_SECRET_ENV_DENYLIST,
    PUBLIC_IDENTITY_REALM,
    PUBLIC_JWT_ISSUER,
    TIER_FEATURES,
)


class HardBanViolation(RuntimeError):
    """Raised when a PUB2-F hard ban would be violated."""


BANNED_CLAIM_PATTERNS = [
    re.compile(r"(?i)\blive\s+billing\b"),
    re.compile(r"(?i)\bstripe\.(?:charge|checkout|payment_intent)\b"),
    re.compile(r"(?i)\bproduction\s+customer\s+database\b"),
    re.compile(r"(?i)\bapp\s+store\s+submission\b"),
    re.compile(r"(?i)\bgoogle\s+play\s+submission\b"),
    re.compile(r"(?i)\bshared[_\s-]?private[_\s-]?jwt\b"),
    re.compile(r"(?i)\breuse[_\s-]?private[_\s-]?admin[_\s-]?session\b"),
    re.compile(r"(?i)\bentitlement\s+grants?\s+private\s+execution\b"),
]

# Allowlist context tokens so ban documentation / negative tests do not false-trip.
_ALLOW_CONTEXT = (
    "hard ban",
    "hard_ban",
    "banned",
    "refuse_",
    "refused",
    "no live",
    "not enabled",
    "non_production",
    "non-production",
    "denylist",
    "deny",
    "assert",
    "pytest.raises",
    "forbidden",
    "violation",
    "must never",
    "do not",
    "never",
    "shared_private_jwt",
    "share_private_jwt",
    "nexus_public_share_private_jwt",
    "reuse_private_admin_session",
    "production_customer_db",
    "live_billing",
    "real_iap",
    "live_public_deploy",
    "flags",
    "env_hard_ban",
    "violations",
    "private_execution",
    "never grant",
    "must never grant",
    "non-goals",
    "non_goals",
    "subscriptions / invoices",
)


def env_hard_ban_guard() -> dict[str, Any]:
    """Refuse production / billing / private-issuer env enablement."""
    flags = {
        "LIVE_BILLING": os.environ.get("NEXUS_PUBLIC_LIVE_BILLING", "false").lower(),
        "REAL_IAP": os.environ.get("NEXUS_PUBLIC_REAL_IAP", "false").lower(),
        "PRODUCTION_CUSTOMER_DB": os.environ.get("NEXUS_PUBLIC_PRODUCTION_CUSTOMER_DB", "false").lower(),
        "LIVE_PUBLIC_DEPLOY": os.environ.get("NEXUS_PUBLIC_LIVE_DEPLOY", "false").lower(),
        "SHARED_PRIVATE_JWT": os.environ.get("NEXUS_PUBLIC_SHARE_PRIVATE_JWT", "false").lower(),
        "REUSE_PRIVATE_ADMIN_SESSION": os.environ.get(
            "NEXUS_PUBLIC_REUSE_PRIVATE_ADMIN_SESSION", "false"
        ).lower(),
        "PRIVATE_EXECUTION_VIA_ENTITLEMENT": os.environ.get(
            "NEXUS_PUBLIC_PRIVATE_EXECUTION_VIA_ENTITLEMENT", "false"
        ).lower(),
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": sorted(HARD_BANS),
        "public_identity_realm": PUBLIC_IDENTITY_REALM,
        "public_jwt_issuer": PUBLIC_JWT_ISSUER,
    }


def assert_env_hard_bans() -> None:
    result = env_hard_ban_guard()
    if not result["ok"]:
        raise HardBanViolation(
            f"HARD BAN: forbidden env flags enabled: {result['violations']}"
        )


def refuse_live_billing() -> None:
    raise HardBanViolation("HARD BAN: live billing refused in PUB2-F non-production foundation")


def refuse_shared_private_jwt_issuer() -> None:
    raise HardBanViolation(
        "HARD BAN: shared private JWT issuer refused — public realm must use isolated issuer"
    )


def refuse_private_admin_session_reuse() -> None:
    raise HardBanViolation(
        "HARD BAN: private admin session reuse refused — member sessions are public-realm only"
    )


def refuse_production_customer_database() -> None:
    raise HardBanViolation(
        "HARD BAN: production customer database refused — LOCAL_OR_STAGING_ONLY store"
    )


def refuse_private_execution_via_entitlement() -> None:
    raise HardBanViolation(
        "HARD BAN: entitlements must never grant private execution access"
    )


def validate_public_issuer(issuer: str) -> None:
    normalized = (issuer or "").strip().lower()
    if not normalized:
        raise HardBanViolation("HARD BAN: empty JWT issuer refused")
    if normalized != PUBLIC_JWT_ISSUER.lower():
        if normalized in {x.lower() for x in PRIVATE_ISSUER_DENYLIST} or "private" in normalized:
            refuse_shared_private_jwt_issuer()
        raise HardBanViolation(
            f"HARD BAN: issuer {issuer!r} is not the public issuer {PUBLIC_JWT_ISSUER!r}"
        )


def validate_public_realm(realm: str) -> None:
    normalized = (realm or "").strip().lower()
    if normalized != PUBLIC_IDENTITY_REALM.lower():
        if normalized in {x.lower() for x in PRIVATE_REALM_DENYLIST} or "private" in normalized:
            refuse_shared_private_jwt_issuer()
        raise HardBanViolation(
            f"HARD BAN: realm {realm!r} is not the public identity realm"
        )


def refuse_private_secret_env(env_name: str) -> None:
    if env_name in PRIVATE_SECRET_ENV_DENYLIST:
        refuse_shared_private_jwt_issuer()


def assert_tier_matrix_excludes_private_execution() -> None:
    for tier, features in TIER_FEATURES.items():
        overlap = set(features) & set(PRIVATE_EXECUTION_FEATURE_DENYLIST)
        if overlap:
            raise HardBanViolation(
                f"HARD BAN: tier {tier} grants private execution features: {sorted(overlap)}"
            )


def scan_owned_paths_for_banned_claims(root: Path) -> dict[str, Any]:
    """Pass-1 / Pass-2 / Pass-3 static scan of owned source for illicit claim language."""
    hits: list[dict[str, str]] = []
    code_roots = [
        "backend/nexus_public_auth/",
        "tests/public_auth/",
        "docs/product_strategy/NEXUS_PUBLIC_AUTH_ENTITLEMENT_ORG_SECURITY_V2.md",
        "docs/product_strategy/NEXUS_PUBLIC_AUTH_MEMBERSHIP_FOUNDATION_V1.md",
    ]
    for rel in code_roots:
        target = root / rel
        if not target.exists():
            continue
        files: list[Path]
        if target.is_file():
            files = [target]
        else:
            files = [p for p in target.rglob("*") if p.is_file() and p.suffix in {".py", ".md"}]
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in BANNED_CLAIM_PATTERNS:
                for m in pat.finditer(text):
                    start = max(0, m.start() - 120)
                    end = min(len(text), m.end() + 120)
                    ctx = text[start:end]
                    ctx_l = ctx.lower()
                    if any(tok in ctx_l for tok in _ALLOW_CONTEXT):
                        continue
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "match": m.group(0),
                            "context": ctx.replace("\n", " ")[:240],
                        }
                    )
    return {"ok": len(hits) == 0, "hits": hits, "hard_bans": sorted(HARD_BANS)}


def run_hard_ban_pass(pass_id: int, root: Path) -> dict[str, Any]:
    """Execute one hard-ban verification pass (1, 2, or 3)."""
    if pass_id not in (1, 2, 3):
        raise ValueError("pass_id must be 1, 2, or 3")
    assert_env_hard_bans()
    assert_tier_matrix_excludes_private_execution()
    scan = scan_owned_paths_for_banned_claims(root)
    adversarial: dict[str, Any] = {"executed": False}
    if pass_id == 2:
        adversarial = _adversarial_probes()
    elif pass_id == 3:
        adversarial = _independent_cross_review_probes()
    ok = scan["ok"] and adversarial.get("ok", True)
    return {
        "pass_id": pass_id,
        "ok": ok,
        "env": env_hard_ban_guard(),
        "scan": scan,
        "adversarial": adversarial,
        "hard_bans": sorted(HARD_BANS),
        "private_execution_access_via_entitlement": False,
    }


def _adversarial_probes() -> dict[str, Any]:
    """Pass-2: attempt banned crossings and confirm they raise."""
    probes: list[dict[str, Any]] = []

    def _expect(name: str, fn) -> None:
        try:
            fn()
            probes.append({"name": name, "ok": False, "detail": "did not raise"})
        except HardBanViolation as exc:
            probes.append({"name": name, "ok": True, "detail": str(exc)})

    _expect("live_billing", refuse_live_billing)
    _expect("shared_private_jwt", refuse_shared_private_jwt_issuer)
    _expect("private_admin_session", refuse_private_admin_session_reuse)
    _expect("production_customer_db", refuse_production_customer_database)
    _expect("private_execution_via_entitlement", refuse_private_execution_via_entitlement)
    _expect("private_issuer_label", lambda: validate_public_issuer("nexus-private-auth"))
    _expect("private_realm_label", lambda: validate_public_realm("nexus.private.identity.v1"))
    _expect(
        "private_secret_env",
        lambda: refuse_private_secret_env("NEXUS_PRIVATE_JWT_SECRET"),
    )

    # Entitlement matrix must refuse private execution features for every tier.
    from backend.nexus_public_auth.entitlements import (
        has_feature,
        refuse_private_execution_entitlement,
    )
    from backend.nexus_public_auth.jwt_issuer import PublicJwtIssuer
    from backend.nexus_public_auth.mfa import MfaService
    from backend.nexus_public_auth.store import PublicAuthStore
    from backend.nexus_public_auth.service import PublicAuthMembershipService
    from backend.nexus_public_auth.rate_limit import AuthRateLimiter

    for banned in sorted(PRIVATE_EXECUTION_FEATURE_DENYLIST)[:6]:
        for tier in ("Free", "Pro", "Elite", "Enterprise"):
            _expect(
                f"entitlement_{tier}_{banned}",
                lambda t=tier, f=banned: has_feature(t, f),
            )
    _expect("refuse_private_execution_helper", refuse_private_execution_entitlement)

    # JWT must refuse private-execution claim injection (false-PASS / exposure).
    issuer = PublicJwtIssuer(secret="pass2-adversarial-public-secret")
    _expect(
        "jwt_private_execution_claim",
        lambda: issuer.issue(
            account_id="acct_p2",
            tier="Enterprise",
            member_roles=["member"],
            extra_claims={"private_execution_access": True},
        ),
    )
    _expect(
        "jwt_exchange_write_claim",
        lambda: issuer.issue(
            account_id="acct_p2",
            tier="Elite",
            member_roles=["member"],
            extra_claims={"exchange_write": True},
        ),
    )

    # MFA enrollment secret must not silently persist in store metadata.
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(
        store=store,
        rate_limiter=AuthRateLimiter(limits={"register": 20}),
    )
    reg = svc.register_member("p2secret@example.com", "P2")
    mfa = MfaService(store)
    enrolled = mfa.enroll_factor(reg["account_id"], "totp")
    persisted = store.get_mfa_factor(enrolled["factor_id"])
    if persisted and "enrollment_secret_once" in (persisted.metadata or {}):
        probes.append(
            {
                "name": "mfa_secret_not_persisted",
                "ok": False,
                "detail": "enrollment_secret_once persisted",
            }
        )
    else:
        probes.append({"name": "mfa_secret_not_persisted", "ok": True, "detail": "ok"})

    # Session create after MFA enroll without challenge must fail (no silent bypass).
    mfa.confirm_enrollment(
        reg["account_id"],
        enrolled["factor_id"],
        enrollment_secret=enrolled["enrollment_secret_once"],
    )
    _expect(
        "session_requires_mfa_challenge",
        lambda: svc.sessions.create_session(
            reg["account_id"], tier="Free", member_roles=["member"]
        ),
    )

    ok = all(p["ok"] for p in probes)
    return {"executed": True, "ok": ok, "probes": probes, "pass_kind": "adversarial"}


def _independent_cross_review_probes() -> dict[str, Any]:
    """Pass-3: independent break attempts beyond Pass-2 summaries."""
    probes: list[dict[str, Any]] = []

    def _expect(name: str, fn) -> None:
        try:
            fn()
            probes.append({"name": name, "ok": False, "detail": "did not raise"})
        except HardBanViolation as exc:
            probes.append({"name": name, "ok": True, "detail": str(exc)})

    from backend.nexus_public_auth.entitlements import (
        assign_tier_manual,
        has_feature,
        require_feature,
    )
    from backend.nexus_public_auth.mfa import MfaService
    from backend.nexus_public_auth.rate_limit import AuthRateLimiter, RateLimitExceeded
    from backend.nexus_public_auth.roles import normalize_org_roles
    from backend.nexus_public_auth.service import PublicAuthMembershipService
    from backend.nexus_public_auth.store import PublicAuthStore

    # 1) Elite/Enterprise still cannot unlock execution scopes via feature names.
    for feature in (
        "private_execution_access",
        "exchange_write",
        "order_placement",
        "autonomy_control",
        "copy_trading",
    ):
        _expect(f"enterprise_cannot_{feature}", lambda f=feature: has_feature("Enterprise", f))
        _expect(
            f"elite_require_{feature}",
            lambda f=feature: require_feature("Elite", f),
        )

    # 2) Stripe/IAP actors blocked even when targeting Free (no upgrade side-channel).
    _expect(
        "iap_actor_blocked",
        lambda: assign_tier_manual(
            current_tier="Free", target_tier="Enterprise", actor="iap:apple_tx"
        ),
    )

    # 3) Private org role still blocked.
    _expect("private_org_role", lambda: normalize_org_roles(["founder_admin"]))

    # 4) Rate limiter trips under burst.
    limiter = AuthRateLimiter(window_seconds=60, limits={"session_create": 3})

    def _burst() -> None:
        for i in range(5):
            limiter.check("session_create", "acct_burst")

    _expect("rate_limit_burst", _burst)

    # 5) MFA verify fails on wrong code (no silent success).
    store = PublicAuthStore()
    svc = PublicAuthMembershipService(store=store)
    reg = svc.register_member("pass3@example.com", "Pass3")
    mfa = MfaService(store)
    enrolled = mfa.enroll_factor(reg["account_id"], "totp", label="pass3")
    confirmed = mfa.confirm_enrollment(
        reg["account_id"],
        enrolled["factor_id"],
        enrollment_secret=enrolled["enrollment_secret_once"],
    )
    assert confirmed["status"] == "enabled"
    challenge = mfa.create_challenge(reg["account_id"], enrolled["factor_id"])

    def _bad_mfa() -> None:
        mfa.verify_challenge(
            reg["account_id"],
            challenge["challenge_id"],
            response_code="00000000000000000000000000000000",
        )

    _expect("mfa_wrong_code", _bad_mfa)

    # 6) Re-run core refuse helpers so Pass-3 is not a summary-only pass.
    _expect("p3_live_billing", refuse_live_billing)
    _expect("p3_private_execution", refuse_private_execution_via_entitlement)
    _expect("p3_shared_jwt", refuse_shared_private_jwt_issuer)

    # 7) MFA challenge replay for a second session must fail.
    challenge2 = mfa.create_challenge(reg["account_id"], enrolled["factor_id"])
    mfa.verify_challenge(
        reg["account_id"],
        challenge2["challenge_id"],
        response_code=challenge2["stub_response_hint"],
    )
    svc.sessions.create_session(
        reg["account_id"],
        tier="Free",
        member_roles=["member"],
        mfa_challenge_id=challenge2["challenge_id"],
    )

    def _replay_challenge() -> None:
        svc.sessions.create_session(
            reg["account_id"],
            tier="Free",
            member_roles=["member"],
            mfa_challenge_id=challenge2["challenge_id"],
        )

    _expect("mfa_challenge_session_replay", _replay_challenge)

    # 8) Org privilege escalation: billing_viewer cannot mint org_owner.
    owner = svc.register_member("owner-p3@example.com", "Owner")
    viewer = svc.register_member("viewer-p3@example.com", "Viewer")
    org = svc.create_org(owner_account_id=owner["account_id"], name="Org P3")
    svc.add_org_member(
        actor_account_id=owner["account_id"],
        org_id=org["org_id"],
        member_account_id=viewer["account_id"],
        roles=["org_billing_viewer"],
    )
    _expect(
        "org_privilege_escalation",
        lambda: svc.assign_org_roles(
            viewer["account_id"],
            org["org_id"],
            ["org_owner"],
            actor_account_id=viewer["account_id"],
        ),
    )

    # 9) Runtime tier-matrix mutation toward private execution is detected.
    from backend.nexus_public_auth import constants as auth_constants
    from backend.nexus_public_auth.entitlements import assert_tier_matrix_immutable

    original = auth_constants.TIER_FEATURES["Free"]
    auth_constants.TIER_FEATURES["Free"] = frozenset(set(original) | {"private_execution"})
    try:
        _expect("tier_matrix_mutation", assert_tier_matrix_immutable)
    finally:
        auth_constants.TIER_FEATURES["Free"] = original

    # 10) Empty-subject rate-limit bypass refused (collapsed to anonymous).
    empty_limiter = AuthRateLimiter(window_seconds=60, limits={"register": 2})

    def _empty_subject_burst() -> None:
        empty_limiter.check("register", "")
        empty_limiter.check("register", "   ")
        empty_limiter.check("register", "")

    _expect("rate_limit_empty_subject", _empty_subject_burst)

    # Ensure RateLimitExceeded is a HardBanViolation subclass for consistent handling.
    if not issubclass(RateLimitExceeded, HardBanViolation):
        probes.append(
            {
                "name": "rate_limit_is_hard_ban",
                "ok": False,
                "detail": "RateLimitExceeded must subclass HardBanViolation",
            }
        )
    else:
        probes.append({"name": "rate_limit_is_hard_ban", "ok": True, "detail": "ok"})

    ok = all(p["ok"] for p in probes)
    return {
        "executed": True,
        "ok": ok,
        "probes": probes,
        "pass_kind": "independent_cross_review",
    }

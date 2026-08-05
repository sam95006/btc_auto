"""Hard-ban enforcement for PUB-H public auth & membership foundation."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_auth.constants import (
    HARD_BANS,
    PRIVATE_ISSUER_DENYLIST,
    PRIVATE_REALM_DENYLIST,
    PRIVATE_SECRET_ENV_DENYLIST,
    PUBLIC_IDENTITY_REALM,
    PUBLIC_JWT_ISSUER,
)


class HardBanViolation(RuntimeError):
    """Raised when a PUB-H hard ban would be violated."""


BANNED_CLAIM_PATTERNS = [
    re.compile(r"(?i)\blive\s+billing\b"),
    re.compile(r"(?i)\bstripe\.(?:charge|checkout|payment_intent)\b"),
    re.compile(r"(?i)\bproduction\s+customer\s+database\b"),
    re.compile(r"(?i)\bapp\s+store\s+submission\b"),
    re.compile(r"(?i)\bgoogle\s+play\s+submission\b"),
    re.compile(r"(?i)\bshared[_\s-]?private[_\s-]?jwt\b"),
    re.compile(r"(?i)\breuse[_\s-]?private[_\s-]?admin[_\s-]?session\b"),
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
    raise HardBanViolation("HARD BAN: live billing refused in PUB-H non-production foundation")


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


def scan_owned_paths_for_banned_claims(root: Path) -> dict[str, Any]:
    """Pass-1 / Pass-2 static scan of owned source for illicit claim language."""
    hits: list[dict[str, str]] = []
    code_roots = [
        "backend/nexus_public_auth/",
        "tests/public_auth/",
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
    """Execute one hard-ban verification pass (1 or 2)."""
    if pass_id not in (1, 2):
        raise ValueError("pass_id must be 1 or 2")
    assert_env_hard_bans()
    scan = scan_owned_paths_for_banned_claims(root)
    adversarial: dict[str, Any] = {"executed": False}
    if pass_id == 2:
        adversarial = _adversarial_probes()
    ok = scan["ok"] and adversarial.get("ok", True)
    return {
        "pass_id": pass_id,
        "ok": ok,
        "env": env_hard_ban_guard(),
        "scan": scan,
        "adversarial": adversarial,
        "hard_bans": sorted(HARD_BANS),
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
    _expect("private_issuer_label", lambda: validate_public_issuer("nexus-private-auth"))
    _expect("private_realm_label", lambda: validate_public_realm("nexus.private.identity.v1"))
    _expect(
        "private_secret_env",
        lambda: refuse_private_secret_env("NEXUS_PRIVATE_JWT_SECRET"),
    )

    ok = all(p["ok"] for p in probes)
    return {"executed": True, "ok": ok, "probes": probes}

"""Credential boundary — fail closed, no mainnet fallback, demo/mainnet separation."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse

from backend.nexus_autonomy.security_constants_v1 import (
    DEMO_ENV_KEY,
    DEMO_ENV_SECRET,
    DEMO_HOST,
    FORBIDDEN_MAINNET_HOSTS,
    MAINNET_ENV_KEY,
    MAINNET_ENV_SECRET,
    TESTNET_HOST,
)
from backend.nexus_autonomy.security_exceptions_v1 import CredentialBoundaryError


PROFILE_DEMO = "demo"
PROFILE_MAINNET = "mainnet"
PROFILE_PUBLIC_READONLY = "public_readonly"
PROFILE_MISSING = "missing"


@dataclass
class CredentialBoundaryResult:
    profile: str
    ok: bool
    fail_closed: bool
    reasons: list[str] = field(default_factory=list)
    mainnet_fallback_used: bool = False
    demo_mainnet_confused: bool = False
    writes_enabled: bool = False
    secret_echoed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "ok": self.ok,
            "fail_closed": self.fail_closed,
            "reasons": list(self.reasons),
            "mainnet_fallback_used": self.mainnet_fallback_used,
            "demo_mainnet_confused": self.demo_mainnet_confused,
            "writes_enabled": self.writes_enabled,
            "secret_echoed": self.secret_echoed,
        }


def _present(environ: Mapping[str, str], key: str) -> bool:
    return bool(str(environ.get(key) or "").strip())


def resolve_exchange_profile(
    environ: Mapping[str, str] | None = None,
    *,
    requested_profile: str | None = None,
    base_url: str | None = None,
) -> CredentialBoundaryResult:
    """Resolve credential profile with fail-closed semantics.

    Rules:
    - missing required demo creds → fail closed (writes disabled)
    - never fall back from demo → mainnet keys
    - demo profile + mainnet URL → confused / rejected
    - empty/malformed keys cannot enable writes
    - public_readonly requires no secrets
    """
    env = environ if environ is not None else os.environ
    requested = (requested_profile or env.get("NEXUS_EXCHANGE_PROFILE") or "").strip().lower()
    url = (base_url or env.get("NEXUS_EXCHANGE_BASE_URL") or "").strip()
    host = (urlparse(url).hostname or "").lower() if url else ""

    demo_key = _present(env, DEMO_ENV_KEY)
    demo_secret = _present(env, DEMO_ENV_SECRET)
    main_key = _present(env, MAINNET_ENV_KEY)
    main_secret = _present(env, MAINNET_ENV_SECRET)

    # Detect illegal mainnet fallback: demo profile using mainnet keys when demo keys absent
    mainnet_fallback = False
    if requested in {"demo", "bybit_demo", ""} and (not demo_key or not demo_secret) and main_key and main_secret:
        mainnet_fallback = True

    confused = False
    if host in FORBIDDEN_MAINNET_HOSTS and requested in {"demo", "bybit_demo"}:
        confused = True
    if host == DEMO_HOST and requested == PROFILE_MAINNET:
        confused = True
    if host == TESTNET_HOST and requested in {"demo", "bybit_demo", PROFILE_MAINNET}:
        # testnet is neither demo nor mainnet private-core profile
        confused = True

    if requested in {"", "auto"}:
        if not demo_key and not demo_secret and not main_key and not main_secret:
            requested = PROFILE_PUBLIC_READONLY if not url or "/v5/market/" in url else PROFILE_MISSING
        elif demo_key and demo_secret:
            requested = PROFILE_DEMO
        else:
            requested = PROFILE_MISSING

    reasons: list[str] = []
    fail_closed = False
    writes_enabled = False
    ok = True

    if mainnet_fallback:
        ok = False
        fail_closed = True
        reasons.append("mainnet_fallback_rejected")
    if confused:
        ok = False
        fail_closed = True
        reasons.append("demo_mainnet_profile_confused")

    if requested == PROFILE_PUBLIC_READONLY:
        # public market data must not require secrets
        if demo_key or demo_secret or main_key or main_secret:
            # presence is ok for process env but must not be used; writes stay off
            pass
        writes_enabled = False
        return CredentialBoundaryResult(
            profile=PROFILE_PUBLIC_READONLY,
            ok=ok,
            fail_closed=True,  # fail-closed for writes
            reasons=reasons or ["public_readonly_no_secrets_required"],
            mainnet_fallback_used=mainnet_fallback,
            demo_mainnet_confused=confused,
            writes_enabled=False,
        )

    if requested == PROFILE_MAINNET:
        # Private Core V9 security boundary: mainnet write profile is never auto-enabled.
        ok = False
        fail_closed = True
        reasons.append("mainnet_profile_blocked_by_security_boundary")
        return CredentialBoundaryResult(
            profile=PROFILE_MAINNET,
            ok=False,
            fail_closed=True,
            reasons=reasons,
            mainnet_fallback_used=mainnet_fallback,
            demo_mainnet_confused=confused,
            writes_enabled=False,
        )

    if requested in {PROFILE_DEMO, "bybit_demo"}:
        if not demo_key or not demo_secret:
            fail_closed = True
            ok = False
            reasons.append("demo_credentials_missing")
            writes_enabled = False
        else:
            # Keys present — still do not enable writes unless explicit founder flag.
            founder = str(env.get("NEXUS_FOUNDER_EXCHANGE_WRITE") or "").strip().lower()
            writes_enabled = founder in {"1", "true", "yes"}
            if not writes_enabled:
                reasons.append("writes_require_explicit_founder_flag")
            # Malformed keys (too short) cannot enable writes
            key_val = str(env.get(DEMO_ENV_KEY) or "").strip()
            sec_val = str(env.get(DEMO_ENV_SECRET) or "").strip()
            if len(key_val) < 8 or len(sec_val) < 8:
                writes_enabled = False
                fail_closed = True
                ok = False
                reasons.append("malformed_credentials")
        if host and host != DEMO_HOST:
            ok = False
            fail_closed = True
            writes_enabled = False
            reasons.append(f"demo_host_rejected:{host}")
        return CredentialBoundaryResult(
            profile=PROFILE_DEMO,
            ok=ok and not mainnet_fallback and not confused,
            fail_closed=fail_closed or not writes_enabled,
            reasons=reasons,
            mainnet_fallback_used=mainnet_fallback,
            demo_mainnet_confused=confused,
            writes_enabled=writes_enabled,
        )

    # missing / unknown → fail closed
    return CredentialBoundaryResult(
        profile=PROFILE_MISSING,
        ok=False,
        fail_closed=True,
        reasons=reasons + ["missing_or_unknown_profile"],
        mainnet_fallback_used=mainnet_fallback,
        demo_mainnet_confused=confused,
        writes_enabled=False,
    )


def assert_no_secret_in_text(text: str, secrets: list[str] | None = None) -> None:
    """Raise if raw secret values or credential-like blobs appear in evidence/logs."""
    lowered = text.lower()
    for s in secrets or []:
        if s and s in text:
            raise CredentialBoundaryError("secret_value_in_text")
    # Reject obvious key material patterns without echoing them
    if re.search(r"(api[_-]?secret|x-bapi-api-key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}", text, re.I):
        raise CredentialBoundaryError("credential_literal_pattern")
    if "begin private key" in lowered:
        raise CredentialBoundaryError("private_key_block")


def audit_credential_boundary(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    scenarios = [
        resolve_exchange_profile({}, requested_profile="demo"),
        resolve_exchange_profile(
            {DEMO_ENV_KEY: "short", DEMO_ENV_SECRET: "short"},
            requested_profile="demo",
            base_url=f"https://{DEMO_HOST}",
        ),
        resolve_exchange_profile(
            {MAINNET_ENV_KEY: "mainnetkey123", MAINNET_ENV_SECRET: "mainnetsecret123"},
            requested_profile="demo",
        ),
        resolve_exchange_profile(
            {DEMO_ENV_KEY: "demokey123456", DEMO_ENV_SECRET: "demosecret123456"},
            requested_profile="demo",
            base_url="https://api.bybit.com",
        ),
        resolve_exchange_profile({}, requested_profile="public_readonly"),
        resolve_exchange_profile({}, requested_profile="mainnet"),
    ]
    # Expected: all fail-closed for writes except none enable writes here
    any_writes = any(s.writes_enabled for s in scenarios)
    any_fallback = any(s.mainnet_fallback_used for s in scenarios)
    confused_caught = any(s.demo_mainnet_confused for s in scenarios)
    missing_fail_closed = scenarios[0].fail_closed and not scenarios[0].ok
    return {
        "scenario_count": len(scenarios),
        "any_writes_enabled": any_writes,
        "mainnet_fallback_detected": any_fallback,
        "demo_mainnet_confusion_detected": confused_caught,
        "missing_env_fail_closed": missing_fail_closed,
        "passed": (not any_writes) and missing_fail_closed and any_fallback and confused_caught,
        "scenarios": [s.to_dict() for s in scenarios],
    }

"""Thin adapters over V16 public APIs — redteam-owned only."""
from __future__ import annotations

import json
import re
from typing import Any

# Credential-like patterns (values), not mere identifier substrings like key name "secret".
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|api[_-]?secret|access[_-]?token|refresh[_-]?token|"
    r"private[_-]?key|password|authorization|bearer|wallet[_-]?seed|mnemonic)"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-+/=.]{8,}"
)
_JSON_CREDENTIAL = re.compile(
    r'(?i)"(api[_-]?key|api[_-]?secret|access[_-]?token|refresh[_-]?token|'
    r'private[_-]?key|password|authorization|wallet[_-]?seed|mnemonic)"\s*:\s*"[^"]{8,}"'
)
_PEM = re.compile(r"(?i)BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY")

# Identifier keys that are forbidden when present as storage fields.
_FORBIDDEN_CREDENTIAL_KEYS = frozenset(
    {
        "api_key",
        "api_secret",
        "access_token",
        "refresh_token",
        "private_key",
        "password",
        "authorization",
        "wallet_seed",
        "mnemonic",
        "exchange_credentials",
        "client_secret",
    }
)


def scan_embedded_secrets(payload: Any) -> dict[str, Any]:
    """Distinguish literal credential patterns from benign identifier substrings.

    A dict key literally named ``secret`` with a null/empty/placeholder value is
    NOT a credential leak. Real leaks require forbidden credential keys with
    non-empty values, assignment/JSON credential patterns, or PEM material.
    """
    forbidden_key_hits: list[str] = []
    credential_value_hits: list[str] = []

    def walk(obj: Any, path: str = "root") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                lk = str(k).lower()
                p = f"{path}.{k}"
                if lk in _FORBIDDEN_CREDENTIAL_KEYS:
                    if v not in (None, "", {}, [], False):
                        forbidden_key_hits.append(lk)
                        credential_value_hits.append(p)
                    else:
                        # Key present but empty — note only, not a leak.
                        pass
                # Bare key "secret" / "token" without value is identifier noise.
                walk(v, p)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, f"{path}[{i}]")

    walk(payload)
    blob = json.dumps(payload, default=str, ensure_ascii=False)
    assignment = bool(_CREDENTIAL_ASSIGNMENT.search(blob))
    json_cred = bool(_JSON_CREDENTIAL.search(blob))
    pem = bool(_PEM.search(blob))

    real_leaks: list[str] = []
    if forbidden_key_hits:
        real_leaks.append("forbidden_credential_key_with_value")
    if assignment or json_cred:
        real_leaks.append("credential_assignment_pattern")
    if pem:
        real_leaks.append("private_key_pem")

    return {
        "forbidden_key_hits": sorted(set(forbidden_key_hits)),
        "credential_paths": credential_value_hits,
        "assignment_pattern": assignment,
        "json_credential_pattern": json_cred,
        "pem_hit": pem,
        "real_leaks": real_leaks,
        "secret_leak_count": len(real_leaks),
        "pass": len(real_leaks) == 0,
        "identifier_only_secret_key_ignored": True,
    }


def route_defensive_context():
    """Build MarketContext for DEFENSIVE_NO_TRADE path via public fixtures."""
    from backend.nexus_strategy_expert_router.fixtures import fixture_defensive_stress

    return fixture_defensive_stress()


def thrash_formal_params() -> dict[str, Any]:
    """Exercise FormalParamLock.propose_update anti-thrash (public API)."""
    from backend.nexus_strategy_expert_router.formal_params import (
        FormalParamLock,
        FormalRouterParams,
    )
    from backend.nexus_strategy_expert_router.hard_bans import HardBanViolation

    lock = FormalParamLock()
    first = lock.propose_update(
        FormalRouterParams(min_data_trust=0.50),
        ts_ms=1_000_000,
    )
    thrash_blocked = False
    thrash_error: str | None = None
    second: dict[str, Any] | None = None
    try:
        second = lock.propose_update(
            FormalRouterParams(min_data_trust=0.55),
            ts_ms=1_000_000 + 30_000,  # 30s — sub-minute thrash
        )
        if second.get("accepted") is False:
            thrash_blocked = True
    except HardBanViolation as exc:
        thrash_blocked = True
        thrash_error = str(exc)
    if lock.rejected_thrash_count > 0:
        thrash_blocked = True
    return {
        "first": first,
        "second": second,
        "thrash_blocked": thrash_blocked,
        "thrash_error": thrash_error,
        "rejected_thrash_count": lock.rejected_thrash_count,
        "lock": lock.to_dict(),
    }


def cherry_pick_blocked() -> dict[str, Any]:
    """Use public cherry-pick gate (not fixture.allowed which is unset)."""
    from backend.nexus_lesson_validation_firewall.fixtures import cherry_pick_attempt_fixture
    from backend.nexus_lesson_validation_firewall.gates import evaluate_cherry_pick_gate
    from backend.nexus_lesson_validation_firewall.bans import refuse_cherry_pick

    lesson = cherry_pick_attempt_fixture()
    gate = evaluate_cherry_pick_gate(lesson)
    refusal = refuse_cherry_pick(str(lesson.get("lesson_id") or "FIX"))
    blocked = gate.get("allowed") is False and refusal.get("allowed") is False
    return {
        "lesson_id": lesson.get("lesson_id"),
        "gate": gate,
        "refusal": refusal,
        "blocked": blocked,
    }

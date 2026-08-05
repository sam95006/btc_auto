"""Secret rejection for Decision Memory Graph payloads."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.nexus_decision_memory_graph.constants import FORBIDDEN_SECRET_KEYS
from backend.nexus_decision_memory_graph.hard_bans import HardBanViolation


def _walk_keys(obj: Any, found: set[str] | None = None) -> set[str]:
    found = found if found is not None else set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower()
            found.add(lk)
            _walk_keys(v, found)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _walk_keys(item, found)
    return found


def scan_for_secrets(payload: Any) -> dict[str, Any]:
    keys = _walk_keys(payload)
    hits = sorted(k for k in keys if k in FORBIDDEN_SECRET_KEYS)
    blob = json.dumps(payload, default=str, ensure_ascii=False)
    assignment_hit = bool(
        re.search(
            r"(api[_-]?key|api[_-]?secret|token|password|private_key)\s*[:=]\s*['\"][^'\"]{8,}",
            blob,
            re.I,
        )
    )
    json_hit = bool(
        re.search(
            r'"(api[_-]?key|api[_-]?secret|token|password|private_key|authorization)"\s*:\s*"[^"]{8,}"',
            blob,
            re.I,
        )
    )
    pem_hit = "begin private key" in blob.lower()
    real_leaks: list[str] = []
    if hits:
        real_leaks.append("forbidden_secret_key")
    if assignment_hit or json_hit:
        real_leaks.append("credential_assignment")
    if pem_hit:
        real_leaks.append("private_key_pem")
    return {
        "forbidden_key_hits": hits,
        "real_leaks": real_leaks,
        "secret_leak_count": len(real_leaks),
        "pass": len(real_leaks) == 0,
        "values_echoed": False,
    }


def assert_no_secrets(payload: Any) -> None:
    result = scan_for_secrets(payload)
    if not result["pass"]:
        raise HardBanViolation(
            f"no_secret_storage:{','.join(result['real_leaks'])}:{','.join(result['forbidden_key_hits'][:5])}"
        )

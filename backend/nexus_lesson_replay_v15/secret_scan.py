"""Secret / forbidden-key scan for V15-I Lesson Replay Lab artifacts."""
from __future__ import annotations

import json
import re
from typing import Any

from backend.nexus_lesson_replay_v15.constants import FORBIDDEN_LOG_KEYS, SCHEMA_SECRET_SCAN


def scan_payload(payload: Any) -> dict[str, Any]:
    """Scan for forbidden keys and credential-looking assignments. Never echo secrets."""
    blob = json.dumps(payload, default=str, ensure_ascii=False)
    lowered = blob.lower()
    key_hits: list[str] = []
    for key in FORBIDDEN_LOG_KEYS:
        if re.search(rf'"{re.escape(key)}"\s*:', lowered):
            key_hits.append(key)

    assignment_hit = bool(
        re.search(r"(api[_-]?key|api[_-]?secret|token)\s*[:=]\s*['\"][^'\"]{16,}", blob, re.I)
    )
    json_assignment_hit = bool(
        re.search(
            r'"(api[_-]?key|api[_-]?secret|token|password|private_key)"\s*:\s*"[^"]{16,}"',
            blob,
            re.I,
        )
    )
    pem_hit = "begin private key" in lowered
    real_leaks: list[str] = []
    if assignment_hit or json_assignment_hit:
        real_leaks.append("credential_assignment")
    if pem_hit:
        real_leaks.append("private_key_pem")
    if key_hits:
        real_leaks.append("forbidden_log_key_present")

    return {
        "schema": SCHEMA_SECRET_SCAN,
        "forbidden_key_hits": key_hits,
        "real_leak_count": len(real_leaks),
        "real_leaks": real_leaks,
        "secret_leak_count": len(real_leaks),
        "pass": len(real_leaks) == 0,
        "values_echoed": False,
    }

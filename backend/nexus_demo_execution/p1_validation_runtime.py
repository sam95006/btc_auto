"""Shared P1 validation runtime helpers for qualification, recovery, and migration."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DISARMED_FLAGS = {
    "MAINNET": "false",
    "REAL_MONEY": "false",
    "DEMO_AUTONOMOUS_ENABLED": "false",
    "AUTONOMOUS_SEND": "false",
    "EXCHANGE_WRITE": "false",
}

EVIDENCE_KINDS = frozenset(
    {
        "p1_qualification",
        "p1_run2_recovery",
        "p1_run8_accounting_recovery",
        "p1_run8_bootstrap_failure",
    }
)


def apply_disarmed_flags(environ: dict[str, str] | None = None) -> dict[str, str]:
    target = environ if environ is not None else os.environ
    for key, value in DISARMED_FLAGS.items():
        target[key] = value
    return dict(DISARMED_FLAGS)


def unique_remote_path(*, kind: str, run_id: str, run_attempt: str) -> str:
    if kind not in EVIDENCE_KINDS:
        raise ValueError("evidence_kind_invalid")
    if not run_id or not run_attempt or not run_id.isdigit() or not run_attempt.isdigit():
        raise ValueError("evidence_run_identity_invalid")
    return f"/tmp/nexus_demo_validation/{kind}_{run_id}_{run_attempt}.json"


def write_json_file(path: Path, payload: dict[str, Any]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, indent=2, default=str)
        if not text.strip().startswith("{"):
            return False
        path.write_text(text, encoding="utf-8")
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def load_valid_json_object(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file() or path.stat().st_size <= 0:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def code_identity_matches(*, expected_sha: str, loaded_sha: str, require_both: bool = False) -> bool:
    expected = (expected_sha or "").strip()
    loaded = (loaded_sha or "").strip()
    if not expected or not loaded:
        return not require_both
    return loaded.startswith(expected[:7]) or expected.startswith(loaded[:7])


def exception_type_name(exc: BaseException) -> str:
    return type(exc).__name__

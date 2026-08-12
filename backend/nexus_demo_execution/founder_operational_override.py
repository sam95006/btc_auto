"""Explicit Founder override gate for aborting incomplete 24H operational observation.

Honest admission path only — never a silent boolean skip.
Cannot enable mainnet, weaken risk controls, lower Net R:R, or bypass 6H→12H machine gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.nexus_demo_execution.v2_policy import MIN_NET_REWARD_RISK_RATIO as V2_RR
from backend.nexus_demo_execution.v3_policy import MIN_NET_REWARD_RISK_RATIO as V3_RR
from backend.nexus_demo_execution.v3_start_gate import evaluate_12h_machine_gate

ABORT_STATUS = "ABORTED_BY_FOUNDER_FOR_DEMO_VALIDATION"
ABORT_REASON = "FOUNDER_PRIORITIZED_BOUNDED_DEMO_EXECUTION_VALIDATION"
REQUIRED_OVERRIDE_FLAGS = (
    "FOUNDER_OVERRIDE_ABORT_OPERATIONAL_24H",
    "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2",
)
OPTIONAL_12H_FLAG = "FOUNDER_APPROVE_DEMO_AUTONOMOUS_12H_V3"

FORBIDDEN_OVERRIDE_SCOPES = frozenset(
    {
        "mainnet",
        "real_money",
        "disable_risk_controls",
        "lower_net_rr",
        "bypass_6h_to_12h_machine_gate",
        "auto_start_24h",
    }
)

_TRUE = frozenset({"1", "true", "yes", "on"})


def _env_true(name: str, env: dict[str, str] | None = None) -> bool:
    src = env if env is not None else os.environ
    return str(src.get(name, "")).strip().lower() in _TRUE


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_observation_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def parse_observation_markers(text: str) -> dict[str, Any]:
    """Extract honesty markers from MD/JSON observation reports."""
    lower = text.lower()
    status = None
    m = re.search(
        r"observation_status\s*[=:]\s*`?([A-Z0-9_]+)`?",
        text,
        flags=re.IGNORECASE,
    )
    if m:
        status = m.group(1).upper()
    if status is None and ABORT_STATUS in text:
        status = ABORT_STATUS
    if '"observation_status"' in lower:
        try:
            data = json.loads(text)
            status = str(data.get("observation_status") or status or "")
        except json.JSONDecodeError:
            pass

    pass_true = (
        '"operational_observation_pass": true' in lower
        or '"operational_observation_pass":true' in lower
        or "operational_observation_pass=true" in lower
        or "operational_observation_pass: true" in lower
        or re.search(r"operational_observation_pass\s*\|\s*`?true`?", text, flags=re.IGNORECASE) is not None
    )
    # Mentioning the PASS token as a forbidden claim must NOT count as pass.
    forbidden_pass_claim = bool(
        re.search(
            r"(not|forbidden|must_not|不得).{0,40}NEXUS_SINGLE_SERVICE_OPERATIONAL_24H_PASS",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    has_pass_marker = (
        "NEXUS_SINGLE_SERVICE_OPERATIONAL_24H_PASS" in text and not forbidden_pass_claim
    )
    pass_true = pass_true or (has_pass_marker and not forbidden_pass_claim)
    pass_false = (
        "operational_observation_pass=false" in lower
        or "operational_observation_pass: false" in lower
        or '"operational_observation_pass": false' in lower
        or '"operational_observation_pass":false' in lower
        or re.search(r"operational_observation_pass\s*\|\s*`?false`?", text, flags=re.IGNORECASE) is not None
    )
    completed = (
        "observation_completed_full_24h=true" in lower
        or '"observation_completed_full_24h": true' in lower
        or '"observation_completed_full_24h":true' in lower
    )
    return {
        "observation_status": status,
        "operational_observation_pass": True if pass_true and not pass_false else (False if pass_false else None),
        "observation_completed_full_24h": completed,
        "has_abort_status": status == ABORT_STATUS or ABORT_STATUS in text,
        "has_pass_marker": "NEXUS_SINGLE_SERVICE_OPERATIONAL_24H_PASS" in text,
    }


@dataclass(frozen=True)
class OverrideRecord:
    founder_override_id: str
    founder_override_reason: str
    approved_at: str
    approved_scope: tuple[str, ...]
    source_observation_report: str
    source_observation_checksum: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "founder_override_id": self.founder_override_id,
            "founder_override_reason": self.founder_override_reason,
            "approved_at": self.approved_at,
            "approved_scope": list(self.approved_scope),
            "source_observation_report": self.source_observation_report,
            "source_observation_checksum": self.source_observation_checksum,
        }


def build_override_record(
    *,
    founder_override_id: str,
    approved_at: str,
    source_observation_report: str,
    source_text: str | None = None,
    founder_override_reason: str = ABORT_REASON,
    approved_scope: tuple[str, ...] = (
        "abort_incomplete_operational_24h",
        "demo_autonomous_6h_v2",
        "demo_autonomous_12h_v3_via_machine_gate",
    ),
) -> OverrideRecord:
    text = source_text if source_text is not None else load_observation_text(source_observation_report)
    return OverrideRecord(
        founder_override_id=founder_override_id.strip(),
        founder_override_reason=founder_override_reason,
        approved_at=approved_at.strip(),
        approved_scope=approved_scope,
        source_observation_report=str(source_observation_report),
        source_observation_checksum=_sha256_text(text),
    )


def evaluate_operational_observation_gate(
    *,
    observation_text: str,
    env: dict[str, str] | None = None,
    override: OverrideRecord | dict[str, Any] | None = None,
    proposed_scope: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Allow 6H start only if observation PASS **or** exact abort+Founder override.

    Missing / incomplete observation without override → BLOCK.
    Aborted observation without exact Founder flags → BLOCK.
    """
    # Important: empty dict must NOT fall through to os.environ (falsy `{} or environ` bug).
    env_map = {k: str(v) for k, v in (env if env is not None else os.environ).items()}
    markers = parse_observation_markers(observation_text)
    problems: list[str] = []

    # Hard safety: override cannot flip these.
    if _env_true("MAINNET", env_map):
        problems.append("mainnet_forbidden")
    if _env_true("REAL_MONEY", env_map):
        problems.append("real_money_forbidden")

    scope = list(proposed_scope or [])
    if override is not None:
        od = override.to_dict() if isinstance(override, OverrideRecord) else dict(override)
        scope.extend(od.get("approved_scope") or [])
    bad_scopes = sorted({s for s in scope if str(s).strip().lower() in FORBIDDEN_OVERRIDE_SCOPES})
    if bad_scopes:
        problems.append("forbidden_override_scope:" + ",".join(bad_scopes))

    # Net R:R floor cannot be lowered via override env.
    for key in ("MIN_NET_REWARD_RISK_RATIO", "NEXUS_MIN_NET_REWARD_RISK_RATIO"):
        if key in env_map and str(env_map[key]).strip():
            try:
                if float(env_map[key]) < 1.2:
                    problems.append("net_rr_lowered_forbidden")
            except ValueError:
                problems.append("net_rr_env_invalid")

    if V2_RR < 1.2 or V3_RR < 1.2:
        problems.append("policy_net_rr_below_floor")

    allow = False
    path = "blocked"

    if markers["operational_observation_pass"] is True and markers.get("has_pass_marker"):
        if markers["has_abort_status"]:
            problems.append("pass_and_abort_conflict")
        else:
            allow = True
            path = "observation_pass"
    elif markers["has_abort_status"] and markers["operational_observation_pass"] is False:
        missing_flags = [f for f in REQUIRED_OVERRIDE_FLAGS if not _env_true(f, env_map)]
        # Exact true required — empty/default does not count.
        if missing_flags:
            problems.append("aborted_without_founder_flags:" + ",".join(missing_flags))
        if override is None:
            problems.append("override_record_missing")
        else:
            od = override.to_dict() if isinstance(override, OverrideRecord) else dict(override)
            for req in (
                "founder_override_id",
                "founder_override_reason",
                "approved_at",
                "approved_scope",
                "source_observation_report",
                "source_observation_checksum",
            ):
                if not od.get(req):
                    problems.append(f"override_field_missing:{req}")
            expected = _sha256_text(observation_text)
            if od.get("source_observation_checksum") and od["source_observation_checksum"] != expected:
                problems.append("override_checksum_mismatch")
            if od.get("founder_override_reason") and od["founder_override_reason"] != ABORT_REASON:
                problems.append("override_reason_mismatch")
        if not problems:
            allow = True
            path = "founder_abort_override"
    else:
        # Incomplete / unknown without PASS marker.
        problems.append("observation_incomplete_or_unmarked")
        if markers["operational_observation_pass"] is False and not markers["has_abort_status"]:
            problems.append("observation_fail_without_abort_status")

    return {
        "allow_6h_v2_start": allow and not problems,
        "path": path if (allow and not problems) else "blocked",
        "problems": problems,
        "markers": markers,
        "required_override_flags": list(REQUIRED_OVERRIDE_FLAGS),
        "optional_12h_flag": OPTIONAL_12H_FLAG,
        "12h_founder_flag_present": _env_true(OPTIONAL_12H_FLAG, env_map),
        "mainnet": False,
        "real_money": False,
        "net_rr_floor": 1.2,
        "can_bypass_6h_to_12h_machine_gate": False,
        "can_disable_risk_controls": False,
        "can_enable_mainnet": False,
    }


def assert_override_cannot_bypass_12h_machine_gate(
    report_6h: dict[str, Any],
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Even with Founder 6H/12H approval flags, 12H still requires machine gate."""
    env_map = {k: str(v) for k, v in (env if env is not None else os.environ).items()}
    gate = evaluate_12h_machine_gate(report_6h)
    founder_wants_12h = _env_true(OPTIONAL_12H_FLAG, env_map) and _env_true(
        "FOUNDER_APPROVE_DEMO_AUTONOMOUS_6H_V2", env_map
    )
    # Explicitly refuse silent bypass.
    if _env_true("BYPASS_6H_TO_12H_MACHINE_GATE", env_map):
        return {
            "allow_12h": False,
            "problems": ["bypass_flag_forbidden"],
            "machine_gate": gate,
            "founder_wants_12h": founder_wants_12h,
        }
    allow = bool(gate.get("machine_gate_pass")) and founder_wants_12h
    problems = list(gate.get("problems") or [])
    if founder_wants_12h and not gate.get("machine_gate_pass"):
        problems.append("founder_flag_cannot_bypass_machine_gate")
    return {
        "allow_12h": allow,
        "problems": problems,
        "machine_gate": gate,
        "founder_wants_12h": founder_wants_12h,
        "auto_start_24h": False,
    }

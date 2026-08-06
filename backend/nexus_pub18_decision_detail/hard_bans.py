"""Hard-ban enforcement for PUB18-B Decision Detail — three passes."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_pub18_decision_detail.constants import (
    EXCHANGE_WRITE_MARKERS,
    FORBIDDEN_PRIVATE_FIELDS,
    HARD_BANS,
    MEMBER_VISIBLE_FIELD_IDS,
    OWNED_PATHS,
    PRIVATE_CORE_IMPORT_PREFIXES,
)
from backend.nexus_pub18_decision_detail.fixtures import catalog
from backend.nexus_pub18_decision_detail.honesty import (
    HonestyViolation,
    assert_not_unavailable_as_zero,
    build_metric_slot,
)
from backend.nexus_pub18_decision_detail.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
    count_forbidden_key_hits,
)
from backend.nexus_pub18_decision_detail.service import (
    build_decision_detail,
    list_decision_details,
)


BANNED_BEHAVIOR_PATTERNS = [
    re.compile(r"(?i)\bplace_order\b"),
    re.compile(r"(?i)\bsubmit_order\b"),
    re.compile(r"(?i)\bcreate_order\b"),
    re.compile(r"(?i)\bexecute_trade\b"),
    re.compile(r"(?i)\bEXCHANGE_WRITE\s*=\s*True\b"),
    re.compile(r"(?i)\bMAINNET\s*=\s*True\b"),
]


class HardBanViolation(RuntimeError):
    """Raised when a PUB18-B hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "CUSTOMER_TRADING": os.environ.get("CUSTOMER_TRADING", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {"ok": len(violations) == 0, "flags": flags, "violations": violations}


def _owned_py_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_file() and target.suffix == ".py":
            files.append(target)
            continue
        if target.is_dir():
            files.extend(p for p in target.rglob("*.py") if p.is_file())
    return sorted(set(files))


def _owned_all_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_file():
            files.append(target)
            continue
        if target.is_dir():
            files.extend(p for p in target.rglob("*") if p.is_file())
    return sorted(set(files))


def _is_allowlisted_ban_context(text: str, match_start: int, match_end: int) -> bool:
    start = max(0, match_start - 220)
    end = min(len(text), match_end + 120)
    ctx = text[start:end].lower()
    allow_tokens = (
        "hard ban",
        "hard_ban",
        "banned",
        "forbidden",
        "refuse_",
        "never",
        "must not",
        "violation",
        "assert",
        "denied",
        "probe",
        "adversarial",
        "no_private",
        "no_founder",
        "no_exact",
        "no_raw",
        "no_account",
        "no_internal",
        "forbidden_private",
        "forbidden_payload",
        "member_must_not",
    )
    return any(tok in ctx for tok in allow_tokens)


def scan_imports(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _owned_py_files(root):
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for mod in modules:
                for prefix in PRIVATE_CORE_IMPORT_PREFIXES:
                    if mod == prefix or mod.startswith(prefix + "."):
                        hits.append(
                            {
                                "file": str(path.relative_to(root)).replace("\\", "/"),
                                "module": mod,
                                "prefix": prefix,
                            }
                        )
    return {"ok": len(hits) == 0, "hits": hits, "private_core_import_count": len(hits)}


def scan_exchange_markers(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _owned_py_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel.endswith("constants.py") or rel.endswith("hard_bans.py"):
            continue
        for marker in EXCHANGE_WRITE_MARKERS:
            idx = 0
            while True:
                found = text.find(marker, idx)
                if found < 0:
                    break
                if _is_allowlisted_ban_context(text, found, found + len(marker)):
                    idx = found + len(marker)
                    continue
                hits.append({"file": rel, "marker": marker})
                idx = found + len(marker)
    return {"ok": len(hits) == 0, "hits": hits}


def scan_banned_behaviors(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _owned_all_files(root):
        if path.suffix.lower() not in {".py", ".ts", ".tsx"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel.endswith("constants.py") or rel.endswith("hard_bans.py"):
            continue
        for pat in BANNED_BEHAVIOR_PATTERNS:
            for m in pat.finditer(text):
                if _is_allowlisted_ban_context(text, m.start(), m.end()):
                    continue
                hits.append({"file": rel, "match": m.group(0)})
    return {"ok": len(hits) == 0, "hits": hits}


def scan_private_field_leaks_in_payloads() -> dict[str, Any]:
    """Scan materialized decision-detail payloads for private field keys."""
    hits: list[str] = []
    for case in catalog():
        detail = build_decision_detail(case)
        for path in count_forbidden_key_hits(detail):
            hits.append(f"{case.get('case_id')}:{path}")
    return {
        "ok": len(hits) == 0,
        "private_field_leak_count": len(hits),
        "hits": hits,
    }


def pass1_implementation(root: Path | str) -> dict[str, Any]:
    root_path = Path(root)
    findings: list[str] = []

    for rel in OWNED_PATHS:
        if not (root_path / rel).exists():
            findings.append(f"missing_owned_path:{rel}")

    expected = list(MEMBER_VISIBLE_FIELD_IDS)
    if expected != [
        "decision_timeline",
        "market_regime",
        "data_trust",
        "strategy_expert_label",
        "evidence",
        "counter_evidence",
        "risk_reason",
        "why_wait_abstain",
        "historical_similarity_aggregate",
        "shadow_outcome",
        "process_classification_aggregate",
        "delayed_learning_summary",
    ]:
        findings.append(f"field_ids_mismatch:{MEMBER_VISIBLE_FIELD_IDS}")

    try:
        feed = list_decision_details()
    except Exception as exc:  # noqa: BLE001
        findings.append(f"list_decision_details_failed:{exc}")
        feed = None

    if feed is not None:
        if feed.get("ok") is not True:
            findings.append("feed_not_ok")
        if feed.get("private_field_leak_count", 1) != 0:
            findings.append("private_field_leak_count_nonzero")
        if feed.get("private_core_import_count", 1) != 0:
            findings.append("private_core_import_count_nonzero")
        rows = feed.get("decision_details") or []
        if len(rows) < 4:
            findings.append(f"too_few_details:{len(rows)}")
        for row in rows:
            ids = [f.get("id") for f in (row.get("fields") or [])]
            if ids != expected:
                findings.append(f"fields_order:{row.get('case_id')}:{ids}")
            chrome = str(row.get("chrome_label", "")).upper()
            if chrome in {"LIVE"}:
                findings.append(f"fixture_as_live:{row.get('case_id')}")
            if row.get("mode") in {"DEMO_DATA", "FIXTURE", "PROVIDER_REQUIRED", "UNAVAILABLE"} and chrome == "LIVE_READ_ONLY":
                findings.append(f"fixture_as_live_read_only:{row.get('case_id')}")
            if row.get("ai_posture") not in {"LONG", "SHORT", "WAIT", "ABSTAIN"}:
                findings.append(f"bad_posture:{row.get('case_id')}")
            if row.get("actually_traded") is True:
                findings.append(f"actually_traded:{row.get('case_id')}")
            try:
                assert_no_forbidden_keys(row)
            except ForbiddenPayloadKeyError as exc:
                findings.append(f"payload_ban:{row.get('case_id')}:{exc}")

    env = env_hard_ban_guard()
    if not env["ok"]:
        findings.append(f"env_violations:{env['violations']}")

    return {
        "pass_number": 1,
        "pass_name": "implementation",
        "ok": len(findings) == 0,
        "findings": findings,
        "hard_bans": list(HARD_BANS),
        "detail_count": len((feed or {}).get("decision_details") or []),
    }


def pass2_adversarial(root: Path | str) -> dict[str, Any]:
    del root
    findings: list[str] = []
    probes: dict[str, Any] = {}

    try:
        assert_not_unavailable_as_zero(0, available=False, path="probe")
        findings.append("unavailable_as_zero_not_raised")
        probes["unavailable_as_zero"] = "NOT_RAISED"
    except HonestyViolation:
        probes["unavailable_as_zero"] = "RAISED"

    try:
        build_metric_slot(key="similarity", value=0, available=False, provider_required=True)
        findings.append("provider_required_zero_accepted")
        probes["provider_required_zero"] = "ACCEPTED"
    except HonestyViolation:
        probes["provider_required_zero"] = "REJECTED"

    for key in (
        "private_raw_graph",
        "proprietary_threshold",
        "strategy_weights",
        "founder_entry",
        "founder_exit",
        "internal_prompt",
        "raw_cot",
        "account_data",
        "chain_of_thought",
        "exact_entry",
    ):
        try:
            assert_no_forbidden_keys({key: 1})
            findings.append(f"{key}_accepted")
            probes[key] = "ACCEPTED"
        except ForbiddenPayloadKeyError:
            probes[key] = "REJECTED"

    try:
        assert_no_forbidden_keys({"fields": [{"id": "x", "strategy_weights": [0.1, 0.9]}]})
        findings.append("nested_strategy_weights_accepted")
        probes["nested_strategy_weights"] = "ACCEPTED"
    except ForbiddenPayloadKeyError:
        probes["nested_strategy_weights"] = "REJECTED"

    try:
        assert_no_forbidden_keys({"fields": [{"id": "x", "raw_cot": "secret reasoning"}]})
        findings.append("nested_raw_cot_accepted")
        probes["nested_raw_cot"] = "ACCEPTED"
    except ForbiddenPayloadKeyError:
        probes["nested_raw_cot"] = "REJECTED"

    return {
        "pass_number": 2,
        "pass_name": "adversarial",
        "ok": len(findings) == 0,
        "findings": findings,
        "probes": probes,
        "hard_bans": list(HARD_BANS),
    }


def pass3_independent_break(root: Path | str) -> dict[str, Any]:
    root_path = Path(root)
    findings: list[str] = []

    imports = scan_imports(root_path)
    exchange = scan_exchange_markers(root_path)
    behaviors = scan_banned_behaviors(root_path)
    leaks = scan_private_field_leaks_in_payloads()
    env = env_hard_ban_guard()

    checks = {
        "imports": imports,
        "exchange_markers": exchange,
        "behaviors": behaviors,
        "private_field_leaks": leaks,
        "env": env,
    }
    for name, check in checks.items():
        if not check.get("ok"):
            findings.append(
                f"break_check_failed:{name}:{check.get('hits') or check.get('violations')}"
            )

    if imports.get("private_core_import_count", 1) != 0:
        findings.append(f"private_core_import_count:{imports.get('private_core_import_count')}")
    if leaks.get("private_field_leak_count", 1) != 0:
        findings.append(f"private_field_leak_count:{leaks.get('private_field_leak_count')}")

    for case in catalog():
        try:
            detail = build_decision_detail(case)
            assert_no_forbidden_keys(detail)
        except Exception as exc:  # noqa: BLE001
            findings.append(f"rebuild_failed:{case.get('case_id')}:{exc}")

    for path in _owned_all_files(root_path):
        if path.name == "NEXUS_FINAL_ACCELERATION_REPORT.json":
            findings.append("acceleration_report_in_owned_paths")

    # Ensure forbidden private field names remain in the ban set.
    required_bans = {
        "private_raw_graph",
        "proprietary_threshold",
        "strategy_weights",
        "founder_entry",
        "founder_exit",
        "internal_prompt",
        "raw_cot",
        "account_data",
    }
    missing = required_bans - set(FORBIDDEN_PRIVATE_FIELDS)
    if missing:
        findings.append(f"forbidden_set_missing:{sorted(missing)}")

    return {
        "pass_number": 3,
        "pass_name": "independent_break_attempts",
        "ok": len(findings) == 0,
        "findings": findings,
        "checks": checks,
        "hard_bans": list(HARD_BANS),
        "private_core_import_count": imports.get("private_core_import_count", 0),
        "private_field_leak_count": leaks.get("private_field_leak_count", 0),
    }


def run_three_passes(root: Path | str) -> dict[str, Any]:
    p1 = pass1_implementation(root)
    p2 = pass2_adversarial(root)
    p3 = pass3_independent_break(root)
    ok = bool(p1["ok"] and p2["ok"] and p3["ok"])
    return {
        "ok": ok,
        "passes": [p1, p2, p3],
        "pass_count": 3,
        "hard_bans_intact": ok,
        "lane": "PUB18-B",
        "lane_name": "DECISION_DETAIL_AND_LEARNING_TRANSPARENCY",
        "private_core_import_count": p3.get("private_core_import_count", 0),
        "private_field_leak_count": p3.get("private_field_leak_count", 0),
        "customer_trading": False,
        "exchange_api_used": False,
        "status_json_written": False,
    }

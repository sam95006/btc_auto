"""Hard-ban enforcement for PUB18-A Live Funnel — three passes."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_pub18_live_funnel.constants import (
    DATA_CLASS_LABELS,
    EXCHANGE_WRITE_MARKERS,
    FIRST_SCREEN_ANSWER_IDS,
    FORBIDDEN_FOUNDER_FIELDS,
    FUNNEL_STAGE_IDS,
    HARD_BANS,
    OWNED_PATHS,
    PRIVATE_CORE_IMPORT_PREFIXES,
)
from backend.nexus_pub18_live_funnel.fixtures import catalog
from backend.nexus_pub18_live_funnel.honesty import (
    HonestyViolation,
    assert_not_fake_live,
    assert_not_unavailable_as_zero,
    build_metric_slot,
)
from backend.nexus_pub18_live_funnel.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
    count_execution_controls,
    count_forbidden_key_hits,
)
from backend.nexus_pub18_live_funnel.service import (
    build_first_screen,
    list_first_screens,
)


BANNED_BEHAVIOR_PATTERNS = [
    re.compile(r"(?i)\bplace_order\b"),
    re.compile(r"(?i)\bsubmit_order\b"),
    re.compile(r"(?i)\bcreate_order\b"),
    re.compile(r"(?i)\bexecute_trade\b"),
    re.compile(r"(?i)\btrade_now\b"),
    re.compile(r"(?i)\bEXCHANGE_WRITE\s*=\s*True\b"),
    re.compile(r"(?i)\bMAINNET\s*=\s*True\b"),
]

TRADE_BUTTON_PATTERNS = [
    re.compile(r"(?i)>\s*Trade\s+Now\s*<"),
    re.compile(r"(?i)tradeNow\s*\("),
    re.compile(r"(?i)onClick=\{[^}]*placeOrder"),
]


class HardBanViolation(RuntimeError):
    """Raised when a PUB18-A hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "CUSTOMER_TRADING": os.environ.get("CUSTOMER_TRADING", "false").lower(),
        "PR26_MERGE": os.environ.get("PR26_MERGE", "false").lower(),
        "PR27_MERGE": os.environ.get("PR27_MERGE", "false").lower(),
        "EDIT_ACCELERATION_REPORT": os.environ.get("EDIT_ACCELERATION_REPORT", "false").lower(),
        "ARCHIVE_REBUILD": os.environ.get("ARCHIVE_REBUILD", "false").lower(),
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
        "no_trade",
        "no_place",
        "no_execution",
        "trade_buttons",
        "forbidden_founder",
        "forbidden_payload",
        "execution_control_count",
    )
    return any(tok in ctx for tok in allow_tokens)


_SCAN_SKIP_SUFFIXES = (
    "constants.py",
    "hard_bans.py",
    "sanitize.py",
)


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
        if rel.endswith(_SCAN_SKIP_SUFFIXES):
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
        if rel.endswith(_SCAN_SKIP_SUFFIXES):
            continue
        # Frontend denylist constant arrays are allowlisted by nearby ban commentary.
        if rel.endswith("liveFunnelModels.ts"):
            # Still scan for actionable trade-button JSX patterns only.
            for pat in TRADE_BUTTON_PATTERNS:
                for m in pat.finditer(text):
                    if _is_allowlisted_ban_context(text, m.start(), m.end()):
                        continue
                    hits.append({"file": rel, "match": m.group(0)})
            continue
        for pat in BANNED_BEHAVIOR_PATTERNS + TRADE_BUTTON_PATTERNS:
            for m in pat.finditer(text):
                if _is_allowlisted_ban_context(text, m.start(), m.end()):
                    continue
                hits.append({"file": rel, "match": m.group(0)})
    return {"ok": len(hits) == 0, "hits": hits}


def scan_private_field_leaks_in_payloads() -> dict[str, Any]:
    hits: list[str] = []
    exec_total = 0
    for case in catalog():
        screen = build_first_screen(case)
        for path in count_forbidden_key_hits(screen):
            hits.append(f"{case.get('case_id')}:{path}")
        exec_total += count_execution_controls(screen)
    return {
        "ok": len(hits) == 0 and exec_total == 0,
        "private_field_leak_count": len(hits),
        "execution_control_count": exec_total,
        "hits": hits,
    }


def pass1_implementation(root: Path | str) -> dict[str, Any]:
    root_path = Path(root)
    findings: list[str] = []

    for rel in OWNED_PATHS:
        if not (root_path / rel).exists():
            findings.append(f"missing_owned_path:{rel}")

    if list(FIRST_SCREEN_ANSWER_IDS) != [
        "global_market_state",
        "crypto_derivatives_risk",
        "top_3_opportunities",
        "ai_posture",
        "supporting_evidence",
        "counter_evidence",
        "invalidation",
        "data_freshness",
        "data_class_label",
    ]:
        findings.append(f"answer_ids_mismatch:{FIRST_SCREEN_ANSWER_IDS}")

    if list(FUNNEL_STAGE_IDS) != [
        "scanned",
        "data_available",
        "liquidity",
        "data_trust",
        "candidate",
        "ai_review",
        "cost_blocked",
        "risk_blocked",
        "shadow_decisions",
    ]:
        findings.append(f"funnel_stage_mismatch:{FUNNEL_STAGE_IDS}")

    try:
        feed = list_first_screens()
    except Exception as exc:  # noqa: BLE001
        findings.append(f"list_first_screens_failed:{exc}")
        feed = None

    if feed is not None:
        if feed.get("ok") is not True:
            findings.append("feed_not_ok")
        if feed.get("private_field_leak_count", 1) != 0:
            findings.append("private_field_leak_count_nonzero")
        if feed.get("execution_control_count", 1) != 0:
            findings.append("execution_control_count_nonzero")
        rows = feed.get("first_screens") or []
        if len(rows) < 4:
            findings.append(f"too_few_screens:{len(rows)}")
        labels_seen = set()
        for row in rows:
            ids = [a.get("id") for a in (row.get("answers") or [])]
            if ids != list(FIRST_SCREEN_ANSWER_IDS):
                findings.append(f"answers_order:{row.get('case_id')}:{ids}")
            chrome = str(row.get("chrome_label", "")).upper()
            if chrome == "LIVE":
                findings.append(f"bare_live:{row.get('case_id')}")
            dc = str(row.get("data_class", "")).upper()
            labels_seen.add(dc)
            if dc not in DATA_CLASS_LABELS:
                findings.append(f"bad_data_class:{row.get('case_id')}:{dc}")
            if row.get("ai_posture") not in {"LONG", "SHORT", "WAIT", "ABSTAIN"}:
                findings.append(f"bad_posture:{row.get('case_id')}")
            if row.get("trade_buttons") is True:
                findings.append(f"trade_buttons:{row.get('case_id')}")
            if row.get("actually_traded") is True:
                findings.append(f"actually_traded:{row.get('case_id')}")
            funnel = row.get("funnel") or {}
            stages = funnel.get("stages") or []
            if [s.get("id") for s in stages] != list(FUNNEL_STAGE_IDS):
                findings.append(f"funnel_order:{row.get('case_id')}")
            for s in stages:
                if not s.get("available") and s.get("display") in {"0", 0}:
                    findings.append(f"unavailable_as_zero:{row.get('case_id')}:{s.get('id')}")
            for a in row.get("answers") or []:
                if a.get("id") != "crypto_derivatives_risk":
                    continue
                for m in a.get("metrics") or []:
                    if not m.get("available") and m.get("display") in {"0", 0}:
                        findings.append(f"metric_unavailable_as_zero:{row.get('case_id')}:{m.get('key')}")
            try:
                assert_no_forbidden_keys(row)
            except ForbiddenPayloadKeyError as exc:
                findings.append(f"payload_ban:{row.get('case_id')}:{exc}")
            if count_execution_controls(row) != 0:
                findings.append(f"exec_controls:{row.get('case_id')}")

        for required in DATA_CLASS_LABELS:
            if required not in labels_seen:
                findings.append(f"missing_data_class_case:{required}")

    env = env_hard_ban_guard()
    if not env["ok"]:
        findings.append(f"env_violations:{env['violations']}")

    return {
        "pass_number": 1,
        "pass_name": "implementation",
        "ok": len(findings) == 0,
        "findings": findings,
        "hard_bans": list(HARD_BANS),
        "screen_count": len((feed or {}).get("first_screens") or []),
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
        build_metric_slot(key="funding", value=0, available=False, provider_required=True)
        findings.append("provider_required_zero_accepted")
        probes["provider_required_zero"] = "ACCEPTED"
    except HonestyViolation:
        probes["provider_required_zero"] = "REJECTED"

    try:
        assert_not_fake_live(data_class="FIXTURE", chrome_label="LIVE")
        findings.append("fixture_as_live_not_raised")
        probes["fixture_as_live"] = "NOT_RAISED"
    except HonestyViolation:
        probes["fixture_as_live"] = "RAISED"

    try:
        assert_not_fake_live(data_class="FIXTURE", chrome_label="LIVE_READ_ONLY")
        findings.append("fixture_as_live_readonly_not_raised")
        probes["fixture_as_live_readonly"] = "NOT_RAISED"
    except HonestyViolation:
        probes["fixture_as_live_readonly"] = "RAISED"

    for key in (
        "position_size",
        "leverage",
        "exact_entry",
        "exact_stop",
        "order_id",
        "private_threshold",
        "lesson_memory",
        "place_order",
        "trade_now",
        "execution_controls",
    ):
        try:
            assert_no_forbidden_keys({key: 1})
            findings.append(f"{key}_accepted")
            probes[key] = "ACCEPTED"
        except ForbiddenPayloadKeyError:
            probes[key] = "REJECTED"

    try:
        assert_no_forbidden_keys({"answers": [{"id": "x", "leverage": 25}]})
        findings.append("nested_leverage_accepted")
        probes["nested_leverage"] = "ACCEPTED"
    except ForbiddenPayloadKeyError:
        probes["nested_leverage"] = "REJECTED"

    poisoned = {"execution_controls": {"place_order": True}}
    if count_execution_controls(poisoned) == 0:
        findings.append("execution_control_counter_missed")
        probes["execution_control_count"] = "MISSED"
    else:
        probes["execution_control_count"] = "DETECTED"

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
    if leaks.get("execution_control_count", 1) != 0:
        findings.append(f"execution_control_count:{leaks.get('execution_control_count')}")

    for case in catalog():
        try:
            screen = build_first_screen(case)
            assert_no_forbidden_keys(screen)
        except Exception as exc:  # noqa: BLE001
            findings.append(f"rebuild_failed:{case.get('case_id')}:{exc}")

    for path in _owned_all_files(root_path):
        if path.name == "NEXUS_FINAL_ACCELERATION_REPORT.json":
            findings.append("acceleration_report_in_owned_paths")

    return {
        "pass_number": 3,
        "pass_name": "independent_break_attempts",
        "ok": len(findings) == 0,
        "findings": findings,
        "checks": checks,
        "hard_bans": list(HARD_BANS),
        "private_core_import_count": imports.get("private_core_import_count", 0),
        "private_field_leak_count": leaks.get("private_field_leak_count", 0),
        "execution_control_count": leaks.get("execution_control_count", 0),
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
        "lane": "PUB18-A",
        "lane_name": "LIVE_FUNNEL_AND_MARKET_PULSE",
        "private_core_import_count": p3.get("private_core_import_count", 0),
        "private_field_leak_count": p3.get("private_field_leak_count", 0),
        "execution_control_count": p3.get("execution_control_count", 0),
        "customer_trading": False,
        "exchange_api_used": False,
        "status_json_written": False,
    }

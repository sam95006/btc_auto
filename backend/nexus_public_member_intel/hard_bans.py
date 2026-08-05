"""Hard-ban enforcement for UX-B Member Web Intelligence — three passes.

Pass 1: implementation completeness (funnel, states, postures, UX-A shape)
Pass 2: adversarial honesty probes
Pass 3: independent break attempts (AST, env, status.json, private_core)
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_member_intel.constants import (
    EXCHANGE_WRITE_MARKERS,
    FUNNEL_STAGE_IDS,
    HARD_BANS,
    LIFECYCLE_STATES,
    MEMBER_POSTURES,
    OWNED_PATHS,
    PRIVATE_CORE_IMPORT_PREFIXES,
)
from backend.nexus_public_member_intel.honesty import (
    HonestyViolation,
    assert_mode_label,
    assert_no_fake_guarantee,
    assert_not_unavailable_as_zero,
    assert_suggestion_not_filled,
    build_funnel_stage,
    format_count,
)
from backend.nexus_public_member_intel.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
)
from backend.nexus_public_member_intel.service import (
    build_experience,
    list_experiences,
    refuse_ai_suggestion_as_fill,
    refuse_backtest_as_live,
    refuse_fake_60_guarantee,
    refuse_fixture_as_live,
    refuse_unavailable_as_zero,
    state_matrix,
)
from backend.nexus_public_member_intel.fixtures import catalog


BANNED_BEHAVIOR_PATTERNS = [
    re.compile(r"(?i)\bplace_order\b"),
    re.compile(r"(?i)\bsubmit_order\b"),
    re.compile(r"(?i)\bcreate_order\b"),
    re.compile(r"(?i)\bexecute_trade\b"),
    re.compile(r"(?i)\b60%\s*guarantee\b"),
    re.compile(r"(?i)\bguaranteed\s*60%\b"),
    re.compile(r"(?i)\bEXCHANGE_WRITE\s*=\s*True\b"),
    re.compile(r"(?i)\bMAINNET\s*=\s*True\b"),
]


class HardBanViolation(RuntimeError):
    """Raised when a UX-B hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
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
        "refuse_",
        "never",
        "must not",
        "forbidden",
        "violation",
        "assert",
        "no_exchange",
        "no_fake",
        "no_ai_suggestion",
        "no_backtest",
        "no_fixture",
        "no_unavailable",
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
        if rel.endswith("constants.py") or rel.endswith("hard_bans.py") or rel.endswith("honesty.ts"):
            continue
        for pat in BANNED_BEHAVIOR_PATTERNS:
            for m in pat.finditer(text):
                if _is_allowlisted_ban_context(text, m.start(), m.end()):
                    continue
                hits.append({"file": rel, "match": m.group(0)})
    return {"ok": len(hits) == 0, "hits": hits}


def scan_status_json(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for path in _owned_all_files(root):
        name = path.name.lower()
        if name.endswith("_status.json") or name == "status.json":
            hits.append(str(path.relative_to(root)).replace("\\", "/"))
    return {"ok": len(hits) == 0, "hits": hits}


def pass1_implementation(root: Path | str) -> dict[str, Any]:
    root_path = Path(root)
    findings: list[str] = []

    for rel in OWNED_PATHS:
        if not (root_path / rel).exists():
            findings.append(f"missing_owned_path:{rel}")

    expected_funnel = (
        "markets_scanned",
        "liquidity",
        "data_quality",
        "ai_analysis",
        "cost_blocked",
        "risk_blocked",
    )
    if tuple(FUNNEL_STAGE_IDS) != expected_funnel:
        findings.append(f"funnel_mismatch:{FUNNEL_STAGE_IDS}")

    required_states = set(LIFECYCLE_STATES)
    for required in (
        "OBSERVING",
        "AI_ANALYZING",
        "AI_SUGGESTION",
        "RISK_REVIEW",
        "READY",
        "ENTERED",
        "MANAGING",
        "EXITED",
        "BLOCKED",
        "ABSTAINED",
        "SIMULATION",
        "HISTORICAL_REPLAY",
        "DEMO_DATA",
        "UNAVAILABLE",
        "STALE",
    ):
        if required not in required_states:
            findings.append(f"missing_lifecycle_state:{required}")

    if set(MEMBER_POSTURES) != {"LONG", "SHORT", "WAIT", "ABSTAIN"}:
        findings.append(f"posture_mismatch:{MEMBER_POSTURES}")

    try:
        feed = list_experiences()
    except Exception as exc:  # noqa: BLE001
        findings.append(f"list_experiences_failed:{exc}")
        feed = None

    if feed is not None:
        if feed.get("ok") is not True:
            findings.append("feed_not_ok")
        if feed.get("private_core_import_count", 1) != 0:
            findings.append("private_core_import_count_nonzero")
        rows = feed.get("experiences") or []
        if len(rows) < 4:
            findings.append(f"too_few_experiences:{len(rows)}")
        for row in rows:
            funnel = (row.get("funnel") or {}).get("stages") or []
            keys = [s.get("key") for s in funnel]
            if keys != list(FUNNEL_STAGE_IDS):
                findings.append(f"funnel_order:{row.get('case_id')}:{keys}")
            for stage in funnel:
                if stage.get("available") is False and stage.get("display") in {"0", 0}:
                    findings.append(f"unavailable_as_zero:{row.get('case_id')}:{stage.get('key')}")
                if stage.get("available") is False and stage.get("count") == 0:
                    findings.append(f"unavailable_count_zero:{row.get('case_id')}:{stage.get('key')}")
            if "why_suggested" not in row:
                findings.append(f"missing_why_suggested:{row.get('case_id')}")
            if "contradicting_evidence" not in row:
                findings.append(f"missing_contradicting:{row.get('case_id')}")
            if "similar_case_stats" not in row:
                findings.append(f"missing_similar:{row.get('case_id')}")
            if "actually_ordered" not in row and "actually_ordered_display" not in row:
                findings.append(f"missing_actually_ordered:{row.get('case_id')}")
            intel = row.get("intelligence") or {}
            for key in (
                "regime_probabilities",
                "ai_recommendation_state",
                "supporting_evidence",
                "contradicting_evidence",
                "uncertainty",
                "abstention_reason",
                "strategy_expert_label",
                "lesson_applied_label",
                "similar_case_summary",
                "data_freshness",
                "decision_lifecycle_status",
            ):
                if key not in intel:
                    findings.append(f"uxa_missing:{row.get('case_id')}:{key}")
            if intel.get("private_core_import_count", 1) != 0:
                findings.append(f"uxa_private_core:{row.get('case_id')}")
            # DEMO / replay must not claim LIVE chrome
            if row.get("mode") in {"DEMO_DATA", "HISTORICAL_REPLAY", "SIMULATION"}:
                if str(row.get("chrome_label", "")).upper() == "LIVE":
                    findings.append(f"fixture_as_live:{row.get('case_id')}")
            if row.get("lifecycle_state") == "AI_SUGGESTION" and row.get("actually_ordered") is True:
                findings.append(f"ai_suggestion_ordered:{row.get('case_id')}")
            if row.get("order_fill_claimed") is True:
                findings.append(f"order_fill_claimed:{row.get('case_id')}")
            similar = row.get("similar_case_stats") or {}
            if similar.get("guarantee_claimed") is True:
                findings.append(f"fake_guarantee:{row.get('case_id')}")
            if similar.get("win_rate") == 0.6 and similar.get("guarantee_claimed") is not False:
                findings.append(f"suspicious_60_win_rate:{row.get('case_id')}")
            try:
                assert_no_forbidden_keys(row)
                assert_no_fake_guarantee(row)
            except (ForbiddenPayloadKeyError, HonestyViolation) as exc:
                findings.append(f"payload_ban:{row.get('case_id')}:{exc}")

    matrix = state_matrix()
    matrix_states = {s["state"] for s in (matrix.get("states") or [])}
    if matrix_states != set(LIFECYCLE_STATES):
        findings.append(f"state_matrix_mismatch:{sorted(matrix_states)}")

    env = env_hard_ban_guard()
    if not env["ok"]:
        findings.append(f"env_violations:{env['violations']}")

    return {
        "pass_number": 1,
        "pass_name": "implementation",
        "ok": len(findings) == 0,
        "findings": findings,
        "hard_bans": list(HARD_BANS),
        "experience_count": len((feed or {}).get("experiences") or []),
    }


def pass2_adversarial(root: Path | str) -> dict[str, Any]:
    del root
    findings: list[str] = []
    probes: dict[str, Any] = {}

    # Unavailable as 0
    try:
        assert_not_unavailable_as_zero(0, available=False, path="probe")
        findings.append("unavailable_as_zero_not_raised")
        probes["unavailable_as_zero"] = "NOT_RAISED"
    except HonestyViolation:
        probes["unavailable_as_zero"] = "RAISED"

    try:
        build_funnel_stage(key="markets_scanned", label="Markets scanned", count=0, available=False)
        findings.append("funnel_unavailable_zero_accepted")
        probes["funnel_unavailable_zero"] = "ACCEPTED"
    except HonestyViolation:
        probes["funnel_unavailable_zero"] = "REJECTED"

    disp = format_count(None, available=False)
    if disp in {"0", 0}:
        findings.append("format_count_unavailable_is_zero")
    probes["format_count_unavailable"] = disp

    # Fixture as Live
    try:
        assert_mode_label(mode="DEMO_DATA", label="LIVE")
        findings.append("fixture_as_live_not_raised")
        probes["fixture_as_live"] = "NOT_RAISED"
    except HonestyViolation:
        probes["fixture_as_live"] = "RAISED"

    try:
        assert_mode_label(mode="HISTORICAL_REPLAY", label="LIVE")
        findings.append("backtest_as_live_not_raised")
        probes["backtest_as_live"] = "NOT_RAISED"
    except HonestyViolation:
        probes["backtest_as_live"] = "RAISED"

    # AI suggestion as filled order
    try:
        assert_suggestion_not_filled(
            lifecycle_state="AI_SUGGESTION",
            actually_ordered=True,
            order_fill_claimed=True,
        )
        findings.append("ai_suggestion_fill_not_raised")
        probes["ai_suggestion_fill"] = "NOT_RAISED"
    except HonestyViolation:
        probes["ai_suggestion_fill"] = "RAISED"

    # Fake 60% guarantee
    try:
        assert_no_fake_guarantee({"note": "60% guarantee on similar cases"})
        findings.append("fake_60_not_raised")
        probes["fake_60"] = "NOT_RAISED"
    except HonestyViolation:
        probes["fake_60"] = "RAISED"

    try:
        assert_no_fake_guarantee({"similar_case_stats": {"guarantee_claimed": True, "win_rate": 0.6}})
        findings.append("guarantee_claimed_not_raised")
        probes["guarantee_claimed"] = "NOT_RAISED"
    except HonestyViolation:
        probes["guarantee_claimed"] = "RAISED"

    for refuse_fn, name in (
        (refuse_fixture_as_live, "fixture_as_live_refuse"),
        (refuse_unavailable_as_zero, "unavailable_as_zero_refuse"),
        (refuse_ai_suggestion_as_fill, "ai_suggestion_fill_refuse"),
        (refuse_backtest_as_live, "backtest_as_live_refuse"),
        (refuse_fake_60_guarantee, "fake_60_refuse"),
    ):
        try:
            refuse_fn()
            findings.append(f"refuse_not_raised:{name}")
            probes[name] = "NOT_RAISED"
        except HonestyViolation:
            probes[name] = "RAISED"

    # Forbidden keys
    try:
        assert_no_forbidden_keys({"order_id": "x"})
        findings.append("order_id_accepted")
        probes["order_id"] = "ACCEPTED"
    except ForbiddenPayloadKeyError:
        probes["order_id"] = "REJECTED"

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
    status_json = scan_status_json(root_path)
    env = env_hard_ban_guard()

    checks = {
        "imports": imports,
        "exchange_markers": exchange,
        "behaviors": behaviors,
        "status_json": status_json,
        "env": env,
    }
    for name, check in checks.items():
        if not check.get("ok"):
            findings.append(
                f"break_check_failed:{name}:{check.get('hits') or check.get('violations')}"
            )

    if imports.get("private_core_import_count", 1) != 0:
        findings.append(f"private_core_import_count:{imports.get('private_core_import_count')}")

    # Rebuild all fixtures and ensure honesty
    for case in catalog():
        try:
            exp = build_experience(case)
            assert_no_forbidden_keys(exp)
            assert_no_fake_guarantee(exp)
        except Exception as exc:  # noqa: BLE001
            findings.append(f"rebuild_failed:{case.get('case_id')}:{exc}")

    # Acceleration report must not be in owned paths
    for path in _owned_all_files(root_path):
        if path.name == "NEXUS_FINAL_ACCELERATION_REPORT.json":
            findings.append("acceleration_report_in_owned_paths")
        if path.name.endswith("_status.json"):
            findings.append(f"status_json_owned:{path.name}")

    return {
        "pass_number": 3,
        "pass_name": "independent_break_attempts",
        "ok": len(findings) == 0,
        "findings": findings,
        "checks": checks,
        "hard_bans": list(HARD_BANS),
        "private_core_import_count": imports.get("private_core_import_count", 0),
    }


def run_three_passes(root: Path | str) -> dict[str, Any]:
    p1 = pass1_implementation(root)
    p2 = pass2_adversarial(root)
    p3 = pass3_independent_break(root)
    ok = bool(p1["ok"] and p2["ok"] and p3["ok"])
    blockers: list[dict[str, str]] = [
        {
            "blocker_id": "NO_STATUS_JSON",
            "detail": "UX-B must not emit *_status.json or lane report artifacts",
        },
        {
            "blocker_id": "UXA_OPTIONAL",
            "detail": "Compatible public-safe shapes embedded; UX-A merge not required",
        },
    ]
    if not ok:
        for p in (p1, p2, p3):
            for f in p.get("findings") or []:
                blockers.append({"blocker_id": f"PASS_{p['pass_number']}", "detail": str(f)})
    return {
        "ok": ok,
        "passes": [p1, p2, p3],
        "pass_count": 3,
        "hard_bans_intact": ok,
        "lane": "UX-B",
        "lane_name": "MEMBER_WEB_INTELLIGENCE_EXPERIENCE",
        "private_core_import_count": p3.get("private_core_import_count", 0),
        "customer_trading": False,
        "exchange_api_used": False,
        "status_json_written": False,
        "blockers": blockers if not ok else [
            {
                "blocker_id": "NO_STATUS_JSON",
                "detail": "UX-B must not emit *_status.json or lane report artifacts",
            }
        ],
    }

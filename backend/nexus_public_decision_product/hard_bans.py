"""Hard-ban enforcement for PUB2-A Decision Product E2E — three passes.

Pass 1: implementation completeness
Pass 2: adversarial probes
Pass 3: independent break attempts
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_decision_product.constants import (
    EXCHANGE_WRITE_MARKERS,
    EXCLUDED_STAGES,
    FLOW_STAGE_IDS,
    FLOW_STAGE_LABELS,
    HARD_BANS,
    OWNED_PATHS,
    PRIVATE_CORE_IMPORT_PREFIXES,
)
from backend.nexus_public_decision_product.journey import (
    JourneyError,
    refuse_execution_stage,
    run_customer_journey,
)
from backend.nexus_public_decision_product.sanitize import (
    ForbiddenPayloadKeyError,
    assert_no_forbidden_keys,
)


BANNED_BEHAVIOR_PATTERNS = [
    re.compile(r"(?i)\bplace_order\b"),
    re.compile(r"(?i)\bsubmit_order\b"),
    re.compile(r"(?i)\bcreate_order\b"),
    re.compile(r"(?i)\bexecute_trade\b"),
    re.compile(r"(?i)\bcopy_trad(?:e|ing)\b"),
    re.compile(r"(?i)\bEXCHANGE_WRITE\s*=\s*True\b"),
    re.compile(r"(?i)\bMAINNET\s*=\s*True\b"),
    re.compile(r"(?i)\bREAL_MONEY\s*=\s*True\b"),
    re.compile(r"(?i)\bDEMO_ORDERS\s*=\s*True\b"),
    re.compile(r"(?i)\bSHADOW_ORDERS\s*=\s*True\b"),
]


class HardBanViolation(RuntimeError):
    """Raised when a PUB2-A hard ban would be violated."""


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
        "CUSTOMER_TRADING": os.environ.get("CUSTOMER_TRADING", "false").lower(),
        "AUTO_ORDERS": os.environ.get("AUTO_ORDERS", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": list(HARD_BANS),
    }


def refuse_customer_trading() -> None:
    raise HardBanViolation("HARD BAN: customer trading refused in PUB2-A Decision Product")


def refuse_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: exchange write refused in PUB2-A Decision Product")


def refuse_private_core_exposure() -> None:
    raise HardBanViolation("HARD BAN: private-core exposure refused in PUB2-A Decision Product")


def refuse_fabricated_customers() -> None:
    raise HardBanViolation("HARD BAN: fabricated customers/metrics refused in PUB2-A")


def refuse_status_json() -> None:
    raise HardBanViolation("HARD BAN: human-facing *_status.json refused in PUB2-A")


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
        "no_exchange",
        "no_customer",
        "never",
        "must not",
        "forbidden",
        "violation",
        "assert",
        "raise hardban",
        "excluded_stages",
        "exchange_write_markers",
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
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_private_core_exposure"}


def scan_exchange_markers(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _owned_py_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        # Ban-definition modules intentionally list markers / excluded stage ids.
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
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_exchange_write"}


def scan_banned_behaviors(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for path in _owned_py_files(root):
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
                hits.append(
                    {
                        "file": rel,
                        "match": m.group(0),
                    }
                )
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_customer_trading"}


def scan_status_json(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for path in _owned_all_files(root):
        name = path.name.lower()
        if name.endswith("_status.json") or name == "status.json":
            hits.append(str(path.relative_to(root)).replace("\\", "/"))
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_human_facing_status_json"}


def pass1_implementation(root: Path | str) -> dict[str, Any]:
    """Pass 1 — implementation completeness of the customer-safe flow."""
    root_path = Path(root)
    findings: list[str] = []

    expected_labels = [
        "Market Observation",
        "Public Evidence",
        "Counter Evidence",
        "Risk Conditions",
        "Public Decision Object",
        "Thesis Monitor",
        "Outcome Review",
        "Decision Memory",
    ]
    if list(FLOW_STAGE_LABELS) != expected_labels:
        findings.append(f"flow_labels_mismatch:{FLOW_STAGE_LABELS}")
    if len(FLOW_STAGE_IDS) != 8:
        findings.append(f"flow_stage_count:{len(FLOW_STAGE_IDS)}")

    for rel in OWNED_PATHS:
        if not (root_path / rel).exists():
            findings.append(f"missing_owned_path:{rel}")

    try:
        journey = run_customer_journey()
    except Exception as exc:  # noqa: BLE001
        findings.append(f"journey_failed:{exc}")
        journey = None

    if journey is not None:
        if journey.get("stage_count") != 8:
            findings.append(f"stage_count:{journey.get('stage_count')}")
        if journey.get("execution_controls") is not False:
            findings.append("execution_controls_not_false")
        if journey.get("fabricated_customers") is not False:
            findings.append("fabricated_customers_flag")
        if journey.get("fabricated_metrics") is not False:
            findings.append("fabricated_metrics_flag")
        if journey.get("source") != "public_decision_cloud_staging_fixtures":
            findings.append("non_fixture_source")
        stage_ids = [s.get("stage_id") for s in journey.get("stages") or []]
        if stage_ids != list(FLOW_STAGE_IDS):
            findings.append(f"stage_order_mismatch:{stage_ids}")
        try:
            assert_no_forbidden_keys(journey)
        except ForbiddenPayloadKeyError as exc:
            findings.append(f"forbidden_key:{exc}")

    env = env_hard_ban_guard()
    if not env["ok"]:
        findings.append(f"env_violations:{env['violations']}")

    return {
        "pass_number": 1,
        "pass_name": "implementation",
        "ok": len(findings) == 0,
        "findings": findings,
        "hard_bans": list(HARD_BANS),
        "flow": list(FLOW_STAGE_IDS),
    }


def pass2_adversarial(root: Path | str) -> dict[str, Any]:
    """Pass 2 — adversarial probes against execution and fabrication."""
    del root  # scans use live code paths; root reserved for API symmetry
    findings: list[str] = []
    probes: dict[str, Any] = {}

    # Execution stage injection must fail closed
    for banned in ("execution", "order_placement", "demo_orders", "shadow_orders", "mainnet_trading"):
        try:
            refuse_execution_stage(banned)
            findings.append(f"execution_stage_not_refused:{banned}")
            probes[banned] = "NOT_REFUSED"
        except JourneyError:
            probes[banned] = "REFUSED"

    for refuse_fn, name in (
        (refuse_customer_trading, "customer_trading"),
        (refuse_exchange_write, "exchange_write"),
        (refuse_private_core_exposure, "private_core"),
        (refuse_fabricated_customers, "fabricated_customers"),
        (refuse_status_json, "status_json"),
    ):
        try:
            refuse_fn()
            findings.append(f"refuse_not_raised:{name}")
            probes[name] = "NOT_RAISED"
        except HardBanViolation:
            probes[name] = "RAISED"

    # Fabricated customer/metric payloads must be rejected
    try:
        assert_no_forbidden_keys({"paid_pilot_count": 3})
        findings.append("fabricated_metric_key_accepted")
        probes["fabricated_metric_sanitize"] = "ACCEPTED"
    except ForbiddenPayloadKeyError:
        probes["fabricated_metric_sanitize"] = "REJECTED"

    try:
        assert_no_forbidden_keys({"fabricated_customer": "alice"})
        findings.append("fabricated_customer_key_accepted")
        probes["fabricated_customer_sanitize"] = "ACCEPTED"
    except ForbiddenPayloadKeyError:
        probes["fabricated_customer_sanitize"] = "REJECTED"

    # Excluded stages must remain outside the public flow
    overlap = set(FLOW_STAGE_IDS) & set(EXCLUDED_STAGES)
    if overlap:
        findings.append(f"excluded_in_flow:{sorted(overlap)}")

    return {
        "pass_number": 2,
        "pass_name": "adversarial",
        "ok": len(findings) == 0,
        "findings": findings,
        "probes": probes,
        "hard_bans": list(HARD_BANS),
    }


def pass3_independent_break(root: Path | str) -> dict[str, Any]:
    """Pass 3 — independent break attempts (AST, env, skip-stage, status.json)."""
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
            findings.append(f"break_check_failed:{name}:{check.get('hits') or check.get('violations')}")

    # Skip-stage / reorder attack: journey must always emit full ordered flow
    journey = run_customer_journey()
    stage_ids = [s.get("stage_id") for s in journey.get("stages") or []]
    if stage_ids != list(FLOW_STAGE_IDS):
        findings.append(f"reorder_or_skip_detected:{stage_ids}")

    # Unknown decision must fail closed (not invent customers)
    try:
        run_customer_journey(decision_id="dec_fabricated_customer_999")
        findings.append("unknown_decision_not_rejected")
    except JourneyError:
        pass

    # Acceleration report must remain untouched by this package
    accel = root_path / "NEXUS_FINAL_ACCELERATION_REPORT.json"
    # Report lives outside worktree typically; owned package must not write it
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
        "accel_path_checked": str(accel),
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
        "lane": "PUB2-A",
        "lane_name": "PUBLIC_DECISION_PRODUCT_E2E",
        "execution_controls": False,
        "customer_trading": False,
        "fabricated_customers": False,
        "fabricated_metrics": False,
    }

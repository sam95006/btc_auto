"""Hard-ban enforcement for UX-A Public Intelligence DTO V2 — three passes.

Pass 1: implementation completeness
Pass 2: adversarial probes (forbidden fields / secrets / memory graph)
Pass 3: independent break attempts (AST private-core imports, exchange write)
"""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_intelligence_dto_v2.constants import (
    AI_RECOMMENDATION_STATES,
    DECISION_LIFECYCLE_STATUSES,
    DENIED_PRIVATE_FIELDS,
    EXCHANGE_WRITE_MARKERS,
    FAIL_RECOMMENDATION,
    HARD_BANS,
    LESSON_APPLIED_LABELS,
    OWNED_PATHS,
    PASS_COUNT,
    PASS_RECOMMENDATION,
    PRIVATE_CORE_IMPORT_PREFIXES,
    REGIME_PROBABILITY_KEYS,
    SCHEMA_VERSION,
    STRATEGY_EXPERT_LABELS,
)
from backend.nexus_public_intelligence_dto_v2.dto import (
    REQUIRED_TOP_LEVEL_KEYS,
    build_abstain_fixture,
    build_fixture_dto,
    publish_public_intelligence_dto,
)
from backend.nexus_public_intelligence_dto_v2.sanitize import (
    ForbiddenPayloadKeyError,
    assert_allowlisted_only,
    assert_no_forbidden_keys,
    collect_field_names,
    serialize_allowlist,
)


class HardBanViolation(RuntimeError):
    """Raised when a UX-A hard ban would be violated."""


BANNED_BEHAVIOR_PATTERNS = [
    re.compile(r"(?i)\bplace_order\b"),
    re.compile(r"(?i)\bsubmit_order\b"),
    re.compile(r"(?i)\bcreate_order\b"),
    re.compile(r"(?i)\bexecute_trade\b"),
    re.compile(r"(?i)\bEXCHANGE_WRITE\s*=\s*True\b"),
    re.compile(r"(?i)\bMAINNET\s*=\s*True\b"),
    re.compile(r"(?i)\bREAL_MONEY\s*=\s*True\b"),
]


def env_hard_ban_guard() -> dict[str, Any]:
    flags = {
        "EXCHANGE_WRITE": os.environ.get("EXCHANGE_WRITE", "false").lower(),
        "MAINNET": os.environ.get("MAINNET", "false").lower(),
        "REAL_MONEY": os.environ.get("REAL_MONEY", "false").lower(),
        "DEMO_ORDERS": os.environ.get("DEMO_ORDERS", "false").lower(),
        "SHADOW_ORDERS": os.environ.get("SHADOW_ORDERS", "false").lower(),
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {
        "ok": len(violations) == 0,
        "flags": flags,
        "violations": violations,
        "hard_bans": list(HARD_BANS),
    }


def refuse_secrets() -> None:
    raise HardBanViolation("HARD BAN: secrets refused in public intelligence DTO V2")


def refuse_internal_strategy_source() -> None:
    raise HardBanViolation("HARD BAN: internal strategy source refused")


def refuse_private_execution_controls() -> None:
    raise HardBanViolation("HARD BAN: private execution controls refused")


def refuse_proprietary_thresholds() -> None:
    raise HardBanViolation("HARD BAN: proprietary thresholds refused")


def refuse_raw_private_memory_graph() -> None:
    raise HardBanViolation("HARD BAN: raw private memory graph refused")


def refuse_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: exchange write refused")


def refuse_private_core_imports() -> None:
    raise HardBanViolation("HARD BAN: private-core imports refused")


def refuse_status_json() -> None:
    raise HardBanViolation("HARD BAN: human-facing *_status.json refused")


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
        "never",
        "must not",
        "forbidden",
        "violation",
        "assert",
        "raise hardban",
        "exchange_write_markers",
        "denied_private",
    )
    return any(tok in ctx for tok in allow_tokens)


def scan_private_core_imports(root: Path) -> dict[str, Any]:
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
    return {
        "ok": len(hits) == 0,
        "hits": hits,
        "private_core_import_count": len(hits),
        "ban": "no_private_core_imports",
    }


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
                hits.append({"file": rel, "match": m.group(0)})
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_exchange_write"}


def scan_status_json(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for path in _owned_all_files(root):
        name = path.name.lower()
        if name.endswith("_status.json") or name == "status.json":
            hits.append(str(path.relative_to(root)).replace("\\", "/"))
    return {"ok": len(hits) == 0, "hits": hits, "ban": "no_status_json_artifact"}


def pass1_implementation(root: Path | str) -> dict[str, Any]:
    """Pass 1 — DTO surface completeness."""
    root_path = Path(root)
    findings: list[str] = []

    for rel in OWNED_PATHS:
        if not (root_path / rel).exists():
            findings.append(f"missing_owned_path:{rel}")

    try:
        payload = publish_public_intelligence_dto()
    except Exception as exc:  # noqa: BLE001
        findings.append(f"publish_failed:{exc}")
        payload = None

    if payload is not None:
        for key in REQUIRED_TOP_LEVEL_KEYS:
            if key not in payload:
                findings.append(f"missing_key:{key}")
        if payload.get("schema_version") != SCHEMA_VERSION:
            findings.append(f"schema_mismatch:{payload.get('schema_version')}")
        if payload.get("private_core_import_count") != 0:
            findings.append(
                f"private_core_import_count:{payload.get('private_core_import_count')}"
            )
        if payload.get("raw_memory_graph") is not False:
            findings.append("raw_memory_graph_not_false")
        if payload.get("private_fields_included") is not False:
            findings.append("private_fields_included_not_false")
        regime = payload.get("regime_probabilities") or {}
        for rk in REGIME_PROBABILITY_KEYS:
            if rk not in regime:
                findings.append(f"missing_regime_key:{rk}")
        if payload.get("ai_recommendation_state") not in AI_RECOMMENDATION_STATES:
            findings.append(f"bad_ai_state:{payload.get('ai_recommendation_state')}")
        if payload.get("decision_lifecycle_status") not in DECISION_LIFECYCLE_STATUSES:
            findings.append(f"bad_lifecycle:{payload.get('decision_lifecycle_status')}")
        if payload.get("strategy_expert_label") not in STRATEGY_EXPERT_LABELS:
            findings.append(f"bad_expert_label:{payload.get('strategy_expert_label')}")
        if payload.get("lesson_applied_label") not in LESSON_APPLIED_LABELS:
            findings.append(f"bad_lesson_label:{payload.get('lesson_applied_label')}")
        if not isinstance(payload.get("supporting_evidence"), list):
            findings.append("supporting_evidence_not_list")
        if not isinstance(payload.get("contradicting_evidence"), list):
            findings.append("contradicting_evidence_not_list")
        similar = payload.get("similar_case_summary") or {}
        if not similar.get("similar_case_summary"):
            findings.append("missing_similar_case_summary")
        try:
            assert_allowlisted_only(payload)
        except ForbiddenPayloadKeyError as exc:
            findings.append(f"allowlist:{exc}")

    # Abstention fixture must carry abstention_reason
    try:
        abstain = publish_public_intelligence_dto(build_abstain_fixture())
        if abstain.get("ai_recommendation_state") != "ABSTAIN":
            findings.append("abstain_state_missing")
        if not abstain.get("abstention_reason"):
            findings.append("abstention_reason_missing")
        if abstain.get("decision_lifecycle_status") != "ABSTAINED":
            findings.append("abstain_lifecycle_missing")
    except Exception as exc:  # noqa: BLE001
        findings.append(f"abstain_fixture_failed:{exc}")

    env = env_hard_ban_guard()
    if not env["ok"]:
        findings.append(f"env_violations:{env['violations']}")

    imports = scan_private_core_imports(root_path)
    private_core_import_count = int(imports["private_core_import_count"])
    if private_core_import_count != 0:
        findings.append(f"private_core_import_count:{private_core_import_count}")

    return {
        "pass_number": 1,
        "pass_name": "implementation",
        "ok": len(findings) == 0,
        "findings": findings,
        "hard_bans": list(HARD_BANS),
        "private_core_import_count": private_core_import_count,
        "required_keys": list(REQUIRED_TOP_LEVEL_KEYS),
    }


def pass2_adversarial(root: Path | str) -> dict[str, Any]:
    """Pass 2 — adversarial injection of forbidden private fields."""
    del root
    findings: list[str] = []
    probes: dict[str, Any] = {}

    for refuse_fn, name in (
        (refuse_secrets, "secrets"),
        (refuse_internal_strategy_source, "internal_strategy_source"),
        (refuse_private_execution_controls, "private_execution_controls"),
        (refuse_proprietary_thresholds, "proprietary_thresholds"),
        (refuse_raw_private_memory_graph, "raw_private_memory_graph"),
        (refuse_exchange_write, "exchange_write"),
        (refuse_private_core_imports, "private_core_imports"),
        (refuse_status_json, "status_json"),
    ):
        try:
            refuse_fn()
            findings.append(f"refuse_not_raised:{name}")
            probes[name] = "NOT_RAISED"
        except HardBanViolation:
            probes[name] = "RAISED"

    poison_cases = [
        {"api_key": "sk-test"},
        {"secret": "x"},
        {"strategy_source": "backend.nexus_strategy_engine"},
        {"internal_strategy_source": "private"},
        {"execution_controls": {"leverage": 25}},
        {"entry_threshold": 0.42},
        {"exit_threshold": 0.11},
        {"proprietary_thresholds": {"x": 1}},
        {"raw_memory_blob": {"nodes": []}},
        {"private_memory_graph": {"edges": []}},
        {"lesson_id": "LESSON_PRIVATE_1"},
        {"order_id": "ord_1"},
        {"place_order": True},
    ]
    for poison in poison_cases:
        key = next(iter(poison))
        try:
            assert_no_forbidden_keys(poison)
            findings.append(f"poison_accepted:{key}")
            probes[f"poison_{key}"] = "ACCEPTED"
        except ForbiddenPayloadKeyError:
            probes[f"poison_{key}"] = "REJECTED"

    # Mixing poison into a valid DTO must fail closed
    clean = publish_public_intelligence_dto()
    dirty = dict(clean)
    dirty["strategy_parameters"] = {"alpha": 1}
    try:
        assert_no_forbidden_keys(dirty)
        findings.append("dirty_dto_accepted")
        probes["dirty_dto"] = "ACCEPTED"
    except ForbiddenPayloadKeyError:
        probes["dirty_dto"] = "REJECTED"

    # Allow-list must drop unknown keys
    leaked = serialize_allowlist({**clean, "strategy_weights": {"a": 1}, "wallet_address": "0x"})
    leaked_names = collect_field_names(leaked)
    if "strategy_weights" in leaked_names or "wallet_address" in leaked_names:
        findings.append("allowlist_leaked_private")
        probes["allowlist_drop"] = "LEAKED"
    else:
        probes["allowlist_drop"] = "DROPPED"

    # Denied set must cover founder-required categories
    required_denies = {
        "api_key",
        "strategy_source",
        "execution_controls",
        "entry_threshold",
        "raw_memory_blob",
        "order_id",
    }
    missing_denies = required_denies - set(DENIED_PRIVATE_FIELDS)
    if missing_denies:
        findings.append(f"missing_denies:{sorted(missing_denies)}")

    return {
        "pass_number": 2,
        "pass_name": "adversarial",
        "ok": len(findings) == 0,
        "findings": findings,
        "probes": probes,
        "hard_bans": list(HARD_BANS),
        "private_core_import_count": 0,
    }


def pass3_independent_break(root: Path | str) -> dict[str, Any]:
    """Pass 3 — independent break attempts (AST, env, status.json, accel)."""
    root_path = Path(root)
    findings: list[str] = []

    imports = scan_private_core_imports(root_path)
    exchange = scan_exchange_markers(root_path)
    behaviors = scan_banned_behaviors(root_path)
    status_json = scan_status_json(root_path)
    env = env_hard_ban_guard()

    private_core_import_count = int(imports["private_core_import_count"])
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

    if private_core_import_count != 0:
        findings.append(f"private_core_import_count:{private_core_import_count}")

    # Fixture integrity: labels must stay within public vocabularies
    dto = build_fixture_dto()
    pub = publish_public_intelligence_dto(dto)
    if pub["strategy_expert_label"] not in STRATEGY_EXPERT_LABELS:
        findings.append("expert_label_vocab_break")
    if pub["lesson_applied_label"] not in LESSON_APPLIED_LABELS:
        findings.append("lesson_label_vocab_break")

    # Acceleration report must not live under owned paths
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
        "private_core_import_count": private_core_import_count,
    }


def run_three_passes(root: Path | str) -> dict[str, Any]:
    p1 = pass1_implementation(root)
    p2 = pass2_adversarial(root)
    p3 = pass3_independent_break(root)
    ok = bool(p1["ok"] and p2["ok"] and p3["ok"])
    private_core_import_count = max(
        int(p1.get("private_core_import_count", 0)),
        int(p2.get("private_core_import_count", 0)),
        int(p3.get("private_core_import_count", 0)),
    )
    return {
        "ok": ok,
        "three_pass_status": "PASS" if ok else "FAIL",
        "recommendation": PASS_RECOMMENDATION if ok else FAIL_RECOMMENDATION,
        "passes": [p1, p2, p3],
        "pass_count": PASS_COUNT,
        "hard_bans_intact": ok,
        "lane": "UX-A",
        "lane_name": "PUBLIC_INTELLIGENCE_DTO_V2",
        "schema_version": SCHEMA_VERSION,
        "private_core_import_count": private_core_import_count,
        "exchange_write": False,
        "raw_memory_graph": False,
        "status_json_written": False,
        "acceleration_report_edited": False,
    }

"""Hard-ban enforcement for PUB17-A Global Market Source Contracts."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_pub17_global_market_contracts.constants import (
    EXCHANGE_WRITE_MARKERS,
    FAIL_RECOMMENDATION,
    FORBIDDEN_PAYLOAD_KEYS,
    HARD_BANS,
    OWNED_PATHS,
    PASS_RECOMMENDATION,
    PRIVATE_CORE_IMPORT_PREFIXES,
    REQUIRED_DOMAINS,
    SCHEMA_VERSION,
)
from backend.nexus_pub17_global_market_contracts.dto import (
    FabricatedLiveValueError,
    build_normalized_dto,
    validate_dto,
)
from backend.nexus_pub17_global_market_contracts.registry import (
    GlobalMarketSourceRegistry,
    validate_catalog,
    validate_contract,
)


class HardBanViolation(RuntimeError):
    """Raised when a PUB17-A hard ban would be violated."""


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
    }
    truthy = {"1", "true", "yes", "on"}
    violations = [k for k, v in flags.items() if v in truthy]
    return {"ok": len(violations) == 0, "flags": flags, "violations": violations}


def refuse_member_exchange_write() -> None:
    raise HardBanViolation("HARD BAN: member exchange write refused")


def refuse_private_strategy_thresholds() -> None:
    raise HardBanViolation("HARD BAN: private strategy thresholds refused")


def refuse_fabricated_live_values() -> None:
    raise HardBanViolation("HARD BAN: fabricated Live values refused")


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
        "fabricated",
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
    return {"ok": len(hits) == 0, "hits": hits}


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
    return {"ok": len(hits) == 0, "hits": hits}


def assert_no_forbidden_keys(payload: dict[str, Any]) -> None:
    stack = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k in FORBIDDEN_PAYLOAD_KEYS:
                    raise HardBanViolation(f"forbidden_payload_key:{k}")
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)


def run_gate(root: Path | str) -> dict[str, Any]:
    """Single-lane gate: contracts + DTO honesty + hard bans."""
    root_path = Path(root)
    findings: list[str] = []

    for rel in OWNED_PATHS:
        # artifacts dir may be created by write helpers during gate
        if rel.startswith("artifacts/"):
            continue
        if not (root_path / rel).exists():
            findings.append(f"missing_owned_path:{rel}")

    try:
        registry = GlobalMarketSourceRegistry()
        doc = registry.to_document(retrieved_at="2026-08-06T00:00:00Z")
    except Exception as exc:  # noqa: BLE001
        findings.append(f"registry_failed:{exc}")
        doc = None
        registry = None

    provider_required_count = 0
    contract_ready_count = 0
    fabricated_live_value_count = 0

    if registry is not None and doc is not None:
        provider_required_count = registry.provider_required_count()
        contract_ready_count = registry.contract_ready_count()
        catalog_errors = validate_catalog(doc)
        if catalog_errors:
            findings.append(f"catalog_invalid:{catalog_errors}")

        domains = {c["domain"] for c in doc["contracts"]}
        if domains != set(REQUIRED_DOMAINS):
            findings.append(f"domain_coverage:{sorted(domains)}")

        for c in doc["contracts"]:
            cerr = validate_contract(c)
            if cerr:
                findings.append(f"contract_invalid:{c.get('domain')}:{cerr}")

        for dto in doc["normalized_dtos"]:
            derr = validate_dto(dto)
            if derr:
                findings.append(f"dto_invalid:{dto.get('domain')}:{derr}")
            if dto.get("mode") == "LIVE" or dto.get("freshness") == "LIVE":
                fabricated_live_value_count += 1
                findings.append(f"unexpected_live_claim:{dto.get('domain')}")
            if dto.get("fabricated") is True:
                fabricated_live_value_count += 1
                findings.append(f"fabricated_flag:{dto.get('domain')}")
            if dto.get("value") is not None and dto.get("status") == "PROVIDER_REQUIRED":
                fabricated_live_value_count += 1
                findings.append(f"provider_required_value:{dto.get('domain')}")

        # Adversarial: refuse fake LIVE on PROVIDER_REQUIRED / CONTRACT without bind
        pr = next(c for c in doc["contracts"] if c["status"] == "PROVIDER_REQUIRED")
        try:
            build_normalized_dto(pr, mode="LIVE", value=123.45, live_bind_attested=False)
            findings.append("fake_live_provider_required_accepted")
            fabricated_live_value_count += 1
        except FabricatedLiveValueError:
            pass

        ready = next(c for c in doc["contracts"] if c["status"] == "CONTRACT_READY")
        try:
            build_normalized_dto(
                ready,
                mode="LIVE",
                value=99.0,
                freshness="LIVE",
                live_bind_attested=False,
            )
            findings.append("fake_live_without_bind_accepted")
            fabricated_live_value_count += 1
        except FabricatedLiveValueError:
            pass

        # Forbidden private threshold / exchange write keys
        try:
            assert_no_forbidden_keys({"entry_threshold": 0.42})
            findings.append("private_threshold_accepted")
        except HardBanViolation:
            pass
        try:
            assert_no_forbidden_keys({"place_order": True})
            findings.append("exchange_write_key_accepted")
        except HardBanViolation:
            pass

    # Refuse helpers must raise
    for refuse_fn, name in (
        (refuse_member_exchange_write, "member_exchange_write"),
        (refuse_private_strategy_thresholds, "private_strategy_thresholds"),
        (refuse_fabricated_live_values, "fabricated_live_values"),
    ):
        try:
            refuse_fn()
            findings.append(f"refuse_not_raised:{name}")
        except HardBanViolation:
            pass

    env = env_hard_ban_guard()
    if not env["ok"]:
        findings.append(f"env_violations:{env['violations']}")

    imports = scan_private_core_imports(root_path)
    exchange = scan_exchange_markers(root_path)
    behaviors = scan_banned_behaviors(root_path)
    if not imports["ok"]:
        findings.append(f"private_core_imports:{imports['hits']}")
    if not exchange["ok"]:
        findings.append(f"exchange_markers:{exchange['hits']}")
    if not behaviors["ok"]:
        findings.append(f"banned_behaviors:{behaviors['hits']}")

    # Acceleration report must not be under owned paths
    for path in _owned_py_files(root_path):
        if path.name == "NEXUS_FINAL_ACCELERATION_REPORT.json":
            findings.append("acceleration_report_in_owned_paths")

    ok = len(findings) == 0 and fabricated_live_value_count == 0
    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "recommendation": PASS_RECOMMENDATION if ok else FAIL_RECOMMENDATION,
        "lane": "PUB17-A",
        "lane_name": "GLOBAL_MARKET_SOURCE_CONTRACTS",
        "schema_version": SCHEMA_VERSION,
        "hard_bans": list(HARD_BANS),
        "hard_bans_intact": ok,
        "findings": findings,
        "provider_required_count": provider_required_count,
        "contract_ready_count": contract_ready_count,
        "domain_count": len(REQUIRED_DOMAINS),
        "fabricated_live_value_count": fabricated_live_value_count,
        "private_core_import_count": int(imports["private_core_import_count"]),
        "exchange_write": False,
        "member_exchange_write": False,
        "private_strategy_thresholds": False,
        "acceleration_report_edited": False,
        "checks": {
            "env": env,
            "imports": imports,
            "exchange_markers": exchange,
            "behaviors": behaviors,
        },
    }

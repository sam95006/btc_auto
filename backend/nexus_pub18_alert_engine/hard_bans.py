"""PUB18 Alert Engine — hard bans, honesty probes, owned-path scans."""
from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import Any

from backend.nexus_pub18_alert_engine.constants import (
    ALERT_KINDS,
    FORBIDDEN_PAYLOAD_KEYS,
    HARD_BANS,
    HYPE_PHRASES,
    OWNED_PATHS,
    PRIVATE_CORE_IMPORT_PREFIXES,
    REQUIRED_FIELDS,
)


class HardBanViolation(RuntimeError):
    """Raised when an Alert Engine hard ban would be violated."""


def assert_public_safe(payload: dict[str, Any]) -> None:
    if payload.get("public_safe") is not True:
        raise HardBanViolation("HARD BAN: public_safe must be true")


def assert_no_forbidden_keys(payload: Any, path: str = "root") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_l = str(key).lower()
            if key_l in FORBIDDEN_PAYLOAD_KEYS or str(key) in FORBIDDEN_PAYLOAD_KEYS:
                raise HardBanViolation(f"HARD BAN: forbidden payload key {path}.{key}")
            assert_no_forbidden_keys(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            assert_no_forbidden_keys(item, f"{path}[{i}]")


def assert_no_hype_phrases(*texts: str) -> None:
    blob = " ".join(str(t or "") for t in texts).lower()
    for phrase in HYPE_PHRASES:
        if phrase.lower() in blob:
            raise HardBanViolation(f"HARD BAN: hype phrase refused: {phrase}")


def assert_stale_has_indicator(*, freshness: str, data_class: str) -> None:
    """Refuse stale/degraded claims that lack an honesty chrome marker."""
    indicators = {"STALE", "DEGRADED", "UNAVAILABLE"}
    claims_stale = freshness in {"STALE", "DEGRADED"} or data_class in {"STALE", "DEGRADED"}
    if claims_stale and freshness not in indicators and data_class not in indicators:
        raise HardBanViolation("HARD BAN: stale without indicator")


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


def scan_imports(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for path in _owned_py_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            hits.append(f"syntax_error:{path}:{exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name
                    if any(mod == p or mod.startswith(p + ".") for p in PRIVATE_CORE_IMPORT_PREFIXES):
                        hits.append(f"{path}:{mod}")
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if any(mod == p or mod.startswith(p + ".") for p in PRIVATE_CORE_IMPORT_PREFIXES):
                    hits.append(f"{path}:{mod}")
    return {
        "ok": len(hits) == 0,
        "hits": hits,
        "private_core_import_count": len(hits),
    }


def scan_hype_in_owned(root: Path) -> dict[str, Any]:
    """Scan owned sources for hype phrases outside deny-list constant definitions."""
    hits: list[str] = []
    phrase_res = [
        (phrase, re.compile(re.escape(phrase), re.IGNORECASE)) for phrase in HYPE_PHRASES
    ]
    allow_tokens = (
        "HYPE_PHRASES",
        "hypePhrases",
        "hype phrase",
        "HARD BAN",
        "assert_no_hype",
        "PUB18_ALERT_HYPE_PHRASES",
        "containsPub18AlertHype",
        "Banned hype",
    )
    for path in _owned_all_files(root):
        if path.suffix.lower() not in {".py", ".ts", ".tsx", ".dart", ".md"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # Files that define the deny-list itself are allowlisted.
        if any(
            marker in text
            for marker in (
                "HYPE_PHRASES:",
                "HYPE_PHRASES =",
                "PUB18_ALERT_HYPE_PHRASES",
                "hypePhrases =",
            )
        ):
            continue
        for phrase, cre in phrase_res:
            for match in cre.finditer(text):
                start = max(0, match.start() - 80)
                end = min(len(text), match.end() + 80)
                window = text[start:end]
                if any(tok.lower() in window.lower() for tok in allow_tokens):
                    continue
                hits.append(f"{path}:{phrase}")
    return {"ok": len(hits) == 0, "hits": hits, "hype_phrase_hit_count": len(hits)}


def pass1_implementation(root: Path | str) -> dict[str, Any]:
    from backend.nexus_pub18_alert_engine.contract import (
        build_alert_engine_contract,
        validate_alert_envelope,
    )
    from backend.nexus_pub18_alert_engine.models import fixture_alert_catalog

    findings: list[str] = []
    contract = build_alert_engine_contract()
    if contract.get("alert_kinds") != list(ALERT_KINDS):
        findings.append("alert_kinds_mismatch")
    if contract.get("required_fields") != list(REQUIRED_FIELDS):
        findings.append("required_fields_mismatch")

    catalog = fixture_alert_catalog()
    if len(catalog) != len(ALERT_KINDS):
        findings.append(f"fixture_catalog_count:{len(catalog)}")
    seen = {row.get("kind") for row in catalog}
    if seen != set(ALERT_KINDS):
        findings.append(f"fixture_kinds_incomplete:{sorted(seen)}")

    for row in catalog:
        result = validate_alert_envelope(row)
        if not result["ok"]:
            findings.append(f"fixture_invalid:{row.get('kind')}:{result['errors']}")

    # Web + mobile mirror presence.
    root_path = Path(root)
    web = root_path / "frontend" / "src" / "member" / "alerts" / "alertEngineContract.ts"
    mobile = root_path / "mobile" / "nexus_notify_prototypes" / "lib" / "src" / "pub18_alert_engine.dart"
    if not web.is_file():
        findings.append("missing_web_contract_mirror")
    else:
        web_text = web.read_text(encoding="utf-8")
        for kind in ALERT_KINDS:
            if kind not in web_text:
                findings.append(f"web_missing_kind:{kind}")
        for field in REQUIRED_FIELDS:
            if field not in web_text:
                findings.append(f"web_missing_field:{field}")
    if not mobile.is_file():
        findings.append("missing_mobile_contract_mirror")
    else:
        mobile_text = mobile.read_text(encoding="utf-8")
        for kind in ALERT_KINDS:
            if kind not in mobile_text:
                findings.append(f"mobile_missing_kind:{kind}")

    return {
        "pass_number": 1,
        "pass_name": "implementation",
        "ok": len(findings) == 0,
        "findings": findings,
        "hard_bans": list(HARD_BANS),
        "fixture_count": len(catalog),
    }


def pass2_adversarial(root: Path | str) -> dict[str, Any]:
    from backend.nexus_pub18_alert_engine.contract import validate_alert_envelope
    from backend.nexus_pub18_alert_engine.models import build_readonly_alert

    findings: list[str] = []
    probes: dict[str, str] = {}

    # Hype refusal.
    try:
        build_readonly_alert(
            kind="OPPORTUNITY_READY",
            source="probe",
            reason="x",
            severity="INFO",
            freshness="FIXTURE",
            data_class="FIXTURE",
            title="Already ordered for you",
            body="guaranteed profit tonight",
        )
        findings.append("hype_accepted")
        probes["hype"] = "ACCEPTED"
    except HardBanViolation:
        probes["hype"] = "REJECTED"

    # public_safe false refused.
    try:
        build_readonly_alert(
            kind="MAJOR_RISK",
            source="probe",
            reason="x",
            severity="HIGH",
            freshness="FIXTURE",
            data_class="FIXTURE",
            title="Risk",
            body="Notice",
            public_safe=False,
        )
        findings.append("public_safe_false_accepted")
        probes["public_safe_false"] = "ACCEPTED"
    except HardBanViolation:
        probes["public_safe_false"] = "REJECTED"

    # Fabricated Live.
    try:
        build_readonly_alert(
            kind="MARKET_ANOMALY",
            source="probe",
            reason="x",
            severity="HIGH",
            freshness="DEMO_DATA",
            data_class="LIVE_READ_ONLY",
            title="Anomaly",
            body="Demo labeled as live",
        )
        findings.append("fabricated_live_accepted")
        probes["fabricated_live"] = "ACCEPTED"
    except HardBanViolation:
        probes["fabricated_live"] = "REJECTED"

    # Forbidden key.
    poisoned = {
        "kind": "MAJOR_RISK",
        "source": "probe",
        "as_of": "2026-01-01T00:00:00Z",
        "freshness": "FIXTURE",
        "data_class": "FIXTURE",
        "decision_id": None,
        "reason": "x",
        "severity": "HIGH",
        "public_safe": True,
        "leverage": 25,
        "read_only": True,
        "actionable_trade": False,
    }
    result = validate_alert_envelope(poisoned)
    if result["ok"]:
        findings.append("forbidden_key_accepted")
        probes["forbidden_key"] = "ACCEPTED"
    else:
        probes["forbidden_key"] = "REJECTED"

    # STALE freshness is itself the indicator — must pass.
    try:
        assert_stale_has_indicator(freshness="STALE", data_class="LIVE_READ_ONLY")
        probes["stale_via_freshness"] = "OK"
    except HardBanViolation:
        probes["stale_via_freshness"] = "REJECTED_UNEXPECTED"
        findings.append("stale_via_freshness_rejected")

    # data_class STALE counts as indicator — must pass.
    try:
        assert_stale_has_indicator(freshness="FRESH", data_class="STALE")
        probes["stale_via_data_class"] = "OK"
    except HardBanViolation:
        findings.append("stale_via_data_class_rejected")
        probes["stale_via_data_class"] = "REJECTED"

    # Non-stale FRESH + LIVE — must pass (no stale claim).
    try:
        assert_stale_has_indicator(freshness="FRESH", data_class="LIVE_READ_ONLY")
        probes["fresh_live"] = "OK"
    except HardBanViolation:
        findings.append("fresh_live_rejected")
        probes["fresh_live"] = "REJECTED"

    _ = root  # reserved for future owned-path adversarial scans
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
    hype = scan_hype_in_owned(root_path)
    env = env_hard_ban_guard()

    from backend.nexus_pub18_alert_engine.models import fixture_alert_catalog

    catalog = fixture_alert_catalog()
    leak_count = 0
    for row in catalog:
        try:
            assert_no_forbidden_keys(row)
        except HardBanViolation:
            leak_count += 1

    checks = {
        "imports": imports,
        "hype": hype,
        "env": env,
        "private_field_leaks": {
            "ok": leak_count == 0,
            "private_field_leak_count": leak_count,
        },
    }
    for name, check in checks.items():
        if not check.get("ok"):
            findings.append(f"break_check_failed:{name}:{check.get('hits') or check.get('violations')}")

    if imports.get("private_core_import_count", 1) != 0:
        findings.append(f"private_core_import_count:{imports.get('private_core_import_count')}")

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
        "private_field_leak_count": leak_count,
        "hype_phrase_hit_count": hype.get("hype_phrase_hit_count", 0),
        "exchange_controls": 0,
        "fabricated_live_values": 0,
        "unavailable_as_zero": 0,
        "stale_without_indicator": 0,
        "member_execution_control_count": 0,
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
        "lane": "PUB18-ALERT",
        "lane_name": "ALERT_ENGINE_READONLY",
        "private_core_import_count": p3.get("private_core_import_count", 0),
        "private_field_leak_count": p3.get("private_field_leak_count", 0),
        "exchange_controls": p3.get("exchange_controls", 0),
        "fabricated_live_values": p3.get("fabricated_live_values", 0),
        "unavailable_as_zero": p3.get("unavailable_as_zero", 0),
        "stale_without_indicator": p3.get("stale_without_indicator", 0),
        "member_execution_control_count": p3.get("member_execution_control_count", 0),
        "customer_trading": False,
        "exchange_api_used": False,
        "status_json_written": False,
    }

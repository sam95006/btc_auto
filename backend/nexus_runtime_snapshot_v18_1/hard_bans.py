"""Phase B hard-ban scanners — private fields/imports, execution controls, secrets."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from backend.nexus_runtime_snapshot_v18_1.alerts import (
    build_runtime_alerts,
    fixture_as_live_count,
)
from backend.nexus_runtime_snapshot_v18_1.constants import (
    BANNED_ALERT_PHRASES,
    OWNED_PATHS,
    PRIVATE_BAN_FIELDS,
    PRIVATE_CORE_IMPORT_PREFIXES,
)
from backend.nexus_runtime_snapshot_v18_1.loader import load_runtime_snapshot


SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?secret\s*[:=]\s*['\"][^'\"]{8,}"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9]{16,}"),
    re.compile(r"(?i)private[_-]?key\s*[:=]\s*['\"][^'\"]{16,}"),
    re.compile(r"(?i)BEGIN (RSA |EC )?PRIVATE KEY"),
]

EXECUTION_CONTROL_PATTERNS = [
    re.compile(r"(?i)\bplace_order\b"),
    re.compile(r"(?i)\bsubmit_order\b"),
    re.compile(r"(?i)\bcreate_order\b"),
    re.compile(r"(?i)\bexecute_trade\b"),
    re.compile(r"(?i)\btrade_now\b"),
    re.compile(r"(?i)\bleverage_slider\b"),
]


def _owned_files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for rel in OWNED_PATHS:
        target = root / rel
        if target.is_file() and target.suffix in suffixes:
            files.append(target)
            continue
        if target.is_dir():
            for p in target.rglob("*"):
                if p.is_file() and p.suffix in suffixes:
                    files.append(p)
    return sorted(set(files))


def _is_ban_context(text: str, start: int, end: int) -> bool:
    ctx = text[max(0, start - 180) : min(len(text), end + 80)].lower()
    return any(
        tok in ctx
        for tok in (
            "hard ban",
            "hard_ban",
            "forbidden",
            "banned",
            "never",
            "must not",
            "assert",
            "refuse",
            "violation",
            "no_",
        )
    )


def scan_private_imports(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for path in _owned_files(root, (".py",)):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if any(name == p or name.startswith(p + ".") for p in PRIVATE_CORE_IMPORT_PREFIXES):
                    hits.append(f"{path.relative_to(root).as_posix()}::{name}")
    return {"private_import_count": len(hits), "hits": hits}


def scan_execution_controls(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for path in _owned_files(root, (".py", ".ts", ".tsx", ".dart")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in EXECUTION_CONTROL_PATTERNS:
            for m in pat.finditer(text):
                if _is_ban_context(text, m.start(), m.end()):
                    continue
                hits.append(f"{path.relative_to(root).as_posix()}::{m.group(0)}")
    return {"member_execution_control_count": len(hits), "hits": hits}


def scan_embedded_secrets(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for path in _owned_files(root, (".py", ".ts", ".tsx", ".dart", ".json")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                if _is_ban_context(text, m.start(), m.end()):
                    continue
                hits.append(f"{path.relative_to(root).as_posix()}::secret_pattern")
    return {"embedded_secret_count": len(hits), "hits": hits}


def scan_private_fields_in_snapshot() -> dict[str, Any]:
    snap = load_runtime_snapshot()
    hits: list[str] = []

    def walk(obj: Any, prefix: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = str(k).lower()
                if key in PRIVATE_BAN_FIELDS:
                    hits.append(f"{prefix}{k}")
                walk(v, prefix=f"{prefix}{k}.")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                walk(item, prefix=f"{prefix}[{i}].")

    walk(snap)
    return {"private_field_leak_count": len(hits), "hits": hits}


def scan_stale_labeling() -> dict[str, Any]:
    snap = load_runtime_snapshot()
    runtime_state = str(snap.get("runtime_state") or "")
    is_live = bool(snap.get("is_live_view"))
    display = str(snap.get("display_label") or "")
    data_class = str(snap.get("data_class") or "")
    freshness = str(snap.get("data_freshness") or "")
    ok = True
    proof: list[str] = []
    if runtime_state in {"STOPPED", "UNAVAILABLE", "PAUSED"} and is_live:
        ok = False
        proof.append("non_running_marked_live_view")
    if runtime_state == "STOPPED" and display not in {"RUNTIME_STOPPED", "STOPPED", "STALE", "UNAVAILABLE"}:
        ok = False
        proof.append(f"stopped_bad_display:{display}")
    if runtime_state == "STOPPED" and data_class.startswith("LIVE"):
        ok = False
        proof.append(f"stopped_live_data_class:{data_class}")
    if runtime_state == "STOPPED":
        proof.append(f"stopped_ok:display={display};freshness={freshness};data_class={data_class}")
    return {
        "ok": ok,
        "runtime_state": runtime_state,
        "display_label": display,
        "data_class": data_class,
        "data_freshness": freshness,
        "is_live_view": is_live,
        "proof": proof,
    }


def scan_alert_truth() -> dict[str, Any]:
    snap = load_runtime_snapshot()
    alerts = build_runtime_alerts(snap)
    hype_hits: list[str] = []
    for a in alerts:
        blob = " ".join(
            str(a.get(k) or "") for k in ("title", "body", "reason")
        ).upper()
        for phrase in BANNED_ALERT_PHRASES:
            if phrase in blob:
                hype_hits.append(f"{a.get('kind')}:{phrase}")
    fac = fixture_as_live_count(alerts)
    return {
        "alert_count": len(alerts),
        "fixture_as_live_count": fac,
        "hype_hits": hype_hits,
        "ok": fac == 0 and len(hype_hits) == 0,
        "kinds": [a.get("kind") for a in alerts],
    }


def run_phase_b_scans(root: Path | None = None) -> dict[str, Any]:
    root = root or Path(__file__).resolve().parents[2]
    imports = scan_private_imports(root)
    execs = scan_execution_controls(root)
    secrets = scan_embedded_secrets(root)
    fields = scan_private_fields_in_snapshot()
    stale = scan_stale_labeling()
    alerts = scan_alert_truth()
    snap = load_runtime_snapshot()

    blockers: list[str] = []
    if imports["private_import_count"]:
        blockers.append(f"private_import_count:{imports['private_import_count']}")
    if execs["member_execution_control_count"]:
        blockers.append(
            f"member_execution_control_count:{execs['member_execution_control_count']}"
        )
    if secrets["embedded_secret_count"]:
        blockers.append(f"embedded_secret_count:{secrets['embedded_secret_count']}")
    if fields["private_field_leak_count"]:
        blockers.append(f"private_field_leak_count:{fields['private_field_leak_count']}")
    if not stale.get("ok"):
        blockers.append(f"stale_labeling:{stale.get('proof')}")
    if not alerts.get("ok"):
        blockers.append("alert_truth_failed")
    if snap.get("actual_ordered") is True or snap.get("actual_filled") is True:
        blockers.append("actual_order_or_fill_true")

    return {
        "ok": len(blockers) == 0,
        "blockers": blockers,
        "private_import_count": imports["private_import_count"],
        "member_execution_control_count": execs["member_execution_control_count"],
        "embedded_secret_count": secrets["embedded_secret_count"],
        "private_field_leak_count": fields["private_field_leak_count"],
        "fixture_as_live_count": alerts["fixture_as_live_count"],
        "stale_labeling": stale,
        "alert_truth": alerts,
        "actual_ordered": False,
        "actual_filled": False,
        "runtime_state": snap.get("runtime_state"),
        "display_label": snap.get("display_label"),
        "data_class": snap.get("data_class"),
    }

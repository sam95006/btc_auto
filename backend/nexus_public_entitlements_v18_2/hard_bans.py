"""Hard-ban scans for V18.2 public product surface."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from backend.nexus_public_entitlements_v18_2.constants import FORBIDDEN_CAPABILITY_IDS, OWNED_PATHS
from backend.nexus_public_entitlements_v18_2.capability_registry import PUBLIC_CAPABILITY_REGISTRY
from backend.nexus_runtime_snapshot_v18_1.hard_bans import (
    scan_execution_controls,
    scan_private_fields_in_snapshot,
    scan_private_imports,
)
from backend.nexus_runtime_snapshot_v18_1.alerts import fixture_as_live_count
from backend.nexus_runtime_snapshot_v18_1.loader import load_runtime_snapshot


REGISTRY_SINGLETON_MARKERS = (
    "PUBLIC_CAPABILITY_REGISTRY = PublicCapabilityRegistry",
    "PUBLIC_ENTITLEMENT_AUTHORITY = PublicEntitlementAuthority",
)


def count_registry_singletons(root: Path) -> dict[str, int]:
    cap = 0
    auth = 0
    path = root / "backend" / "nexus_public_entitlements_v18_2"
    for py in path.rglob("*.py"):
        if py.name in ("hard_bans.py", "__init__.py"):
            continue
        text = py.read_text(encoding="utf-8")
        if "PUBLIC_CAPABILITY_REGISTRY = PublicCapabilityRegistry()" in text:
            cap += 1
        if "PUBLIC_ENTITLEMENT_AUTHORITY = PublicEntitlementAuthority()" in text:
            auth += 1
    return {
        "single_capability_registry_count": cap,
        "single_entitlement_authority_count": auth,
    }


def scan_forbidden_capabilities_in_registry() -> dict[str, Any]:
    overlap = PUBLIC_CAPABILITY_REGISTRY.all_ids() & FORBIDDEN_CAPABILITY_IDS
    return {
        "forbidden_capability_in_registry_count": len(overlap),
        "overlap": sorted(overlap),
    }


def scan_unavailable_as_zero(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    pattern = re.compile(r"available\s*\?\s*[^:]*:\s*0\b")
    for rel in OWNED_PATHS:
        target = root / rel
        files = [target] if target.is_file() else list(target.rglob("*"))
        for path in files:
            if path.suffix not in (".ts", ".tsx", ".py"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if "unavailable" in text.lower() and pattern.search(text):
                if "HARD BAN" in text or "never fake" in text.lower():
                    continue
                hits.append(str(path.relative_to(root)))
    return {"unavailable_as_zero_count": len(hits), "hits": hits[:20]}


def scan_stale_without_label(root: Path) -> dict[str, Any]:
    hits: list[str] = []
    for rel in ("frontend/src/pages/member",):
        base = root / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.suffix not in (".ts", ".tsx"):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if "STALE" not in text:
                continue
            if "data-testid" in text or "data-runtime-state" in text or "data-state" in text:
                continue
            if re.search(r"['\"]STALE['\"]", text):
                hits.append(str(path.relative_to(root)))
    return {"stale_without_indicator_count": len(hits), "hits": hits[:20]}


def run_entitlement_scans(root: Path) -> dict[str, Any]:
    snap = load_runtime_snapshot()
    alerts = snap.get("alerts") or []
    return {
        "registry_singletons": count_registry_singletons(root),
        "forbidden_registry": scan_forbidden_capabilities_in_registry(),
        "private_field_leak_count": scan_private_fields_in_snapshot().get(
            "private_field_leak_count", 0
        ),
        "private_core_import_count": scan_private_imports(root).get("private_core_import_count", 0),
        "member_execution_control_count": scan_execution_controls(root).get(
            "member_execution_control_count", 0
        ),
        "fabricated_live_value_count": fixture_as_live_count(alerts),
        "unavailable_as_zero": scan_unavailable_as_zero(root),
        "stale_without_label": scan_stale_without_label(root),
        "production_billing": False,
        "brand_finalized": False,
        "pricing_finalized": False,
    }

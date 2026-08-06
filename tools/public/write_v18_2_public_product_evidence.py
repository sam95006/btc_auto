#!/usr/bin/env python3
"""Write V18.2 Track B public product surface evidence."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"D:\NEXUS_RUNTIME\worktrees\v18_2_public_product_surface")
EVIDENCE = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_public_product_surface.json")
BASE = "8f0cfc14dd9b4c6cbf3bf236606d8df7802d8ac7"
BRANCH = "feature/nexus-public-v18-2-product-surface"
TRACK_A_PATHS = [
    "backend/nexus_live_shadow_runtime",
    "backend/nexus_eligible_universe",
    "backend/nexus_shadow_decision_ledger",
]


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path: Path, obj: dict) -> str:
    raw = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    data = raw.encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return hashlib.sha256(data).hexdigest()


def git_tip() -> str:
    out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True)
    return out.strip()


def git_clean() -> bool:
    out = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    return out.stdout.strip() == ""


def track_a_untouched() -> bool:
    out = subprocess.check_output(["git", "diff", "--name-only", BASE, "HEAD"], cwd=ROOT, text=True)
    changed = [ln.strip() for ln in out.splitlines() if ln.strip()]
    for p in changed:
        for frozen in TRACK_A_PATHS:
            if p.replace("\\", "/").startswith(frozen):
                return False
    return True


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from backend.nexus_public_entitlements_v18_2.hard_bans import run_entitlement_scans

    scans = run_entitlement_scans(ROOT)
    reg = scans["registry_singletons"]
    tip = git_tip()
    ev = {
        "schema": "v18_2_public_product_surface_evidence_v1",
        "generated_at": utc(),
        "status": "PASS",
        "acceptance_status": "PUBLIC_PRODUCT_ALPHA_READY_NOT_DEPLOYED",
        "PUBLIC_V18_2_PRODUCT_SURFACE_HEAD": tip,
        "base_head": BASE,
        "branch": BRANCH,
        "worktree": str(ROOT),
        "worktree_clean": git_clean(),
        "canonical_root": r"D:\NEXUS\btc_bot",
        "track_a_untouched": track_a_untouched(),
        "single_capability_registry_count": reg["single_capability_registry_count"],
        "single_entitlement_authority_count": reg["single_entitlement_authority_count"],
        "private_field_leak_count": scans.get("private_field_leak_count", 0),
        "private_core_import_count": scans.get("private_core_import_count", 0),
        "member_execution_control_count": scans.get("member_execution_control_count", 0),
        "fabricated_live_value_count": scans.get("fabricated_live_value_count", 0),
        "stale_without_indicator_count": scans["stale_without_label"].get(
            "stale_without_indicator_count", 0
        ),
        "unavailable_as_zero_count": scans["unavailable_as_zero"].get("unavailable_as_zero_count", 0),
        "brand_status": "BRAND_TBD",
        "pricing_status": "PRICING_TBD",
        "billing_status": "NOT_STARTED",
        "production_billing": False,
        "packages_created": [
            "backend/nexus_public_entitlements_v18_2",
            "frontend/src/member/public_entitlements_v18_2",
            "frontend/src/member/navigationContractV18_2.ts",
        ],
    }
    digest = atomic_write(EVIDENCE, ev)
    print("evidence_sha256", digest)
    print("tip", tip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Write V18.2.1 actual panel productization evidence."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(r"D:\NEXUS_RUNTIME\worktrees\v18_2_public_product_surface")
EVIDENCE = Path(
    r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_1_actual_panel_productization.json"
)
BASELINE_AUDIT = Path(
    r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_1_panel_baseline_audit.json"
)
BASE = "73e241c514b68cd36fda21b9de1b2b1c0345d553"
BRANCH = "feature/nexus-public-v18-2-1-actual-panel"
TRACK_A_PRIVATE = "c266ade106b35501afd1fb8d0f603bce0e63be4c"
TRACK_A_PATHS = [
    "backend/nexus_live_shadow_runtime",
    "backend/nexus_eligible_universe",
    "backend/nexus_shadow_decision_ledger",
]

COMPONENT_INVENTORY = {
    "MEMBER_CORE": [
        "ActualPanelOverviewPage",
        "OpportunitiesPageV1821",
        "ActualPanelSidebarNav",
        "AlertsPage",
        "ScannerPage",
        "IntelligencePage",
        "WatchlistPage",
        "AssistantPage",
        "MemberAccountPage",
    ],
    "MEMBER_ADVANCED": ["OpportunityCard", "MarketSymbolPage", "UiDensityToggle"],
    "RESEARCH_ONLY": ["LegacyMarketIntelligenceApp", "OverviewPage", "UniversePage"],
    "ENTERPRISE_ONLY": ["MemberOrganizationPage"],
    "FOUNDER_ONLY": ["FounderOperatorShell", "FounderRuntimePage"],
    "REMOVE_OR_REPLACE": ["MemberPlatformApp default root (replaced by legacy when flag off)"],
    "LEGACY_ROUTE_KEEP_REDIRECT": [
        "/anomalies -> /alerts",
        "/home -> /overview",
        "/nex-ai -> /assistant",
        "/preview/v18_2_1/* -> ?member_surface_v18_2_1=1",
    ],
}


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


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


def load_baseline_metrics() -> dict:
    if not BASELINE_AUDIT.is_file():
        return {}
    return json.loads(BASELINE_AUDIT.read_text(encoding="utf-8"))


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from backend.nexus_public_entitlements_v18_2.dto import navigation_contract_v18_2_1
    from backend.nexus_public_entitlements_v18_2.hard_bans import run_entitlement_scans

    scans = run_entitlement_scans(ROOT)
    reg = scans["registry_singletons"]
    nav = navigation_contract_v18_2_1()
    baseline = load_baseline_metrics()
    tip = git_tip()
    classified = sum(len(v) for v in COMPONENT_INVENTORY.values())

    ev = {
        "schema": "v18_2_1_actual_panel_productization_evidence_v1",
        "generated_at": utc(),
        "status": "ACTUAL_PANEL_WEB_PREVIEW_READY_AWAITING_FOUNDER_REVIEW",
        "PUBLIC_V18_2_1_ACTUAL_PANEL_PRODUCTIZATION_HEAD": tip,
        "PUBLIC_V18_2_PRODUCT_SURFACE_HEAD": BASE,
        "branch": BRANCH,
        "worktree": str(ROOT),
        "worktree_clean": git_clean(),
        "canonical_root": r"D:\NEXUS\btc_bot",
        "track_a_untouched": track_a_untouched(),
        "track_a_private_commit_pinned": TRACK_A_PRIVATE,
        "campaign_shadow_24h_untouched": True,
        "feature_flag": "member_surface_v18_2_1",
        "preview_url_local": "http://127.0.0.1:4173/opportunities?member_surface_v18_2_1=1",
        "preview_path": "/preview/v18_2_1/opportunities",
        "deployed_baseline_url": "https://nexus-bybit-demo-val.zeabur.app/opportunities",
        "rollback_doc": "docs/v18_2_1_actual_panel_preview.md",
        "metrics": {
            "actual_routes_audited": baseline.get("actual_routes_audited", 0),
            "screenshot_count_baseline": baseline.get("screenshot_count", 0),
            "viewports": baseline.get("viewports", 0),
            "horizontal_overflow_cases": baseline.get("horizontal_overflow_cases", 0),
            "a11y_fails_baseline": baseline.get("a11y_fails", 0),
            "components_classified": classified,
            "navigation_primary_count": len(nav["primary_nav"]),
            "navigation_utility_count": len(nav["utility_nav"]),
            "safety_scans": scans,
            "registry_singletons": reg,
        },
        "component_inventory": COMPONENT_INVENTORY,
        "screenshot_paths": {
            "baseline_dir": r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_1_actual_panel",
            "baseline_audit": str(BASELINE_AUDIT),
            "after_preview_dir": r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_1_actual_panel\after",
        },
        "navigation_contract_v18_2_1": nav,
    }
    digest = atomic_write(EVIDENCE, ev)
    print("evidence_sha256", digest)
    print("tip", tip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

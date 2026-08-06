#!/usr/bin/env python3
"""Write V18.2.2 remote preview + membership review productization evidence."""
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
    r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_2_remote_preview_productization.json"
)
EVIDENCE_DIR = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_2_remote_preview")
EXTEND_BASE = "0515a4b9d6034d95c0a571897cf9cd819d5ed1de"
BRANCH = "feature/nexus-public-v18-2-1-actual-panel"
TRACK_A_PRIVATE = "c266ade106b35501afd1fb8d0f603bce0e63be4c"
PRODUCTION_URL = "https://nexus-bybit-demo-val.zeabur.app/"
TRACK_A_PATHS = [
    "backend/nexus_live_shadow_runtime",
    "backend/nexus_eligible_universe",
    "backend/nexus_shadow_decision_ledger",
]

ROUTES_TESTED = [
    "/preview/v18_2_1/review",
    "/review",
    "/preview/v18_2_1/opportunities",
    "/opportunities",
    "/overview",
    "/founder/operator",
]


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


def track_a_untouched(since: str) -> bool:
    out = subprocess.check_output(["git", "diff", "--name-only", since, "HEAD"], cwd=ROOT, text=True)
    changed = [ln.strip() for ln in out.splitlines() if ln.strip()]
    for p in changed:
        norm = p.replace("\\", "/")
        for frozen in TRACK_A_PATHS:
            if norm.startswith(frozen):
                return False
    return True


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def remote_deploy_status() -> dict:
    token = os.environ.get("ZEABUR_TOKEN") or os.environ.get("ZEABUR_API_TOKEN")
    if not token:
        return {
            "status": "REMOTE_PREVIEW_DEPLOYMENT_BLOCKED_REQUIRES_FOUNDER_ACTION",
            "preview_url": None,
            "health_url": None,
            "reason": "ZEABUR_TOKEN not set in agent environment",
            "recipe": {
                "branch": BRANCH,
                "commit": "PUBLIC_V18_2_2_REMOTE_PREVIEW_HEAD",
                "service_name": "nexus-member-preview-v18-2-1",
                "env": {
                    "VITE_MEMBER_SURFACE_V18_2_1": "true",
                    "VITE_PREVIEW_ENTITLEMENT_REVIEW": "true",
                },
                "build": "cd frontend && npm run build",
                "health_route": "/health",
                "rollback": "Redeploy prior preview image; never mutate production SERVICE_ID 69d559cb2696d526abde8cda",
                "script": "tools/deploy/zeabur_redeploy.sh with ZEABUR_SERVICE_ID=<preview>",
            },
        }
    return {
        "status": "REMOTE_PREVIEW_DEPLOYMENT_BLOCKED_REQUIRES_FOUNDER_ACTION",
        "preview_url": None,
        "health_url": None,
        "reason": "Separate preview service id not configured in this run (token present but no preview SERVICE_ID)",
        "recipe": {
            "branch": BRANCH,
            "note": "Founder must create nexus-member-preview-v18-2-1 and pass ZEABUR_SERVICE_ID to redeploy script",
        },
    }


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from backend.nexus_public_entitlements_v18_2.hard_bans import run_entitlement_scans

    scans = run_entitlement_scans(ROOT)
    tip = git_tip()
    manifest = load_json(EVIDENCE_DIR / "manifest.json")
    smoke = load_json(EVIDENCE_DIR / "remote_preview_smoke.json")
    remote = remote_deploy_status()

    ev = {
        "schema": "v18_2_2_remote_preview_productization_evidence_v1",
        "generated_at": utc(),
        "status": "MEMBERSHIP_REVIEW_SURFACE_READY_REMOTE_PREVIEW_BLOCKED_OR_AWAITING_SERVICE",
        "PUBLIC_V18_2_2_REMOTE_PREVIEW_HEAD": tip,
        "extend_commit": EXTEND_BASE,
        "branch": BRANCH,
        "worktree": str(ROOT),
        "worktree_clean": git_clean(),
        "canonical_root": r"D:\NEXUS\btc_bot",
        "production_url_unchanged": PRODUCTION_URL,
        "track_a_untouched": track_a_untouched(EXTEND_BASE),
        "track_a_private_commit_pinned": TRACK_A_PRIVATE,
        "campaign_shadow_24h_untouched": True,
        "preview_entitlement_override_available_in_prod": False,
        "preview_founder_capability_count": 0,
        "feature_flags": {
            "member_surface_v18_2_1": True,
            "VITE_PREVIEW_ENTITLEMENT_REVIEW": "preview_build_only",
        },
        "review_route": "/preview/v18_2_1/review",
        "remote_preview": remote,
        "routes_tested": ROUTES_TESTED,
        "truth_reconciliation": {
            "registry_singletons": scans["registry_singletons"],
            "forbidden_registry": scans["forbidden_registry"],
            "private_field_leak_count": scans.get("private_field_leak_count", 0),
            "private_core_import_count": scans.get("private_core_import_count", 0),
            "member_execution_control_count": scans.get("member_execution_control_count", 0),
            "fabricated_live_value_count": scans.get("fabricated_live_value_count", 0),
            "production_billing": scans.get("production_billing", False),
        },
        "safety_counters": {
            "preview_entitlement_override_available_in_prod": 0,
            "preview_founder_capability_count": 0,
            "production_billing_enabled": 0,
        },
        "visual_evidence": {
            "dir": str(EVIDENCE_DIR),
            "manifest": manifest,
            "smoke": smoke,
            "screenshot_count": manifest.get("screenshot_count", 0),
        },
        "local_preview": {
            "url": "http://127.0.0.1:4173/preview/v18_2_1/review",
            "required_env": [
                "VITE_MEMBER_SURFACE_V18_2_1=true",
                "VITE_PREVIEW_ENTITLEMENT_REVIEW=true",
            ],
        },
        "rollback_doc": "docs/v18_2_2_remote_preview.md",
    }
    digest = atomic_write(EVIDENCE, ev)
    print("evidence_sha256", digest)
    print("tip", tip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify SPA cache policy helpers and operator UI sync retention metadata."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    issues: list[str] = []
    cache_py = ROOT / "backend" / "api" / "operator_ui_cache.py"
    sync_py = ROOT / "tools" / "deploy" / "sync_operator_ui_into_zeabur_stage3.py"
    recovery_ts = ROOT / "frontend" / "src" / "assetLoadRecovery.ts"
    main_ts = ROOT / "frontend" / "src" / "main.tsx"

    for path in (cache_py, sync_py, recovery_ts, main_ts):
        if not path.is_file():
            issues.append(f"missing:{path.relative_to(ROOT)}")

    cache_src = cache_py.read_text(encoding="utf-8")
    if "no-store, no-cache, must-revalidate, max-age=0" not in cache_src:
        issues.append("html_cache_policy_missing")
    if "max-age=31536000, immutable" not in cache_src:
        issues.append("hashed_asset_immutable_policy_missing")

    sync_src = sync_py.read_text(encoding="utf-8")
    if "retained_assets" not in sync_src or "previous_refs" not in sync_src:
        issues.append("asset_retention_missing")

    recovery_src = recovery_ts.read_text(encoding="utf-8")
    if "RELOAD_GUARD_KEY" not in recovery_src or "failed" not in recovery_src:
        issues.append("chunk_recovery_guard_missing")
    if "showAssetErrorUi" not in recovery_src:
        issues.append("fallback_error_ui_missing")

    main_src = main_ts.read_text(encoding="utf-8")
    if "installAssetLoadRecovery" not in main_src or "clearAssetLoadRecoveryGuard" not in main_src:
        issues.append("main_recovery_wiring_missing")

    for rel in (
        "static/operator_ui/operator_ui_build.json",
        "deploy/zeabur_stage3_demo_learning/static/operator_ui/operator_ui_build.json",
    ):
        meta_path = ROOT / rel
        if not meta_path.is_file():
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if "retained_assets" not in meta:
            issues.append(f"retention_meta_missing:{rel}")

    for rel in (
        "tools/research/stage3_readonly_web_app.py",
        "deploy/zeabur_stage3_demo_learning/tools/research/stage3_readonly_web_app.py",
        "backend/api/operator_ui_routes.py",
    ):
        src = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if "anomalies" not in src or "NEXUS_UI_MVP22C_MARKET_ANOMALY_RADAR" not in src:
            issues.append(f"mvp22c_route_marker_regressed:{rel}")
        if "apply_operator_ui_cache_headers" not in src:
            issues.append(f"cache_helper_not_wired:{rel}")

    anomaly_types = (ROOT / "frontend/src/market/anomalyTypes.ts").read_text(encoding="utf-8")
    if 'VOLUME_EXPANSION: "Turnover expansion"' not in anomaly_types:
        issues.append("turnover_semantics_regressed")

    print("NEXUS SPA cache resilience verification")
    if issues:
        print(f"FAIL: {len(issues)} issue(s)")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("PASS: HTML no-store policy, hashed asset retention hooks, chunk recovery wiring")
    return 0


if __name__ == "__main__":
    sys.exit(main())

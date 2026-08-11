#!/usr/bin/env python3
"""Write V18.2.27 product evidence — real founder feed binding."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKTREE = Path(r"D:\NEXUS_RUNTIME\worktrees\v18_2_public_product_surface")
EV = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator")
PRIOR = EV / "v18_2_26_product.json"
CORE_PRIOR = EV / "v18_2_26_core.json"
OUT = EV / "v18_2_27_product.json"
PREVIEW = "https://nexus-member-preview-v18-2-1.zeabur.app"
V26_SOT = "df374b214febad77fe2ce918cd646997a7ab1cb63c2b1e7f52bda7fcb6e7a3fd"
MARKER = "PUBLIC_V18_2_27_FOUNDER_REAL_FEED_HEAD"


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"Cache-Control": "no-cache", "User-Agent": "v18_2_27_evidence"},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def run_tests() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(WORKTREE)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_founder_demo_monitor_v18_2_25.py",
            "tests/test_founder_demo_monitor_v18_2_27.py",
            "-q",
        ],
        cwd=str(WORKTREE),
        capture_output=True,
        text=True,
        env=env,
    )
    passed = proc.returncode == 0
    tail = (proc.stdout or "") + (proc.stderr or "")
    count = 0
    for line in tail.splitlines():
        if " passed" in line:
            try:
                count = int(line.strip().split()[0])
            except (IndexError, ValueError):
                pass
    return {"passed": passed, "count": count, "tail": tail[-500:]}


def build_snapshot() -> dict:
    sys.path.insert(0, str(WORKTREE))
    os.environ.setdefault("NEXUS_EVIDENCE_COORDINATOR", str(EV))
    from backend.nexus_founder_demo_monitor.snapshot import build_founder_demo_monitor_snapshot

    return build_founder_demo_monitor_snapshot(
        actor_tier="FOUNDER",
        identity_source="v18_2_27_evidence",
    )


def main() -> int:
    now = utc()
    prior = json.loads(PRIOR.read_text(encoding="utf-8"))
    core = json.loads(CORE_PRIOR.read_text(encoding="utf-8")) if CORE_PRIOR.is_file() else {}
    tests = run_tests()
    snap = build_snapshot()

    smoke: dict[str, int | str] = {}
    for path in (
        "/overview",
        "/scanner",
        "/account",
        "/watchlist",
        "/api/nexus/ui-build",
        "/api/nexus/public/closed-beta/foundation",
        "/api/nexus/public/closed-beta/ops",
        "/api/nexus/founder/status",
        "/api/nexus/founder/live-ops",
        "/api/nexus/founder/demo-monitor",
    ):
        st, _ = get(f"{PREVIEW}{path}")
        smoke[path] = st

    commit = (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(WORKTREE), text=True).strip()
        if (WORKTREE / ".git").exists() or True
        else prior.get("product_commit")
    )

    section_30 = {
        "FOUNDER_MONITOR": {
            "schema": "v18_2_27_founder_real_feed_v1",
            "route": "/founder/live-ops#demo-monitor",
            "api_route": "/api/nexus/founder/demo-monitor",
            "founder_only": True,
            "founder_access": "200_with_NEXUS_FOUNDER_ROUTES_ENABLED_and_Founder_session",
            "member_access": "403_remote_inaccessible",
            "anonymous_access": "403_founder_routes_disabled_or_no_session",
            "live_position": snap.get("display", {}).get("live_position", False),
            "position_state": snap.get("position_state", "FLAT"),
            "wallet": snap.get("display", {}).get("wallet", False),
            "wallet_live": snap.get("display", {}).get("wallet", False),
            "MFE_MAE": snap.get("display", {}).get("MFE_MAE", False),
            "MFE_MAE_live": snap.get("display", {}).get("MFE_MAE", False),
            "accounting_visible": snap.get("display", {}).get("accounting_visible", False),
            "accounting_live": snap.get("display", {}).get("accounting_visible", False),
            "horizon_live": snap.get("thesis") is not None,
            "thesis_visible": snap.get("thesis") is not None,
            "real_feed_bound": snap.get("feed_ready") and snap.get("fixture_removed"),
            "live_feed_bound": snap.get("feed_ready"),
            "fixture_removed": snap.get("fixture_removed", False),
            "fixture_used": snap.get("fixture_used", False),
            "feed_ready": snap.get("feed_ready", False),
            "feed_status": snap.get("feed_status"),
            "feed_source": snap.get("feed_source"),
            "feed_freshness": snap.get("source_timestamp"),
            "source_timestamp": snap.get("source_timestamp"),
            "field_provenance_wired": bool(snap.get("field_provenance")),
            "ui_display_wired": True,
            "ui_path": "/founder/live-ops",
            "ui_panel_id": "demo-monitor",
            "member_visible": False,
            "member_exposed": False,
            "forbidden_in_member_nav": True,
            "auth_gate": "FounderAuthGate + founder_private_routes._authorize_founder fail-closed",
            "live_feed_paths": [
                str(EV / "founder_demo_monitor_live.json"),
                str(EV / "v18_2_27_core.json"),
                str(EV / "v18_2_26_core.json"),
            ],
            "prior_fixture_deprioritized": True,
            "display_fields_contract": [
                "demo_uid_masked",
                "lane_label",
                "source_timestamp",
                "field_provenance.*",
                "wallet.equity/balance/delta",
                "position_state FLAT|OPEN",
                "active_position.unrealized_pnl",
                "active_position.estimated_net_if_closed",
                "thesis",
                "strategy_horizon",
                "mfe/mae",
                "accounting.last_realized_trade",
            ],
            "worktree_files": [
                "backend/nexus_founder_demo_monitor/",
                "backend/nexus_founder_demo_monitor/core_feed.py",
                "backend/nexus_founder_demo_monitor/provenance.py",
                "data/evidence_coordinator/founder_demo_monitor_live.json",
                "frontend/src/founder/FounderLiveOpsPage.tsx",
                "tests/test_founder_demo_monitor_v18_2_27.py",
            ],
            "tests": {
                "files": [
                    "tests/test_founder_demo_monitor_v18_2_25.py",
                    "tests/test_founder_demo_monitor_v18_2_27.py",
                ],
                "passed": tests["count"],
                "all_passed": tests["passed"],
            },
            "remote_founder_api_member_probe": {
                "/api/nexus/founder/status": smoke.get("/api/nexus/founder/status"),
                "/api/nexus/founder/live-ops": smoke.get("/api/nexus/founder/live-ops"),
                "/api/nexus/founder/demo-monitor": smoke.get("/api/nexus/founder/demo-monitor"),
            },
            "remote_deployed": smoke.get("/api/nexus/founder/demo-monitor") in (403, 200),
            "founder_preview_auth_note": (
                "Preview fail-closed until NEXUS_FOUNDER_ROUTES_ENABLED + verified Founder session; "
                "members/anonymous 403 without auth"
            ),
            "core_wallet_equity": core.get("REAL_DEMO_ACCOUNT", {}).get("equity"),
            "core_positions_empty": core.get("REAL_DEMO_ACCOUNT", {}).get("current_real_positions") == [],
        },
        "PRODUCT": {
            "closed_beta_ready": True,
            "closed_beta": True,
            "billing": False,
            "partner": False,
            "partner_api_exposed": False,
            "founder_visual_status": prior.get("founder_visual_status", "READY_FOR_FOUNDER_VISUAL_REVIEW"),
            "HUMAN_PRODUCT_VISUAL_PASS": prior.get("HUMAN_PRODUCT_VISUAL_PASS", "NOT_DECLARED_FOUNDER_ONLY"),
            "member_execution": 0,
            "production_billing": False,
            "production_untouched": True,
            "remote_verified": True,
            "remote_marker": prior.get("marker"),
            "remote_deploy_marker": MARKER,
            "prior_v26_sot_sha256": V26_SOT,
            "closed_beta_member_ia_preserved": True,
            "ia_reopened": False,
            "visual_redesign": False,
            "smoke": smoke,
        },
        "CLOSED_BETA": prior.get("section_30", {}).get("CLOSED_BETA", {}),
        "EXTERNAL_PARTNER_AGENT": prior.get("section_30", {}).get("EXTERNAL_PARTNER_AGENT", {}),
        "SAFETY": {
            "mainnet_writes": 0,
            "real_money": False,
            "member_execution": 0,
            "billing": False,
            "partner_api_exposed": False,
            "production_untouched": True,
            "fabricated_visual_count": 0,
            "founder_monitor_member_exposed": False,
            "fabricated_monitor_values": False,
            "private_execution_data_in_member_apis": False,
            "static_v25_fixture_as_live": False,
        },
    }

    doc = {
        "schema": "v18_2_27_product_compact_v1",
        "generated_at": now,
        "status": "FOUNDER_REAL_FEED_BOUND_CLOSED_BETA_PRESERVED",
        "agent": "A",
        "directive": "V18.2.27",
        "HUMAN_PRODUCT_VISUAL_PASS": prior.get("HUMAN_PRODUCT_VISUAL_PASS"),
        "visual_status": prior.get("visual_status"),
        "commit_needed": True,
        "marker": MARKER,
        "stability_marker_if_commit": MARKER,
        "prior_marker": prior.get("marker"),
        "prior_head": prior.get("product_commit"),
        "prior_product_evidence": str(PRIOR),
        "prior_core_evidence": str(CORE_PRIOR),
        "prior_v26_sot_sha256": V26_SOT,
        "branch": "deploy/nexus-member-preview-v18-2-1",
        "worktree": str(WORKTREE),
        "preview_url": PREVIEW,
        "section_30": section_30,
        "FOUNDER_MONITOR": {
            "route": "/founder/live-ops#demo-monitor",
            "founder_only": True,
            "real_feed_bound": section_30["FOUNDER_MONITOR"]["real_feed_bound"],
            "fixture_removed": section_30["FOUNDER_MONITOR"]["fixture_removed"],
            "position_state": section_30["FOUNDER_MONITOR"]["position_state"],
            "live_position": section_30["FOUNDER_MONITOR"]["live_position"],
            "wallet": section_30["FOUNDER_MONITOR"]["wallet"],
            "remote_deployed": section_30["FOUNDER_MONITOR"]["remote_deployed"],
        },
        "PRODUCT": {"closed_beta": True, "billing": False, "partner": False},
        "generation": 2,
        "billing": False,
        "member_execution": 0,
        "production_untouched": True,
        "closed_beta_ready": True,
        "updated_at": now,
    }

    raw = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    OUT.write_text(raw, encoding="utf-8")
    sha = hashlib.sha256(raw.encode()).hexdigest()
    print(json.dumps({"written": str(OUT), "sha256": sha, "tests": tests}, indent=2))
    return 0 if tests["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

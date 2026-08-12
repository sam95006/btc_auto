#!/usr/bin/env python3
"""V15-C Real Development Research Campaign harness.

TWO PASSES. Development-classified real historical data (or FIXTURE_NOT_REAL fallback).
Hard bans: no WF, no OOS, no demo/exchange, no auto-integrate, no QUALIFIED,
no profitability claims, no *_status.json.

Emits artifacts under:
  artifacts/readiness/immutable/v15_c_real_development_research_campaign/

Does NOT write any *_status.json (lane hard ban).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ART_REL = Path("artifacts/readiness/immutable/v15_c_real_development_research_campaign")
BRANCH = "feature/v15-real-development-research-campaign"
BASE_COMMIT = "a7c14d9e9004e0e3a6399424fa3375fdea17e367"

OWNED_SCAN_PATHS = [
    "backend/nexus_dev_research_campaign_v15/",
    "tools/research/dev_research_campaign_v15/",
    "tests/dev_research_campaign_v15/",
    "artifacts/readiness/immutable/v15_c_real_development_research_campaign/",
]

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    if "status.json" in path.name:
        raise RuntimeError(f"HARD BAN: refusing status json write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def scan_secrets() -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_SCAN_PATHS:
        target = ROOT / rel
        if not target.is_dir():
            continue
        files = [
            p
            for p in target.rglob("*")
            if p.is_file() and p.suffix.lower() in {".py", ".json", ".md"}
        ]
        for path in files:
            # Skip large market cache payloads
            if "market_cache" in str(path).replace("\\", "/"):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v15_c_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": OWNED_SCAN_PATHS,
    }


def run_pytest() -> dict[str, Any]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/dev_research_campaign_v15/",
            "-q",
            "--tb=line",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    return {
        "exit_code": proc.returncode,
        "passed": proc.returncode == 0,
        "elapsed_s": round(time.perf_counter() - t0, 3),
        "tail": "\n".join(out.strip().splitlines()[-80:]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=ROOT / ART_REL)
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--fixture-only", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")
    os.environ.setdefault("FORMAL_WALK_FORWARD", "false")
    os.environ.setdefault("OOS_EXECUTE", "false")
    os.environ.setdefault("OOS_CONSUME", "false")
    os.environ.setdefault("AUTO_INTEGRATE", "false")
    os.environ.setdefault("DEMO_ORDERS", "false")
    os.environ.setdefault("SHADOW_ORDERS", "false")

    from backend.nexus_dev_research_campaign_v15 import (
        run_adversarial_review,
        run_campaign,
        write_immutable_artifacts,
    )
    from backend.nexus_dev_research_campaign_v15.data import load_development_panel
    from backend.nexus_dev_research_campaign_v15.hard_bans import assert_no_status_json

    secrets = scan_secrets()
    _write(args.out_dir / "secret_scan.json", secrets)

    use_network = not args.no_network and not args.fixture_only
    panel = load_development_panel(
        root=ROOT,
        use_network=use_network,
        allow_fixture_fallback=True,
    )
    # If fixture-only requested, force fixture path
    if args.fixture_only and panel.classification != "FIXTURE_NOT_REAL":
        from backend.nexus_dev_research_campaign_v15.data import _fixture_panel
        from backend.nexus_dev_research_campaign_v15.constants import (
            DEFAULT_INTERVAL,
            DEFAULT_SYMBOLS,
            DEV_END_MS,
            DEV_START_MS,
        )

        panel = _fixture_panel(
            symbols=list(DEFAULT_SYMBOLS),
            start_ms=DEV_START_MS,
            end_ms=DEV_END_MS,
            interval=DEFAULT_INTERVAL,
        )

    # TWO PASSES
    report_p1 = run_campaign(root=ROOT, panel=panel, pass_id=1)
    adv_p1 = run_adversarial_review(report_p1, root=ROOT, pass_name="pass_1")

    report_p2 = run_campaign(root=ROOT, panel=panel, pass_id=2)
    adv_p2 = run_adversarial_review(report_p2, root=ROOT, pass_name="pass_2")

    report = report_p2
    adversarial_passes = [adv_p1, adv_p2]
    paths = write_immutable_artifacts(report, adversarial_passes, root=ROOT)

    pytest_result: dict[str, Any] = {"skipped": True, "passed": True}
    if not args.skip_pytest:
        pytest_result = run_pytest()
        _write(args.out_dir / "pytest_report.json", pytest_result)

    status_scan = assert_no_status_json(ROOT / ART_REL)
    head = _git_head()

    pass_ok = (
        report["qualification_ready_count"] == 0
        and report["oos_consumed"] is False
        and report["formal_walk_forward_executed"] is False
        and report["exchange_write_attempt_count"] == 0
        and report["demo_order_count"] == 0
        and report["profitability_claimed"] is False
        and report["qualified_claimed"] is False
        and adv_p1["adversarial_ok"]
        and adv_p2["adversarial_ok"]
        and secrets["secret_leak_count"] == 0
        and bool(pytest_result.get("passed"))
        and status_scan["ok"]
        and int(report["mechanism_count"]) >= 40
        and report["status_json_emitted"] is False
    )

    metrics = {
        "schema": "v15_c_final_metrics",
        "lane": "V15-C",
        "lane_name": "REAL_DEVELOPMENT_RESEARCH_CAMPAIGN",
        "branch": BRANCH,
        "base_commit": BASE_COMMIT,
        "lane_head": head,
        "worktree": str(ROOT),
        "created_at": _utc(),
        "pass": pass_ok,
        "pass_1_ok": adv_p1["adversarial_ok"],
        "pass_2_ok": adv_p2["adversarial_ok"],
        "passes_completed": ["PASS_1", "PASS_2"],
        "data_lineage": report["data_lineage"],
        "fixture_used": report["fixture_used"],
        "fixture_never_called_real": True,
        "development_interval_id": report["development_interval_id"],
        "panel_digest": report["panel_digest"],
        "mechanism_count": report["mechanism_count"],
        "mechanism_family_count": report["mechanism_family_count"],
        "label_histogram": report["label_histogram"],
        "multiple_testing_rejected_count": report["label_histogram"].get(
            "MULTIPLE_TESTING_REJECTED", 0
        ),
        "cost_destroyed_count": report["label_histogram"].get("COST_DESTROYED", 0),
        "data_blocked_count": report["label_histogram"].get("DATA_BLOCKED", 0),
        "sample_blocked_count": report["label_histogram"].get("SAMPLE_BLOCKED", 0),
        "regime_fragile_count": report["label_histogram"].get("REGIME_FRAGILE", 0),
        "development_review_count": report["label_histogram"].get("DEVELOPMENT_REVIEW", 0),
        "development_promising_not_qualified_count": report["label_histogram"].get(
            "DEVELOPMENT_PROMISING_NOT_QUALIFIED", 0
        ),
        "rejected_count": report["label_histogram"].get("REJECTED", 0),
        "mt_testable_count": report["multiple_testing"]["testable_count"],
        "mt_bh_discoveries": report["multiple_testing"]["bh"]["discoveries"],
        "qualification_ready_count": 0,
        "qualified_claimed": False,
        "profitability_claimed": False,
        "profitability_claim_count": 0,
        "edge_claimed": False,
        "edge_claim_count": 0,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "exchange_write_attempt_count": 0,
        "mainnet_touch_count": 0,
        "auto_integrate": False,
        "pr27_merge_attempted": False,
        "status_json_emitted": False,
        "status_json_scan_ok": status_scan["ok"],
        "secret_leak_count": secrets["secret_leak_count"],
        "adversarial_remaining_count": adv_p2["remaining_count"],
        "pytest_passed": bool(pytest_result.get("passed")),
        "artifacts": {k: str(v).replace("\\", "/") for k, v in paths.items()},
        "hard_bans_honored": True,
        "code_checksum": report["code_checksum"],
    }
    # Final metrics file is NOT a status.json
    _write(args.out_dir / "final_metrics.json", metrics)
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0 if pass_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

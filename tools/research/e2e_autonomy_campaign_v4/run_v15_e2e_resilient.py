#!/usr/bin/env python3
"""Resilient V15-K full-scale driver: two passes, file progress, no *_status.json."""
from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG = Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME")) / "v15_k_e2e_campaign_run.log"
PROGRESS = Path(os.environ.get("NEXUS_RUNTIME", r"D:\NEXUS_RUNTIME")) / "v15_k_e2e_campaign_progress.jsonl"


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _log(msg: str) -> None:
    line = f"{_utc()} {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except OSError:
                pass
    except OSError:
        # stdout may already be redirected to LOG; do not fail the campaign.
        pass


def _progress(obj: dict) -> None:
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    with PROGRESS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"at": _utc(), **obj}, default=str) + "\n")
        fh.flush()


def main() -> int:
    os.environ.setdefault("EXCHANGE_WRITE", "false")
    os.environ.setdefault("MAINNET", "false")
    os.environ.setdefault("REAL_MONEY", "false")
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    # Import runner helpers after env harden.
    from tools.research.e2e_autonomy_campaign_v4.run_v15_e2e_autonomy_campaign import (
        run_secret_scan,
        write_artifacts,
    )
    from backend.nexus_e2e_autonomy_v4 import (
        FROZEN_SEED,
        TARGET_CANDIDATES,
        run_v15_e2e_autonomy_campaign,
    )

    candidate_count = int(os.environ.get("NEXUS_V15_K_E2E_CANDIDATES", str(TARGET_CANDIDATES)))
    seed = int(os.environ.get("NEXUS_V15_K_E2E_SEED", str(FROZEN_SEED)))
    passes = int(os.environ.get("NEXUS_V15_K_E2E_PASSES", "2"))
    session_cands = int(os.environ.get("NEXUS_V15_K_FAULT_SESSION_CANDIDATES", "64"))

    _log(f"START candidates={candidate_count} passes={passes} seed={seed}")
    pass_reports: list[dict] = []
    try:
        for pidx in range(1, max(1, passes) + 1):
            _log(f"PASS {pidx} BEGIN")
            _progress({"event": "pass_begin", "pass_index": pidx})
            report = run_v15_e2e_autonomy_campaign(
                root=None,
                candidate_count=candidate_count,
                seed=seed,
                keep_root=False,
                session_candidate_count=session_cands,
            )
            # Floor guard: never promote below-floor counts to PASS in artifacts.
            if int(report.get("candidate_count") or 0) < TARGET_CANDIDATES or int(
                report.get("completed_lifecycle_count") or 0
            ) < 50_000:
                report = dict(report)
                report["pass"] = False
                if report.get("status") == "NEXUS_V15_K_E2E_AUTONOMY_CAMPAIGN_V4_PASS":
                    report["status"] = (
                        "NEXUS_V15_K_E2E_AUTONOMY_CAMPAIGN_V4_SMOKE_ONLY:runner_floor_guard"
                    )
                blockers = list(report.get("blockers") or [])
                if not any("smoke_only_below_founder_targets" in b for b in blockers):
                    blockers.append("smoke_only_below_founder_targets:runner_floor_guard")
                report["blockers"] = blockers
            pass_reports.append(report)
            _progress(
                {
                    "event": "pass_end",
                    "pass_index": pidx,
                    "pass": report.get("pass"),
                    "status": report.get("status"),
                    "candidate_count": report.get("candidate_count"),
                    "completed_lifecycle_count": report.get("completed_lifecycle_count"),
                    "digest": report.get("digest"),
                    "blockers": report.get("blockers"),
                }
            )
            _log(
                f"PASS {pidx} END pass={report.get('pass')} "
                f"status={report.get('status')} "
                f"completed={report.get('completed_lifecycle_count')} "
                f"digest={report.get('digest')}"
            )
    except Exception as exc:  # noqa: BLE001
        _log(f"FATAL {type(exc).__name__}:{exc}")
        _log(traceback.format_exc())
        return 3

    campaign = pass_reports[-1]
    if len(pass_reports) >= 2:
        digests = {p["digest"] for p in pass_reports}
        if len(digests) != 1:
            campaign = dict(campaign)
            campaign["blockers"] = list(campaign.get("blockers") or []) + [
                f"two_pass_digest_mismatch:{sorted(digests)}"
            ]
            campaign["pass"] = False
            campaign["status"] = (
                "NEXUS_V15_K_E2E_AUTONOMY_CAMPAIGN_V4_INVALID:two_pass_digest_mismatch"
            )

    secret_scan = run_secret_scan()
    if secret_scan["secret_leak_count"] > 0:
        campaign = dict(campaign)
        campaign["blockers"] = list(campaign.get("blockers") or []) + ["secret_leak"]
        campaign["pass"] = False
        campaign["status"] = "NEXUS_V15_K_E2E_AUTONOMY_CAMPAIGN_V4_INVALID:secret_leak"

    paths = write_artifacts(
        campaign=campaign,
        pass_reports=pass_reports,
        secret_scan=secret_scan,
    )
    summary = {
        "lane": "V15-K",
        "status": campaign["status"],
        "pass": campaign["pass"],
        "candidate_count": campaign["candidate_count"],
        "completed_lifecycle_count": campaign["completed_lifecycle_count"],
        "exchange_write_attempt_count": campaign["exchange_write_attempt_count"],
        "invariants": campaign["invariants"],
        "fault_coverage": campaign["fault_coverage"],
        "blockers": campaign["blockers"],
        "digests": [p.get("digest") for p in pass_reports],
        "two_pass_match": len({p.get("digest") for p in pass_reports}) == 1,
        "secret_leak_count": secret_scan.get("secret_leak_count", 0),
        "status_json_written": False,
        "artifacts": {k: str(v) for k, v in paths.items()},
    }
    _log("SUMMARY " + json.dumps(summary, sort_keys=True, default=str))
    print(json.dumps(summary, indent=2, sort_keys=True, default=str), flush=True)
    return 0 if campaign["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

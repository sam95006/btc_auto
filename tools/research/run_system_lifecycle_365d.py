#!/usr/bin/env python3
"""Run V11.1 365-day System Lifecycle Campaign → immutable readiness package.

SYSTEM CORRECTNESS ONLY.

Full target: 365 logical days, multi-symbol, multi vol regimes, full fault matrix.
TWO PASSES by default to confirm deterministic digests + invariants.

Smoke / CI:
  NEXUS_V11_1_SYSTEM_365D_SMOKE=1
  NEXUS_V11_1_SYSTEM_365D_CANDIDATES=<int>
  NEXUS_V11_1_SYSTEM_365D_SEED=<int>
  NEXUS_V11_1_SYSTEM_365D_PASSES=<int>   (default 2)
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/readiness/immutable/v11_1_system_365d"

OWNED_SCAN_PATHS = (
    "backend/nexus_system/lifecycle_365d",
    "tools/research/run_system_lifecycle_365d.py",
    "tests/test_system_lifecycle_365d.py",
)

SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, default=str, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_secret_scan() -> dict:
    hits: list[str] = []
    files_scanned = 0
    for rel in OWNED_SCAN_PATHS:
        path = ROOT / rel
        targets: list[Path]
        if path.is_dir():
            targets = sorted(
                p for p in path.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"}
            )
        elif path.is_file():
            targets = [path]
        else:
            continue
        for fp in targets:
            files_scanned += 1
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(str(fp.relative_to(ROOT)).replace("\\", "/"))
                    break
    return {
        "schema": "v11_1_system_365d_secret_scan",
        "secret_leak_count": len(hits),
        "hits": hits,
        "files_scanned": files_scanned,
        "owned_paths": list(OWNED_SCAN_PATHS),
        "created_at": _utc(),
    }


def write_artifacts(
    *,
    campaign: dict,
    pass_reports: list[dict],
    secret_scan: dict,
) -> dict[str, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    def dump(name: str, obj: object) -> Path:
        p = OUT / name
        _write(p, obj)
        paths[name] = p
        return p

    dump("campaign_report.json", campaign)
    dump("invariants.json", campaign.get("invariants") or {})
    dump("injection_matrix.json", campaign.get("injection_matrix") or {})
    dump("focused_probes.json", campaign.get("focused_probes") or {})
    dump("universe.json", campaign.get("universe") or {})
    dump("hard_bans.json", {
        "hard_bans": campaign.get("hard_bans"),
        "attestations": campaign.get("hard_ban_attestations"),
        "system_correctness_only": True,
        "edge_claim": False,
        "profitability_measured": False,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
        "strategy_selected": False,
    })
    dump("secret_scan.json", secret_scan)
    dump(
        "two_pass.json",
        {
            "schema": "v11_1_system_365d_two_pass",
            "pass_count": len(pass_reports),
            "digests": [p.get("campaign_digest") for p in pass_reports],
            "deterministic": len({p.get("campaign_digest") for p in pass_reports}) == 1,
            "passes": [
                {
                    "pass_number": i + 1,
                    "status": p.get("System_Lifecycle_365d_status"),
                    "pass": p.get("system_lifecycle_365d_pass"),
                    "digest": p.get("campaign_digest"),
                    "invariants": p.get("invariants"),
                }
                for i, p in enumerate(pass_reports)
            ],
            "created_at": _utc(),
        },
    )

    findings = {
        "schema": "v11_1_system_365d_findings",
        "critical": [],
        "high": [],
        "notes": [
            "SYSTEM CORRECTNESS campaign — no profitability / edge / OOS / WF claims.",
            "TWO-PASS digests compared for determinism.",
        ],
        "created_at": _utc(),
    }
    if not campaign.get("system_lifecycle_365d_pass"):
        findings["critical"].append(
            {
                "id": "CAMPAIGN_FAIL",
                "detail": campaign.get("System_Lifecycle_365d_status"),
                "violations": campaign.get("invariant_violations"),
            }
        )
    if int(secret_scan.get("secret_leak_count", 0)) != 0:
        findings["critical"].append(
            {"id": "SECRET_LEAK", "hits": secret_scan.get("hits")}
        )
    digests = [p.get("campaign_digest") for p in pass_reports]
    if len(set(digests)) != 1:
        findings["critical"].append(
            {"id": "NON_DETERMINISTIC_DIGEST", "digests": digests}
        )
    dump("findings_summary.json", findings)

    blockers: list[dict] = []
    if findings["critical"]:
        blockers.extend(findings["critical"])
    dump(
        "blockers.json",
        {
            "schema": "v11_1_system_365d_blockers",
            "blocker_count": len(blockers),
            "blockers": blockers,
            "created_at": _utc(),
        },
    )

    metrics = {
        "schema": "v11_1_system_365d_metrics",
        "logical_days": campaign.get("logical_days"),
        "logical_hours": campaign.get("logical_hours"),
        "candidate_count": campaign.get("candidate_count"),
        "mode": campaign.get("mode"),
        "seed": campaign.get("seed"),
        "invariants": campaign.get("invariants"),
        "session_metrics": (campaign.get("session") or {}).get("metrics"),
        "universe": campaign.get("universe"),
        "focused_probes_pass": (campaign.get("focused_probes") or {}).get("probe_pass"),
        "exchange_write_attempt_count": campaign.get("exchange_write_attempt_count"),
        "campaign_digest": campaign.get("campaign_digest"),
        "created_at": _utc(),
    }
    dump("metrics.json", metrics)

    secret_ok = int(secret_scan.get("secret_leak_count", 0)) == 0
    deterministic = len(set(digests)) == 1
    all_pass = (
        bool(campaign.get("system_lifecycle_365d_pass"))
        and secret_ok
        and deterministic
        and int(campaign.get("exchange_write_attempt_count", 1)) == 0
    )
    status = {
        "schema": "v11_1_system_365d",
        "package": campaign.get("package"),
        "status": (
            "NEXUS_V11_1_SYSTEM_LIFECYCLE_365D_PASS"
            if all_pass
            else "NEXUS_V11_1_SYSTEM_LIFECYCLE_365D_INVALID:AGGREGATE"
        ),
        "system_lifecycle_365d_pass": all_pass,
        "pass_count": len(pass_reports),
        "deterministic_two_pass": deterministic,
        "secret_scan_pass": secret_ok,
        "adapter_id": campaign.get("adapter_id"),
        "canonical_execution_engine": campaign.get("canonical_execution_engine"),
        "canonical_execution_engine_count": campaign.get("canonical_execution_engine_count"),
        "logical_days": campaign.get("logical_days"),
        "mode": campaign.get("mode"),
        "invariants": campaign.get("invariants"),
        "exchange_write_attempt_count": campaign.get("exchange_write_attempt_count"),
        "system_correctness_only": True,
        "edge_claim": False,
        "profitability_measured": False,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
        "strategy_selected": False,
        "mainnet": False,
        "real_money": False,
        "runtime_mode": campaign.get("runtime_mode"),
        "campaign_digest": campaign.get("campaign_digest"),
        "blocker_count": len(blockers),
        "created_at": _utc(),
    }
    dump("system_lifecycle_365d_status.json", status)

    readiness = {
        "schema": "v11_1_system_365d_readiness",
        "ready": all_pass,
        "status": status["status"],
        "artifacts": sorted(paths.keys()),
        "created_at": _utc(),
    }
    dump("readiness_report.json", readiness)
    return paths


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.nexus_system.lifecycle_365d import (
        PASS_STATUS,
        load_lifecycle_365_config,
        run_system_lifecycle_365d_campaign,
    )

    cfg = load_lifecycle_365_config()
    passes = cfg.passes
    print(
        f"v11_1 system 365d mode={cfg.mode} days={cfg.logical_days} "
        f"candidates={cfg.candidate_count} seed={cfg.seed} passes={passes}",
        flush=True,
    )

    pass_reports: list[dict] = []
    run_root = ROOT / ".nexus_runtime" / "tmp" / "v11_1_system_365d"
    for p in range(1, passes + 1):
        pass_root = run_root / f"pass_{p}"
        if pass_root.exists():
            # Fresh root per pass to avoid cross-pass durability pollution.
            import shutil

            shutil.rmtree(pass_root, ignore_errors=True)
        pass_root.mkdir(parents=True, exist_ok=True)
        campaign = run_system_lifecycle_365d_campaign(pass_root, config=cfg)
        print(
            f"pass={p} status={campaign.get('System_Lifecycle_365d_status')} "
            f"digest={campaign.get('campaign_digest', '')[:16]} "
            f"inv_ok={not campaign.get('invariant_violations')}",
            flush=True,
        )
        pass_reports.append(campaign)

    final = pass_reports[-1]
    secret_scan = run_secret_scan()
    paths = write_artifacts(
        campaign=final,
        pass_reports=pass_reports,
        secret_scan=secret_scan,
    )
    digests = {p.get("campaign_digest") for p in pass_reports}
    ok = (
        final.get("system_lifecycle_365d_pass")
        and final.get("System_Lifecycle_365d_status") == PASS_STATUS
        and len(digests) == 1
        and int(secret_scan.get("secret_leak_count", 0)) == 0
    )
    print(
        json.dumps(
            {
                "status": "PASS" if ok else "FAIL",
                "System_Lifecycle_365d_status": final.get("System_Lifecycle_365d_status"),
                "invariants": final.get("invariants"),
                "deterministic": len(digests) == 1,
                "out": str(OUT),
                "artifacts": sorted(paths.keys()),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

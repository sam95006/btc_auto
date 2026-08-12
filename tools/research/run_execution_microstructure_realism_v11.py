#!/usr/bin/env python3
"""Run V11 Execution Microstructure Realism → immutable readiness package.

Full target (default): 250,000 deterministic generated scenarios.

Smoke / CI overrides:
  NEXUS_V11_MICRO_SMOKE=1
  NEXUS_V11_MICRO_SCENARIOS=<int>
  NEXUS_V11_MICRO_SEED=<int>
  NEXUS_V11_MICRO_PASSES=<int>   (default 2)

TWO PASSES by default to confirm deterministic scenario counts + invariants.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts/readiness/immutable/v11_execution_microstructure_realism"

OWNED_SCAN_PATHS = (
    "backend/nexus_execution/book_model_v11.py",
    "backend/nexus_execution/microstructure_realism_v11",
    "tools/research/run_execution_microstructure_realism_v11.py",
    "tests/test_execution_microstructure_realism_v11.py",
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
        "schema": "v11_execution_microstructure_realism_secret_scan",
        "secret_leak_count": len(hits),
        "hits": hits,
        "files_scanned": files_scanned,
        "owned_paths": list(OWNED_SCAN_PATHS),
        "created_at": _utc(),
    }


def main() -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.nexus_execution.microstructure_realism_v11 import (
        PASS_STATUS,
        load_micro_config,
        run_microstructure_campaign,
        write_microstructure_artifacts,
    )

    cfg = load_micro_config()
    passes = max(1, int(os.environ.get("NEXUS_V11_MICRO_PASSES", "2")))
    print(
        f"v11 microstructure mode={cfg.mode} scenarios={cfg.scenarios} "
        f"seed={cfg.seed} passes={passes}",
        flush=True,
    )

    pass_reports: list[dict] = []
    final_status = None
    for p in range(1, passes + 1):
        campaign = run_microstructure_campaign(config=cfg)
        print(
            f"pass={p} count={campaign.get('generated_execution_scenario_count')} "
            f"pass={campaign.get('pass')} violations="
            f"{(campaign.get('invariants') or {}).get('scenarios_with_violations')}",
            flush=True,
        )
        secret_scan = run_secret_scan() if p == passes else None
        paths = write_microstructure_artifacts(
            OUT,
            campaign=campaign,
            secret_scan=secret_scan,
            pass_number=p,
        )
        _write(OUT / f"pass_{p}_summary.json", {
            "pass_number": p,
            "generated_execution_scenario_count": campaign.get("generated_execution_scenario_count"),
            "invariants": campaign.get("invariants"),
            "pass": campaign.get("pass"),
            "seed": campaign.get("seed"),
        })
        pass_reports.append(
            {
                "pass_number": p,
                "count": campaign.get("generated_execution_scenario_count"),
                "invariants": campaign.get("invariants"),
                "pass": campaign.get("pass"),
            }
        )
        status_path = paths.get("microstructure_status.json")
        final_status = json.loads(status_path.read_text(encoding="utf-8")) if status_path else {}

    # Determinism check across passes.
    counts = {r["count"] for r in pass_reports}
    inv = {json.dumps(r["invariants"], sort_keys=True) for r in pass_reports}
    determinism = {
        "schema": "v11_execution_microstructure_realism_determinism",
        "passes": passes,
        "counts_identical": len(counts) == 1,
        "invariants_identical": len(inv) == 1,
        "pass_reports": pass_reports,
        "created_at": _utc(),
    }
    _write(OUT / "determinism_report.json", determinism)

    if not determinism["counts_identical"] or not determinism["invariants_identical"]:
        print("DETERMINISM_FAIL", flush=True)
        return 2

    summary = {
        "status": (final_status or {}).get("status"),
        "fuzz_scenarios_achieved": (final_status or {}).get("fuzz_scenarios_achieved"),
        "fuzz_pass": (final_status or {}).get("fuzz_pass"),
        "secret_scan_pass": (final_status or {}).get("secret_scan_pass"),
        "passes": passes,
        "out": str(OUT),
    }
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if (final_status or {}).get("status") == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())

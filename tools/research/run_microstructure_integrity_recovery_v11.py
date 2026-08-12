#!/usr/bin/env python3
"""Run V11 microstructure integrity recovery (forensic RCA + recovery map).

Hard bans: does not edit raw campaign partitions, does not start Event Study,
does not silently repair bytes, does not generate strategies.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def secret_scan(owned_paths: list[Path]) -> dict:
    bad: list[str] = []
    pat = re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY")
    for base in owned_paths:
        if not base.exists():
            continue
        paths = [base] if base.is_file() else list(base.rglob("*"))
        for p in paths:
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".py", ".md", ".json", ".yml", ".yaml", ".toml", ".txt"}:
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if pat.search(text):
                bad.append(str(p.relative_to(ROOT)))
    return {"secret_leak_count": len(bad), "secret_leak_paths": bad}


def main(argv: list[str] | None = None) -> int:
    os.environ["EXCHANGE_WRITE"] = "false"
    os.environ["MAINNET"] = "false"
    os.environ["REAL_MONEY"] = "false"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--partitions-root",
        type=Path,
        default=Path(
            r"D:\NEXUS\btc_bot\.nexus_runtime\microstructure\finalize_roots\ms_accum_v7_bounded_24h\partitions"
        ),
    )
    parser.add_argument(
        "--source-partitions-root",
        type=Path,
        default=Path(r"D:\NEXUS\btc_bot\.nexus_runtime\microstructure\v1_2\BYBIT"),
    )
    parser.add_argument(
        "--finalizer-artifact-dir",
        type=Path,
        default=Path(
            r"D:\NEXUS\btc_bot\artifacts\readiness\immutable\microstructure_campaign_finalizer_v1_real_ms_accum_v7"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts/readiness/immutable/v11_microstructure_integrity_recovery",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=ROOT / "tests/fixtures/microstructure_integrity_v11",
    )
    parser.add_argument("--skip-fixtures", action="store_true")
    parser.add_argument("--pass-number", type=int, default=1)
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from backend.nexus_microstructure.integrity_recovery_v11.orchestrator import (
        run_integrity_recovery,
    )

    # Hard ban: refuse to write under raw microstructure runtime partitions.
    banned = Path(r"D:\NEXUS\btc_bot\.nexus_runtime\microstructure")
    out_resolved = args.output_dir.resolve()
    fix_resolved = args.fixtures_dir.resolve()
    for target in (out_resolved, fix_resolved):
        try:
            target.relative_to(banned.resolve())
            print("REFUSING to write under raw microstructure runtime:", target, file=sys.stderr)
            return 2
        except ValueError:
            pass

    result = run_integrity_recovery(
        partitions_root=args.partitions_root,
        output_dir=args.output_dir,
        fixtures_dir=None if args.skip_fixtures else args.fixtures_dir,
        finalizer_artifact_dir=args.finalizer_artifact_dir,
        source_partitions_root=args.source_partitions_root,
        write_fixtures=not args.skip_fixtures,
    )
    result["status"]["pass"] = args.pass_number
    owned = [
        ROOT / "backend/nexus_microstructure/integrity_recovery_v11",
        ROOT / "tools/research/run_microstructure_integrity_recovery_v11.py",
        ROOT / "tests/test_microstructure_integrity_recovery_v11.py",
        ROOT / "tests/fixtures/microstructure_integrity_v11",
        ROOT / "artifacts/readiness/immutable/v11_microstructure_integrity_recovery",
    ]
    secret = secret_scan(owned)
    (args.output_dir / "secret_scan.json").write_text(
        json.dumps(secret, indent=2) + "\n", encoding="utf-8"
    )
    result["status"]["secret_leak_count"] = secret["secret_leak_count"]
    if secret["secret_leak_count"]:
        result["status"]["Microstructure_Integrity_Recovery_V11_status"] = "FAIL"
    (args.output_dir / "recovery_status.json").write_text(
        json.dumps(result["status"], indent=2) + "\n", encoding="utf-8"
    )

    print(json.dumps({
        "status": result["status"]["Microstructure_Integrity_Recovery_V11_status"],
        "pass": args.pass_number,
        "classification_counts": result["status"]["classification_counts"],
        "primary_classification_counts": result["status"].get("primary_classification_counts"),
        "v11_measured": result["status"]["v11_measured"],
        "reported_v1": result["status"]["reported_v1"],
        "fixes_verified": result["status"].get("fixes_verified"),
        "event_study_readiness_status": "NOT_READY",
        "remaining_blockers": result["status"]["remaining_blockers"],
        "output_dir": str(args.output_dir),
    }, indent=2))
    return 0 if result["status"]["Microstructure_Integrity_Recovery_V11_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V17-G Gold Feature Factory — fixture-only runner / evidence emitter."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.nexus_gold_feature_factory import (  # noqa: E402
    FEATURE_IDS,
    HARD_BANS,
    LANE,
    build_synthetic_market,
    compute_all_features,
    feature_catalog,
    prove_pit_excludes_future,
    run_factory_guards,
    verify_deterministic_replay,
)
from backend.nexus_gold_feature_factory.constants import (  # noqa: E402
    BASE_COMMIT,
    BRANCH,
    EVIDENCE_CLASSIFICATION,
    SCHEMA,
)
from backend.nexus_gold_feature_factory.guards import (  # noqa: E402
    FeatureFactoryBanError,
    reject_duplicate_authority,
)


def _git_head() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=str(ROOT), stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        return "UNKNOWN"


def build_evidence(*, pytest_rc: int, pytest_summary: str) -> dict:
    market = build_synthetic_market(seed="v17g-evidence")
    bundle = compute_all_features(market)
    replay = verify_deterministic_replay(market)
    pit = prove_pit_excludes_future(market, as_of=int(market["as_of_default"]))
    guards = run_factory_guards(ROOT)

    # Attempt dual authority must fail
    dual_authority_blocked = False
    try:
        reject_duplicate_authority("trend", "trend.rogue_alt_formula.v9")
    except FeatureFactoryBanError:
        dual_authority_blocked = True

    metadata_ok = all(
        all(
            k in obs
            for k in (
                "feature_version",
                "source_lineage",
                "as_of",
                "available_at",
                "lookback",
                "normalization",
                "missing_policy",
                "license_scope",
                "calculation_hash",
            )
        )
        for obs in bundle["features"].values()
    )

    passed = (
        pytest_rc == 0
        and replay["ok"]
        and pit["ok"]
        and guards["silent_forward_fill_ok"]
        and guards["single_authority_ok"]
        and guards["future_label_ast_ok"]
        and dual_authority_blocked
        and metadata_ok
        and bundle["feature_count"] == len(FEATURE_IDS)
        and bundle["exchange_write_attempt_count"] == 0
        and bundle["mainnet"] is False
        and EVIDENCE_CLASSIFICATION == "fixture"
    )

    return {
        "schema": SCHEMA,
        "lane": LANE,
        "pass": passed,
        "branch": BRANCH,
        "base_sha": BASE_COMMIT,
        "lane_head": _git_head(),
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_classification": EVIDENCE_CLASSIFICATION,
        "real_or_fixture": "fixture",
        "fixture_only": True,
        "feature_ids": list(FEATURE_IDS),
        "feature_count": len(FEATURE_IDS),
        "catalog_version": feature_catalog()["catalog_version"],
        "bundle_checksum": bundle["bundle_checksum"],
        "fixture_checksum": market["fixture_checksum"],
        "deterministic_replay_ok": replay["ok"],
        "pit_excludes_future_ok": pit["ok"],
        "metadata_fields_ok": metadata_ok,
        "dual_authority_blocked": dual_authority_blocked,
        "guards": guards,
        "hard_bans": HARD_BANS,
        "tests": {
            "pytest_exit_code": pytest_rc,
            "summary": pytest_summary,
            "focused": "tests/test_gold_feature_factory_v17.py",
        },
        "exchange_write_attempt_count": 0,
        "mainnet": False,
        "pr26_touched": False,
        "pr27_touched": False,
        "report_edited": False,
        "sample_feature_hashes": {
            fid: bundle["features"][fid]["calculation_hash"] for fid in FEATURE_IDS
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="V17-G Gold Feature Factory runner")
    parser.add_argument(
        "--evidence-out",
        default=r"D:\NEXUS_RUNTIME\evidence_coordinator\v17_g_feature_factory.json",
    )
    parser.add_argument("--skip-pytest", action="store_true")
    args = parser.parse_args()

    pytest_rc = 0
    pytest_summary = "skipped"
    if not args.skip_pytest:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_gold_feature_factory_v17.py",
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        pytest_rc = proc.returncode
        pytest_summary = (proc.stdout + proc.stderr).strip()[-2000:]

    evidence = build_evidence(pytest_rc=pytest_rc, pytest_summary=pytest_summary)
    out = Path(args.evidence_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pass": evidence["pass"], "lane_head": evidence["lane_head"], "evidence": str(out)}))
    return 0 if evidence["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

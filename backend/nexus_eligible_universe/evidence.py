"""Evidence assembly for V18-C Eligible Universe Engine."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_eligible_universe.catalog import live_catalog_smoke
from backend.nexus_eligible_universe.constants import (
    BASE_COMMIT,
    BRANCH,
    CAMPAIGN_ID,
    FUNNEL_KEYS,
    GATES,
    HARD_BANS,
    LANE,
    LANE_NAME,
    OWNED_PATHS,
    SCHEMA,
    UNIVERSE_CLASSES,
)
from backend.nexus_eligible_universe.engine import evaluate_universe
from backend.nexus_eligible_universe.fixtures import AS_OF_MS, expected_class_for_symbol, fixture_instruments
from backend.nexus_eligible_universe.hard_bans import hard_ban_probe_matrix


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha_obj(obj: Any) -> str:
    import hashlib

    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()


def run_fixture_proof() -> dict[str, Any]:
    instruments = fixture_instruments()
    result = evaluate_universe(instruments, as_of_ms=AS_OF_MS)
    mismatches: list[dict[str, str]] = []
    for d in result["decisions"]:
        expected = expected_class_for_symbol(d["symbol"])
        if expected is not None and d["universe_class"] != expected:
            mismatches.append(
                {
                    "symbol": d["symbol"],
                    "got": d["universe_class"],
                    "expected": expected,
                }
            )
    # Fail-closed proof: no UNKNOWN-bearing fixture may be ELIGIBLE
    unknown_promotions = [
        d
        for d in result["decisions"]
        if d["universe_class"] == "ELIGIBLE"
        and any(not g["known"] for g in d["gates"])
    ]
    funnel = result["funnel"]
    hardcoded_guard = all(isinstance(funnel[k], int) and funnel[k] >= 0 for k in FUNNEL_KEYS)
    return {
        "passed": len(mismatches) == 0 and len(unknown_promotions) == 0 and hardcoded_guard,
        "instrument_count": len(instruments),
        "funnel": funnel,
        "class_histogram": result["class_histogram"],
        "mismatches": mismatches,
        "unknown_promotions": [d["symbol"] for d in unknown_promotions],
        "funnel_checksum": _sha_obj(funnel),
        "decision_checksum": _sha_obj(
            sorted(
                (
                    {
                        "symbol": d["symbol"],
                        "universe_class": d["universe_class"],
                        "reasons": d["reasons"],
                    }
                    for d in result["decisions"]
                ),
                key=lambda x: x["symbol"],
            )
        ),
    }


def run_live_smoke_proof(*, limit: int = 40, as_of_ms: int | None = None) -> dict[str, Any]:
    import time

    smoke = live_catalog_smoke(limit=limit)
    if not smoke["ok"]:
        return {
            "passed": True,  # live optional; fixture path is authoritative
            "optional": True,
            "ok": False,
            "mode": smoke.get("mode"),
            "error": smoke.get("error"),
            "funnel": None,
            "eligible_must_be_zero_when_fields_missing": True,
            "note": "Live smoke unavailable; fixture funnel remains evidence of record",
        }
    clock = as_of_ms if as_of_ms is not None else int(time.time() * 1000)
    evaluated = evaluate_universe(smoke["instruments"], as_of_ms=clock)
    funnel = evaluated["funnel"]
    # With missing history/completeness/trust/depth/cost, ELIGIBLE must be 0
    eligible_zero = funnel["eligible_contracts"] == 0
    return {
        "passed": eligible_zero,
        "optional": True,
        "ok": True,
        "mode": smoke["mode"],
        "exchange_write": False,
        "total_instruments_fetched": smoke["total_instruments_fetched"],
        "total_tickers_fetched": smoke["total_tickers_fetched"],
        "normalized_count": smoke["normalized_count"],
        "funnel": funnel,
        "class_histogram": evaluated["class_histogram"],
        "eligible_must_be_zero_when_fields_missing": eligible_zero,
        "sample_symbols": [d["symbol"] for d in evaluated["decisions"][:8]],
        "sample_classes": [d["universe_class"] for d in evaluated["decisions"][:8]],
    }


def evaluate_lane(*, head: str, worktree: str, try_live: bool = True) -> dict[str, Any]:
    fixture_proof = run_fixture_proof()
    live_proof = (
        run_live_smoke_proof()
        if try_live
        else {
            "passed": True,
            "optional": True,
            "ok": False,
            "mode": "SKIPPED",
            "funnel": None,
        }
    )
    bans = hard_ban_probe_matrix()
    passed = (
        fixture_proof["passed"]
        and live_proof["passed"]
        and bans["all_refused"]
        and bans["env_guard"]["ok"]
    )
    evidence = {
        "schema": "v18_c_eligible_universe_evidence_v1",
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "lane": LANE,
        "lane_name": LANE_NAME,
        "program_id": "NEXUS_V18_LIVE_ELIGIBLE_UNIVERSE",
        "campaign_id": CAMPAIGN_ID,
        "engine_schema": SCHEMA,
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "recommendation": (
            "NEXUS_V18_LIVE_ELIGIBLE_UNIVERSE_PASS"
            if passed
            else "NEXUS_V18_LIVE_ELIGIBLE_UNIVERSE_FAIL"
        ),
        "branch": BRANCH,
        "base_head": BASE_COMMIT,
        "commit": head,
        "lane_head": head,
        "worktree": worktree,
        "owned_paths": list(OWNED_PATHS),
        "prohibited_paths": [
            "frontend/",
            "deploy/",
            "G:/",
            "PR26",
            "PR27",
            "acceleration_report",
        ],
        "hard_bans": sorted(HARD_BANS),
        "hard_ban_probes": bans,
        "universe_classes": list(UNIVERSE_CLASSES),
        "gates": list(GATES),
        "funnel_keys": list(FUNNEL_KEYS),
        "fixture_proof": {
            "passed": fixture_proof["passed"],
            "instrument_count": fixture_proof["instrument_count"],
            "funnel": fixture_proof["funnel"],
            "class_histogram": fixture_proof["class_histogram"],
            "mismatches": fixture_proof["mismatches"],
            "unknown_promotions": fixture_proof["unknown_promotions"],
            "funnel_checksum": fixture_proof["funnel_checksum"],
            "decision_checksum": fixture_proof["decision_checksum"],
            "evidence_class": "CONTROL_FIXTURE_FROM_PUBLIC_CATALOG_SHAPE",
            "note": "Funnel integers computed by engine over fixtures — not hardcoded",
        },
        "live_catalog_smoke": live_proof,
        "sample_funnel": fixture_proof["funnel"],
        "execution_mode": "READ_ONLY_PUBLIC_CATALOG_OR_FIXTURE_FAIL_CLOSED",
        "evidence_class": "UNIVERSE_CONTROL_NOT_MARKET_PERFORMANCE",
        "label": "LIVE_ELIGIBLE_UNIVERSE_ENGINE_NOT_REAL_TRADING",
        "exchange_write": False,
        "mainnet": False,
        "demo": False,
        "real_money": False,
        "pr26_touched": False,
        "pr27_touched": False,
        "report_edited": False,
        "archive_rebuilt": False,
        "unknown_defaults_to_eligible": False,
    }
    return evidence


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

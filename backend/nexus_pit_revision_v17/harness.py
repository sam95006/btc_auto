"""Harness: evaluate V17-D PIT revision control and write immutable artifacts."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_pit_revision_v17.constants import (
    ARTIFACT_REL,
    BASE_COMMIT,
    BRANCH,
    HARD_BANS,
    LANE,
    LANE_NAME,
    NON_CLAIMS,
    SCHEMA,
    SCHEMA_VERSION,
    TIME_AXES,
)
from backend.nexus_pit_revision_v17.fixtures import DAY, T0, build_revision_catalog, fixture_summary
from backend.nexus_pit_revision_v17.hard_bans import hard_ban_probe_matrix, scan_owned_paths_for_banned_claims
from backend.nexus_pit_revision_v17.redteam import run_future_leakage_redteam
from backend.nexus_pit_revision_v17.store import PitRevisionStore, prove_pit_visibility, research_query


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_obj(obj: Any) -> str:
    return _sha_bytes(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )


def _atomic_write_json(path: Path, obj: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    data = payload.encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return _sha_bytes(data)


def evaluate_pit_revision_control(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    store = PitRevisionStore()
    store.ingest_many(build_revision_catalog())

    demo_queries = [
        research_query(
            store,
            series_id="SYNTH.BTCUSDT.CLOSE",
            as_known_at=T0 + 3 * DAY,
        ).to_dict(),
        research_query(
            store,
            series_id="SYNTH.BTCUSDT.CLOSE",
            as_known_at=T0 + 6 * DAY,
        ).to_dict(),
        research_query(
            store,
            series_id="SYNTH.ETHUSDT.CLOSE",
            as_known_at=T0 + 4 * DAY,
        ).to_dict(),
        research_query(
            store,
            series_id="SYNTH.BTCUSDT.REGIME_LABEL",
            as_known_at=T0 + 5 * DAY,
            label_name="regime_v1",
        ).to_dict(),
    ]

    pit_proof = prove_pit_visibility(
        store, series_id="SYNTH.BTCUSDT.CLOSE", as_known_at=T0 + 3 * DAY
    )
    redteam = run_future_leakage_redteam()
    bans = hard_ban_probe_matrix()
    claim_scan = scan_owned_paths_for_banned_claims(root)

    status = (
        "PASS"
        if redteam["pass"]
        and pit_proof["pit_holds"]
        and bans["env_ok"]
        and claim_scan["ok"]
        and redteam["survivor_count"] == 0
        else "FAIL"
    )

    summary = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "branch": BRANCH,
        "base": BASE_COMMIT,
        "generated_at": _utc(),
        "status": status,
        "time_axes": list(TIME_AXES),
        "capabilities": [
            "as_known_at",
            "later_revisions",
            "revision_lineage",
            "late_arriving",
            "backfill",
            "label_revision",
            "unavailable_at_time_guard",
        ],
        "fixture_summary": fixture_summary(),
        "demo_queries": demo_queries,
        "pit_visibility_proof": pit_proof,
        "future_leakage_redteam": {
            "attack_count": redteam["attack_count"],
            "blocked_count": redteam["blocked_count"],
            "survivor_count": redteam["survivor_count"],
            "survivors": redteam["survivors"],
            "pass": redteam["pass"],
        },
        "hard_bans": list(HARD_BANS),
        "hard_ban_probe": bans,
        "banned_claim_scan": claim_scan,
        "non_claims": list(NON_CLAIMS),
        "formal_wf_executed": False,
        "oos_claimed": False,
        "exchange_write_attempt_count": 0,
        "mainnet_client_count": 0,
        "real_market_data": False,
        "fixture_only": True,
    }
    summary["content_sha256"] = _sha_obj(
        {k: v for k, v in summary.items() if k not in {"generated_at", "content_sha256"}}
    )
    return summary


def write_immutable_artifacts(
    summary: dict[str, Any],
    *,
    repo_root: Path | None = None,
    redteam: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    art = root / ARTIFACT_REL
    written: dict[str, str] = {}
    written["summary"] = _atomic_write_json(art / "pit_revision_summary.json", summary)
    if redteam is None:
        redteam = run_future_leakage_redteam()
    written["redteam"] = _atomic_write_json(art / "future_leakage_redteam.json", redteam)
    contract = {
        "schema": "v17_d_pit_revision_contract_v1",
        "time_axes": list(TIME_AXES),
        "research_query_requires": ["as_known_at"],
        "visibility_rule": (
            "available_time <= AS_KNOWN_AT AND "
            "revision_time <= AS_KNOWN_AT AND "
            "ingest_time <= AS_KNOWN_AT"
        ),
        "hard_bans": list(HARD_BANS),
        "non_claims": list(NON_CLAIMS),
    }
    written["contract"] = _atomic_write_json(art / "pit_revision_contract.json", contract)
    return {"artifact_dir": str(art), "sha256": written}


def run_pit_revision_lab(*, repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[2]
    redteam = run_future_leakage_redteam()
    summary = evaluate_pit_revision_control(repo_root=root)
    artifacts = write_immutable_artifacts(summary, repo_root=root, redteam=redteam)
    return {
        "summary": summary,
        "redteam": redteam,
        "artifacts": artifacts,
        "status": summary["status"],
        "survivor_count": redteam["survivor_count"],
    }

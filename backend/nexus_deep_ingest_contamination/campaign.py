"""Three-capability campaign for V17 deep ingest recovery + contamination."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from backend.nexus_deep_ingest_contamination.archive_recovery import CorruptArchiveRecovery
from backend.nexus_deep_ingest_contamination.constants import (
    ARTIFACT_REL,
    BASE_SHA,
    BRANCH,
    COVERAGE_AREAS,
    HARD_BANS,
    LANE,
    LANE_NAME,
    NON_CLAIMS,
    OWNED_PATHS,
    PROGRAM_ID,
    SCHEMA,
    SCHEMA_CAMPAIGN,
)
from backend.nexus_deep_ingest_contamination.duplicate_ingest import DuplicateDatasetIngestor
from backend.nexus_deep_ingest_contamination.hard_bans import hard_ban_inventory
from backend.nexus_deep_ingest_contamination.provider_failover import build_default_failover_proofs
from backend.nexus_deep_ingest_contamination.redteam import run_ingest_contamination_redteam
from backend.nexus_deep_ingest_contamination.resource_profile import (
    resource_limits_document,
    run_bounded_resource_smoke,
)
from backend.nexus_deep_ingest_contamination.revision_conflict import RevisionConflictHarness
from backend.nexus_deep_ingest_contamination.split_contamination import (
    run_deep_split_contamination_attacks,
)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _prove_archive_recovery() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="v17_deep_camp_archive_") as tmp:
        archive = CorruptArchiveRecovery(Path(tmp))
        archive.pack_entry("e1", {"n": 1})
        archive.pack_entry("e2", {"n": 2})
        archive.pack_entry("e3", {"n": 3})
        archive.corrupt_entry_bytes("e2", mode="truncate")
        recovery = archive.recover()
        cp = archive.read_checkpoint()
        ok = (
            recovery["verified_count"] >= 2
            and recovery["quarantined_count"] == 1
            and recovery["silent_corrupt_resume"] is False
            and cp is not None
        )
        return {
            "name": "corrupt_archive_recovery",
            "pass": ok,
            "recovery": recovery,
            "checkpoint": cp,
        }


def _prove_duplicate_ingest() -> dict[str, Any]:
    ing = DuplicateDatasetIngestor()
    a = ing.ingest(dataset_id="ds1", payload={"k": 1}, ingest_id="i1")
    b = ing.ingest(dataset_id="ds1", payload={"k": 1}, ingest_id="i2")
    c = ing.ingest(dataset_id="ds1", payload={"k": 2}, ingest_id="i3")
    ok = a.status == "INGESTED" and b.status == "DUPLICATE" and c.status == "REJECTED"
    return {
        "name": "duplicate_dataset_ingestion",
        "pass": ok,
        "first": a.to_dict(),
        "duplicate": b.to_dict(),
        "id_conflict": c.to_dict(),
        "snapshot": ing.snapshot(),
    }


def _prove_revision_conflict() -> dict[str, Any]:
    proof = RevisionConflictHarness().build_conflict_fixture()
    return {
        "name": "revision_conflict_testing",
        "pass": proof["attack_blocked"],
        "proof": proof,
    }


def run_campaign(*, root: Path | None = None, head: str = "UNKNOWN") -> dict[str, Any]:
    root = Path(root) if root is not None else Path(".")
    archive = _prove_archive_recovery()
    duplicate = _prove_duplicate_ingest()
    revision = _prove_revision_conflict()
    split_rt = run_deep_split_contamination_attacks()
    failover = build_default_failover_proofs()
    resources = run_bounded_resource_smoke()
    redteam = run_ingest_contamination_redteam()
    bans = hard_ban_inventory()

    coverage = {
        "corrupt_archive_recovery": archive["pass"],
        "duplicate_dataset_ingestion": duplicate["pass"],
        "revision_conflict_testing": revision["pass"],
        "dataset_split_contamination_attacks": split_rt.get("status") == "PASS",
        "api_rate_limit_and_provider_outage_failover": failover.get("pass") is True,
        "bounded_memory_disk_profiling_smoke": resources.get("status") == "PASS",
    }
    all_coverage = all(coverage.values())
    survivors = int(redteam.get("survivor_count", 1))
    status = "PASS" if all_coverage and survivors == 0 and redteam.get("status") == "PASS" else "FAIL"

    report = {
        "schema": SCHEMA_CAMPAIGN,
        "module_schema": SCHEMA,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "program_id": PROGRAM_ID,
        "branch": BRANCH,
        "base": BASE_SHA,
        "HEAD": head,
        "status": status,
        "coverage_areas": list(COVERAGE_AREAS),
        "coverage": coverage,
        "proofs": {
            "archive_recovery": archive,
            "duplicate_ingest": duplicate,
            "revision_conflict": revision,
            "split_contamination": {
                "status": split_rt.get("status"),
                "survivor_count": split_rt.get("survivor_count"),
                "attack_count": split_rt.get("attack_count"),
                "survivors": split_rt.get("survivors"),
            },
            "provider_failover": failover,
            "resource_smoke": resources,
        },
        "redteam": redteam,
        "survivor_count": survivors,
        "survivors": redteam.get("survivors", []),
        "resource_limits": resource_limits_document(),
        "hard_bans": list(HARD_BANS),
        "hard_ban_inventory": bans,
        "owned_paths": list(OWNED_PATHS),
        "non_claims": list(NON_CLAIMS),
        "claims_15y_history_downloaded": False,
        "formal_wf_executed": False,
        "oos_claimed": False,
        "exchange_write": False,
        "mainnet": False,
        "real_money": False,
        "report_edited": False,
        "pr26_touched": False,
        "pr27_touched": False,
        "fixture_only": True,
        "live_network": False,
    }

    artifact_dir = root / ARTIFACT_REL
    _write_json(artifact_dir / "campaign_report.json", report)
    _write_json(artifact_dir / "redteam.json", redteam)
    _write_json(artifact_dir / "resource_smoke.json", resources)
    _write_json(
        artifact_dir / "summary.json",
        {
            "status": status,
            "HEAD": head,
            "survivor_count": survivors,
            "coverage": coverage,
        },
    )
    report["artifact_dir"] = str(artifact_dir).replace("\\", "/")
    return report

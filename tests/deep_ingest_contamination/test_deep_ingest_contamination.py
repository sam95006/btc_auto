"""V17 deep ingest recovery + dataset contamination tests."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_deep_ingest_contamination.archive_recovery import (  # noqa: E402
    CorruptArchiveRecovery,
)
from backend.nexus_deep_ingest_contamination.campaign import run_campaign  # noqa: E402
from backend.nexus_deep_ingest_contamination.constants import (  # noqa: E402
    BOUNDED_MAX_DISK_BYTES,
    COVERAGE_AREAS,
    HARD_BANS,
    OWNED_PATHS,
    SCHEMA,
)
from backend.nexus_deep_ingest_contamination.duplicate_ingest import (  # noqa: E402
    DuplicateDatasetIngestor,
)
from backend.nexus_deep_ingest_contamination.hard_bans import (  # noqa: E402
    HardBanViolation,
    refuse_15y_history_claim,
    refuse_exchange_write,
)
from backend.nexus_deep_ingest_contamination.provider_failover import (  # noqa: E402
    ProviderFailoverSimulator,
    build_default_failover_proofs,
)
from backend.nexus_deep_ingest_contamination.redteam import (  # noqa: E402
    run_ingest_contamination_redteam,
)
from backend.nexus_deep_ingest_contamination.resource_profile import (  # noqa: E402
    run_bounded_resource_smoke,
)
from backend.nexus_deep_ingest_contamination.revision_conflict import (  # noqa: E402
    RevisionConflictError,
    RevisionConflictHarness,
)
from backend.nexus_deep_ingest_contamination.split_contamination import (  # noqa: E402
    run_deep_split_contamination_attacks,
)

ROOT = Path(__file__).resolve().parents[2]


def test_owned_paths_and_coverage_contract():
    assert SCHEMA.startswith("v17_deep_")
    assert len(COVERAGE_AREAS) == 6
    assert "corrupt_archive_recovery" in COVERAGE_AREAS
    assert any("nexus_deep_ingest_contamination" in p for p in OWNED_PATHS)
    assert "no_claim_15y_history_downloaded" in HARD_BANS
    assert "no_silent_corrupt_resume" in HARD_BANS


def test_corrupt_archive_recovery_quarantines_and_resumes():
    with tempfile.TemporaryDirectory() as tmp:
        archive = CorruptArchiveRecovery(Path(tmp))
        archive.pack_entry("a", {"x": 1})
        archive.pack_entry("b", {"x": 2})
        archive.corrupt_entry_bytes("b", mode="truncate")
        result = archive.recover()
        assert result["quarantined_count"] == 1
        assert result["verified_count"] == 1
        assert result["silent_corrupt_resume"] is False
        assert result["status"] == "RECOVERED_WITH_QUARANTINE"
        silent = archive.attempt_silent_resume_over_corrupt("b")
        assert silent["attack_blocked"] is True


def test_corrupt_archive_bitflip_and_empty():
    with tempfile.TemporaryDirectory() as tmp:
        archive = CorruptArchiveRecovery(Path(tmp))
        archive.pack_entry("c", {"x": 3})
        archive.corrupt_entry_bytes("c", mode="flip")
        assert archive.verify_entry("c")["status"] == "QUARANTINED"
        archive.pack_entry("d", {"x": 4})
        archive.corrupt_entry_bytes("d", mode="empty")
        assert archive.verify_entry("d")["status"] == "QUARANTINED"


def test_duplicate_dataset_ingestion():
    ing = DuplicateDatasetIngestor()
    first = ing.ingest(dataset_id="ds", payload={"a": 1}, ingest_id="1")
    second = ing.ingest(dataset_id="ds", payload={"a": 1}, ingest_id="2")
    conflict = ing.ingest(dataset_id="ds", payload={"a": 2}, ingest_id="3")
    assert first.status == "INGESTED"
    assert second.status == "DUPLICATE"
    assert conflict.status == "REJECTED"
    probe = DuplicateDatasetIngestor().duplicate_attack_probe(
        dataset_id="ds2", payload={"rows": [1, 2, 3]}
    )
    assert probe["attack_blocked"] is True
    assert probe["survivor"] is False


def test_revision_conflict_fork_refused():
    harness = RevisionConflictHarness()
    proof = harness.build_conflict_fixture()
    assert proof["fork_detected"] is True
    assert proof["ambiguous_tip_refused"] is True
    assert proof["duplicate_revision_id_blocked"] is True
    assert proof["attack_blocked"] is True
    with pytest.raises(RevisionConflictError):
        harness.refuse_ambiguous_tip(series_id="btc.mark", as_known_at=1_700_000_002_000)


def test_dataset_split_contamination_survivors_zero():
    report = run_deep_split_contamination_attacks()
    assert report["status"] == "PASS"
    assert report["survivor_count"] == 0
    assert report["survivors"] == []
    assert report["attack_count"] >= 10


def test_provider_rate_limit_failover_fixture():
    sim = ProviderFailoverSimulator()
    rate = sim.run_rate_limit_failover_scenario()
    assert rate["pass"] is True
    assert rate["live_network"] is False
    assert rate["result"]["provider"] == sim.secondary


def test_provider_outage_failover_fixture():
    proofs = build_default_failover_proofs()
    assert proofs["pass"] is True
    assert proofs["outage_failover"]["pass"] is True
    assert proofs["fixture_only"] is True


def test_bounded_resource_smoke_documents_limits_no_15y():
    smoke = run_bounded_resource_smoke(entry_count=6)
    assert smoke["status"] == "PASS"
    assert smoke["claims_15y_history_downloaded"] is False
    assert smoke["fifteen_year_claim_banned"] is True
    assert smoke["disk_budget_enforced"] is True
    assert smoke["limits"]["max_disk_bytes"] == BOUNDED_MAX_DISK_BYTES
    with pytest.raises(HardBanViolation):
        refuse_15y_history_claim(claimed=True)


def test_hard_bans_exchange_write():
    with pytest.raises(HardBanViolation):
        refuse_exchange_write()


def test_redteam_survivors_zero():
    rt = run_ingest_contamination_redteam()
    assert rt["status"] == "PASS"
    assert rt["survivor_count"] == 0
    assert rt["survivors"] == []
    assert rt["attack_count"] >= 8


def test_campaign_pass():
    report = run_campaign(root=ROOT, head="TEST_HEAD")
    assert report["status"] == "PASS"
    assert report["survivor_count"] == 0
    assert all(report["coverage"].values())
    assert report["claims_15y_history_downloaded"] is False
    assert report["formal_wf_executed"] is False
    assert report["exchange_write"] is False
    assert (ROOT / "artifacts/readiness/immutable/v17_deep_ingest_contamination/campaign_report.json").exists()

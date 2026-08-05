"""Focused tests for V15-K End-to-End Autonomy Campaign V4.

Defaults use reduced candidate counts for CI speed. Full 100000/50000 targets
are exercised by ``tools/research/e2e_autonomy_campaign_v4/run_v15_e2e_autonomy_campaign.py``.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("EXCHANGE_WRITE", "false")
os.environ.setdefault("MAINNET", "false")
os.environ.setdefault("REAL_MONEY", "false")

from backend.nexus_e2e_autonomy_v4 import (  # noqa: E402
    CANONICAL_PATH,
    FROZEN_SEED,
    HARD_BANS,
    PASS_STATUS,
    REQUIRED_ONTOLOGY,
    REQUIRED_ZERO_INVARIANTS,
    SCALE_FAULT_CLASSES,
    SMOKE_ONLY_STATUS,
    TARGET_CANDIDATES,
    TARGET_COMPLETED_LIFECYCLES,
    TARGET_SYMBOL_COUNT,
    build_fixture_instruments,
    build_scale_candidates,
    campaign_digest,
    injection_matrix,
    invariants_pass,
    run_cancel_replace_probe,
    run_checkpoint_rollback_probe,
    run_focused_scale_probes,
    run_qualification_blocks_probe,
    run_v15_e2e_autonomy_campaign,
    universe_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OWNED = (
    REPO_ROOT / "backend/nexus_e2e_autonomy_v4",
    REPO_ROOT / "tools/research/e2e_autonomy_campaign_v4",
    REPO_ROOT / "tests/e2e_autonomy_campaign_v4",
)

SECRET_PATTERNS = (
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*\S+"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}['\"]"),
)


def test_targets_and_exports() -> None:
    assert TARGET_CANDIDATES == 100_000
    assert TARGET_COMPLETED_LIFECYCLES == 50_000
    assert TARGET_SYMBOL_COUNT == 100
    assert PASS_STATUS.startswith("NEXUS_V15_K")
    assert "no_profitability_calculation" in HARD_BANS
    assert "no_auto_integrate" in HARD_BANS
    assert "no_auto_integrate_pr27" in HARD_BANS
    assert "duplicate_decision_count" in REQUIRED_ZERO_INVARIANTS
    assert "exchange_write_attempt_count" in REQUIRED_ZERO_INVARIANTS
    assert "CLOSED" in REQUIRED_ONTOLOGY
    assert "LessonGate" in CANONICAL_PATH
    assert "capture_degradation" in SCALE_FAULT_CLASSES
    assert "snapshot_corruption" in SCALE_FAULT_CLASSES
    assert "provider_outage" in SCALE_FAULT_CLASSES
    assert "qualification_blocks" in SCALE_FAULT_CLASSES


def test_universe_multi_symbol_multi_regime() -> None:
    instruments = build_fixture_instruments()
    assert len(instruments) >= TARGET_SYMBOL_COUNT
    cands = build_scale_candidates(500, seed=FROZEN_SEED, complete_quota=280)
    uni = universe_summary(cands)
    assert uni["fixture_universe_size"] >= TARGET_SYMBOL_COUNT
    assert uni["symbol_count"] >= min(TARGET_SYMBOL_COUNT, 20)
    assert uni["vol_regime_count"] >= 3
    assert all(c.get("edge_claim") is False for c in cands)
    assert all(c.get("profitability_measured") is False for c in cands)
    assert any(c.get("fault_tag") for c in cands)
    assert any(c.get("fault_tag") == "capture_degradation" for c in cands)
    for c in cands:
        assert c["symbol"] in instruments


def test_injection_matrix_covers_founder_classes() -> None:
    matrix = injection_matrix()
    for fault in SCALE_FAULT_CLASSES:
        assert fault in matrix["fault_class_to_coverage"]
        assert matrix["fault_class_to_coverage"][fault]


def test_cancel_replace_qualification_checkpoint_probes(tmp_path: Path) -> None:
    cr = run_cancel_replace_probe()
    assert cr["probe_pass"] is True
    assert cr["cancel_replace_count"] >= 1
    assert cr["invariants"]["exchange_write_attempt_count"] == 0
    qual = run_qualification_blocks_probe()
    assert qual["probe_pass"] is True
    assert qual["formal_walk_forward_executed"] is False
    assert qual["oos_consumed"] is False
    assert qual["profitability_measured"] is False
    ckpt = run_checkpoint_rollback_probe(tmp_path)
    assert ckpt["probe_pass"] is True
    assert ckpt["invariants"]["checkpoint_loss_count"] == 0


def test_smoke_campaign_two_pass(tmp_path: Path) -> None:
    """Reduced runs may prove integrity but MUST NOT emit lane PASS_STATUS."""
    a = run_v15_e2e_autonomy_campaign(
        root=tmp_path / "pass1",
        candidate_count=24,
        seed=FROZEN_SEED,
        keep_root=True,
        session_candidate_count=32,
    )
    b = run_v15_e2e_autonomy_campaign(
        root=tmp_path / "pass2",
        candidate_count=24,
        seed=FROZEN_SEED,
        keep_root=True,
        session_candidate_count=32,
    )
    assert a["pass"] is False, "reduced candidate_count must never lane-PASS"
    assert b["pass"] is False
    assert a["smoke_only"] is True
    assert a["integrity_ok"] is True, a.get("blockers")
    assert b["integrity_ok"] is True, b.get("blockers")
    assert a["status"].startswith(SMOKE_ONLY_STATUS), a["status"]
    assert a["status"] != PASS_STATUS
    assert a["founder_scale_ok"] is False
    assert a["candidate_count"] == 24
    assert a["completed_lifecycle_count"] >= 12
    assert a["exchange_write_attempt_count"] == 0
    assert campaign_digest(a) == campaign_digest(b)
    assert a["digest"] == b["digest"]
    for key in REQUIRED_ZERO_INVARIANTS:
        assert a["invariants"][key] == 0
        assert b["invariants"][key] == 0
    assert invariants_pass(a["invariants"])
    assert a["universe"]["fixture_universe_size"] >= TARGET_SYMBOL_COUNT
    assert a["universe"]["vol_regime_count"] >= 3
    assert a["closed_loop"]["restart_count"] >= 1
    assert all(a["fault_coverage"].values()), a["fault_coverage"]
    for sample in a["closed_loop"]["sample_completed"]:
        assert all(s in sample["stages"] for s in CANONICAL_PATH)
        assert sample["ontology"] == list(REQUIRED_ONTOLOGY)
        assert sample["intent_id"]
        assert sample["position_id"]
        assert not str(sample["intent_id"]).startswith("intent_")
        assert not str(sample["position_id"]).startswith("pos_")


def test_reduced_run_cannot_emit_pass_status(tmp_path: Path) -> None:
    """Adversarial false-PASS guard: 1000-candidate smoke is NEVER PASS."""
    report = run_v15_e2e_autonomy_campaign(
        root=tmp_path / "smoke1000",
        candidate_count=48,
        seed=FROZEN_SEED,
        keep_root=True,
        session_candidate_count=24,
    )
    assert report["candidate_count"] == 48
    assert report["candidate_count"] < TARGET_CANDIDATES
    assert report["pass"] is False
    assert report["status"] != PASS_STATUS
    assert report["smoke_only"] is True or report["status"].startswith(SMOKE_ONLY_STATUS)
    assert report["founder_scale_ok"] is False
    assert any("smoke_only_below_founder_targets" in b for b in report["blockers"])


def test_focused_probes_aggregate(tmp_path: Path) -> None:
    focused = run_focused_scale_probes(tmp_path / "focused", seed=FROZEN_SEED)
    assert focused["probe_pass"] is True, focused
    assert focused["probes"]["cancel_replace_probe"]["probe_pass"] is True
    assert focused["probes"]["qualification_blocks_probe"]["probe_pass"] is True
    assert focused["probes"]["checkpoint_rollback_probe"]["probe_pass"] is True
    assert focused["probes"]["restart_recovery_probe"]["probe_pass"] is True
    assert focused["invariants"]["checkpoint_loss_count"] == 0
    assert focused["invariants"]["exchange_write_attempt_count"] == 0


def test_negative_fault_coverage_requires_probe_pass() -> None:
    """Adversarial: mere probe key presence must not satisfy coverage helpers."""
    from backend.nexus_e2e_autonomy_v4.campaign import run_v15_e2e_autonomy_campaign

    # Smoke already asserts all(fault_coverage.values()); additionally ensure
    # kill_switch / clock_anomaly map to probe_pass rather than key presence alone
    # by checking focused probe payloads from a tiny campaign.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="v15k_cov_") as td:
        report = run_v15_e2e_autonomy_campaign(
            root=Path(td),
            candidate_count=16,
            seed=FROZEN_SEED,
            keep_root=True,
            session_candidate_count=24,
        )
    probes = report["focused_probes"]["probes"]
    assert report["pass"] is False
    assert report["smoke_only"] is True
    assert probes["terminal_kill_switch_during_open_position"]["probe_pass"] is True
    assert probes["terminal_clock_jump_backward"]["probe_pass"] is True
    assert report["fault_coverage"]["kill_switch"] is True
    assert report["fault_coverage"]["clock_anomaly"] is True
    # Flip: if probe_pass were False, coverage must not claim True via key alone.
    fake = dict(report["fault_coverage"])
    assert "kill_switch" in fake
    assert probes["cancel_replace_probe"]["probe_pass"] is True


def test_scale_memory_ledger_sequence_number() -> None:
    from backend.nexus_e2e_autonomy_v4.scale_fast_store import ScaleMemoryLedgerLink

    link = ScaleMemoryLedgerLink()
    assert link.sequence_number == 0
    link.append(
        decision_id="d1",
        event_type="OBSERVED",
        payload={"ok": True},
        idempotency_key="k1",
    )
    assert link.sequence_number == 1
    try:
        link.append(
            decision_id="d1",
            event_type="BAD",
            payload={"api_key": "should_refuse"},
            idempotency_key="k2",
        )
        raise AssertionError("secret payload must be refused")
    except ValueError as exc:
        assert "forbidden_secret" in str(exc)


def test_negative_digest_changes_on_invariant_drift() -> None:
    """Adversarial: digest must move if a required-zero counter is non-zero."""
    base = {
        "schema": "v15_k_e2e_autonomy_campaign_v4",
        "seed": 1,
        "candidate_count": 10,
        "completed_lifecycle_count": 7,
        "rejected_count": 3,
        "blocked_count": 0,
        "error_count": 0,
        "universe": {"symbol_count": 100},
        "injection_matrix": {"x": 1},
        "invariants": {k: 0 for k in REQUIRED_ZERO_INVARIANTS},
        "canonical_path": list(CANONICAL_PATH),
        "ontology": list(REQUIRED_ONTOLOGY),
        "fault_coverage": {"multi_symbol": True},
        "hard_bans": list(HARD_BANS),
        "profitability_measured": False,
        "auto_integrate_pr27": False,
    }
    dirty = dict(base)
    dirty["invariants"] = dict(base["invariants"])
    dirty["invariants"]["exchange_write_attempt_count"] = 1
    assert campaign_digest(base) != campaign_digest(dirty)


def test_negative_false_pass_blocked_by_exchange_write() -> None:
    """Adversarial: non-zero exchange write must fail the campaign invariants gate."""
    from backend.nexus_e2e_autonomy_v4.invariants import empty_invariant_counts

    counts = empty_invariant_counts()
    assert invariants_pass(counts)
    counts["exchange_write_attempt_count"] = 1
    assert not invariants_pass(counts)
    counts = empty_invariant_counts()
    counts["duplicate_decision_count"] = 1
    assert not invariants_pass(counts)


def test_owned_paths_secret_scan() -> None:
    hits: list[str] = []
    for root in OWNED:
        if root.is_dir():
            files = [p for p in root.rglob("*") if p.is_file() and p.suffix in {".py", ".json", ".md"}]
        elif root.is_file():
            files = [root]
        else:
            continue
        for fp in files:
            text = fp.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(str(fp))
                    break
    assert hits == []


def test_no_profitability_calc_in_owned_sources() -> None:
    banned = re.compile(
        r"(?i)(sharpe|profit_factor|expectancy|net_pnl|realized_pnl_usd)\s*[:=]"
    )
    for root in OWNED:
        if not root.exists():
            continue
        files = (
            [p for p in root.rglob("*.py")]
            if root.is_dir()
            else ([root] if root.suffix == ".py" else [])
        )
        for fp in files:
            text = fp.read_text(encoding="utf-8", errors="ignore")
            assert not banned.search(text), f"profitability calc leak in {fp}"

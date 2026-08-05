"""V16-B Counterfactual Replay Engine — unit and adversarial tests."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ["EXCHANGE_WRITE"] = "false"
os.environ["MAINNET"] = "false"
os.environ["REAL_MONEY"] = "false"
os.environ.pop("NEXUS_FOUNDER_EXCHANGE_WRITE", None)

from backend.nexus_counterfactual_replay_v16.adversarial import (  # noqa: E402
    pass1_core_integrity,
    pass2_adversarial_leakage,
    pass3_determinism_and_seal,
    run_three_passes,
)
from backend.nexus_counterfactual_replay_v16.constants import (  # noqa: E402
    ALTERNATE_PATHS,
    DISCLAIMER,
    HARD_BANS,
    OWNED_PATHS,
)
from backend.nexus_counterfactual_replay_v16.engine import (  # noqa: E402
    deterministic_replay_proof,
    refuse_banned_artifact_names,
    replay_decision,
    run_counterfactual_replay,
)
from backend.nexus_counterfactual_replay_v16.fixtures import (  # noqa: E402
    build_fixture_bars,
    build_fixture_decisions,
    fixture_manifest,
)
from backend.nexus_counterfactual_replay_v16.hard_bans import (  # noqa: E402
    HardBanViolation,
    refuse_counterfactual_as_real_performance,
    refuse_rewrite_real_ledger,
    refuse_status_json_lane_artifact,
    refuse_status_report_artifact,
)
from backend.nexus_counterfactual_replay_v16.harness import (  # noqa: E402
    evaluate_counterfactual_engine,
    write_immutable_artifacts,
)
from backend.nexus_counterfactual_replay_v16.ledger_guard import (  # noqa: E402
    assert_ledger_unchanged,
    freeze_ledger_snapshot,
)
from backend.nexus_counterfactual_replay_v16.paths import (  # noqa: E402
    PATH_EVALUATORS,
    assert_path_inventory_complete,
)
from backend.nexus_counterfactual_replay_v16.pit import (  # noqa: E402
    filter_bars_pit,
    prove_pit_excludes_future,
)

ROOT = Path(__file__).resolve().parents[2]


def test_path_inventory_complete():
    assert_path_inventory_complete()
    assert set(ALTERNATE_PATHS) == set(PATH_EVALUATORS)
    assert len(ALTERNATE_PATHS) == 11


def test_hard_bans_include_core_guards():
    for ban in (
        "no_future_leakage",
        "no_rewrite_real_ledger",
        "no_counterfactual_profit_as_real_performance",
        "no_status_json_lane_artifact",
        "no_status_report_artifact",
    ):
        assert ban in HARD_BANS
    assert any("nexus_counterfactual_replay_v16" in p for p in OWNED_PATHS)
    assert "COUNTERFACTUAL_PROFIT_IS_NOT_REAL_PERFORMANCE" in DISCLAIMER


def test_fixtures_labelled_not_real_ledger():
    man = fixture_manifest()
    assert man["is_fixture"] is True
    assert man["is_real_ledger"] is False
    assert man["real_performance"] is False
    assert man["decision_count"] == 3


def test_pit_excludes_future_bar():
    bars = build_fixture_bars()
    future = [b for b in bars if b.regime == "FUTURE_LEAK"]
    assert len(future) == 1
    as_of = future[0].ts_ms - 1
    proof = prove_pit_excludes_future(bars, as_of_ms=as_of)
    assert proof["pit_holds"] is True
    assert proof["future_count"] >= 1
    eligible = filter_bars_pit(bars, as_of_ms=as_of)
    assert all(b.regime != "FUTURE_LEAK" for b in eligible)


def test_ledger_never_rewritten():
    decisions = build_fixture_decisions()
    bars = build_fixture_bars()
    d = decisions[0]
    snap = freeze_ledger_snapshot(d)
    replay_decision(d, bars)
    assert_ledger_unchanged(d, snap)
    mutated = dict(snap)
    mutated["size"] = float(snap["size"]) + 9
    with pytest.raises(HardBanViolation):
        assert_ledger_unchanged(d, mutated)


def test_all_paths_evaluated_with_comparability():
    result = run_counterfactual_replay()
    assert result["all_decisions_coverage_complete"] is True
    assert result["counterfactual_profit_is_not_real_performance"] is True
    assert result["is_real_performance"] is False
    assert result["profitability_claimed"] is False
    for r in result["replays"]:
        path_ids = {o["path_id"] for o in r["outcomes"]}
        assert "observed_baseline" in path_ids
        for p in ALTERNATE_PATHS:
            assert p in path_ids
        for o in r["outcomes"]:
            assert o["comparability"]
            assert o["coverage"]
            assert o["is_real_performance"] is False
            if o["executed"] and not o["blocked"]:
                assert o["cost_included"] is True
                assert o["slippage_cost"] is not None


def test_low_data_trust_blocks():
    result = run_counterfactual_replay()
    d2 = next(r for r in result["replays"] if r["decision_id"] == "V16B_DEC_002")
    block = next(o for o in d2["outcomes"] if o["path_id"] == "block_low_data_trust")
    assert block["blocked"] is True
    assert block["coverage"] == "LOW_DATA_TRUST"


def test_deterministic_replay():
    proof = deterministic_replay_proof(runs=3)
    assert proof["deterministic"] is True
    assert len(set(proof["fingerprints"])) == 1
    a = run_counterfactual_replay()
    b = run_counterfactual_replay()
    assert a["fingerprint"] == b["fingerprint"]


def test_refuse_apis():
    with pytest.raises(HardBanViolation):
        refuse_rewrite_real_ledger()
    with pytest.raises(HardBanViolation):
        refuse_counterfactual_as_real_performance()
    with pytest.raises(HardBanViolation):
        refuse_status_json_lane_artifact()
    with pytest.raises(HardBanViolation):
        refuse_status_report_artifact()


def test_banned_artifact_names():
    with pytest.raises(HardBanViolation):
        refuse_banned_artifact_names(["v16_counterfactual_replay_status.json"])
    with pytest.raises(HardBanViolation):
        refuse_banned_artifact_names(["SUMMARY.md"])
    refuse_banned_artifact_names(["deterministic_replay.json", "three_pass.json"])


def test_three_passes_pass():
    three = run_three_passes()
    assert three["all_passed"] is True
    assert three["lane_result"] == "PASS"
    assert three["wrote_status_json"] is False
    assert three["wrote_status_report"] is False
    assert len(three["passes"]) == 3
    assert all(p["passed"] for p in three["passes"])


def test_pass_helpers_on_fresh_bundle():
    replay = run_counterfactual_replay()
    bundle = {
        "replay": replay,
        "artifact_names": [
            "deterministic_replay.json",
            "three_pass.json",
            "fixture_manifest.json",
            "pytest_report.json",
        ],
    }
    assert pass1_core_integrity(bundle)["passed"] is True
    assert pass2_adversarial_leakage(bundle)["passed"] is True
    assert pass3_determinism_and_seal(bundle)["passed"] is True


def test_harness_writes_no_status(tmp_path: Path):
    # Evaluate then write into a temp tree mirroring ARTIFACT_REL under tmp by monkeypatching root.
    result = evaluate_counterfactual_engine(root=ROOT)
    assert result["lane_result"] == "PASS"
    written = write_immutable_artifacts(result, root=tmp_path, pytest_info={"passed": True, "tests": 1})
    names = list(written.keys())
    assert not any(n.endswith("_status.json") for n in names)
    assert "SUMMARY.md" not in names
    assert "deterministic_replay.json" in names
    assert "three_pass.json" in names
    for rel in written.values():
        assert (tmp_path / rel).is_file()


def test_pass2_rejects_false_real_performance_claim():
    replay = run_counterfactual_replay()
    poisoned = dict(replay)
    poisoned["profitability_claimed"] = True
    poisoned["is_real_performance"] = True
    bundle = {"replay": poisoned, "artifact_names": ["deterministic_replay.json"]}
    result = pass2_adversarial_leakage(bundle)
    assert result["passed"] is False
    ids = {f["id"] for f in result["findings"]}
    assert "P2_FALSE_PASS_PROFIT" in ids or "P2_FALSE_PASS_CF_SUM" in ids

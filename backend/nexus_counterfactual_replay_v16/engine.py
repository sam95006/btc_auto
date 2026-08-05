"""Deterministic Counterfactual Replay Engine (V16-B)."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_counterfactual_replay_v16.constants import (
    ALTERNATE_PATHS,
    DEFAULT_SEED,
    DISCLAIMER,
    HARD_BANS,
    REPLAY_LABEL,
    SCHEMA,
    SCHEMA_DETERMINISTIC,
    SCHEMA_REPLAY,
)
from backend.nexus_counterfactual_replay_v16.fixtures import (
    build_fixture_bars,
    build_fixture_decisions,
    fixture_manifest,
)
from backend.nexus_counterfactual_replay_v16.hard_bans import (
    assert_no_status_json_filenames,
    assert_no_status_report_filenames,
    hard_ban_inventory,
)
from backend.nexus_counterfactual_replay_v16.ledger_guard import (
    assert_ledger_unchanged,
    assert_outcome_not_real_performance,
    freeze_ledger_snapshot,
)
from backend.nexus_counterfactual_replay_v16.paths import evaluate_all_paths
from backend.nexus_counterfactual_replay_v16.pit import prove_pit_excludes_future
from backend.nexus_counterfactual_replay_v16.types import Bar, DecisionTrade


def _digest(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def replay_decision(
    decision: DecisionTrade,
    bars: list[Bar],
    *,
    ledger_snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate all alternate paths for one Decision/Trade.

    Never mutates the real ledger snapshot.
    """
    snap = freeze_ledger_snapshot(decision)
    if ledger_snapshots is not None:
        ledger_snapshots.append(snap)

    outcomes = evaluate_all_paths(decision, bars)
    # Prove ledger unchanged after CF evaluation.
    assert_ledger_unchanged(decision, snap)
    for o in outcomes:
        assert_outcome_not_real_performance(o.to_dict())

    path_ids = [o.path_id for o in outcomes]
    required = {"observed_baseline", *ALTERNATE_PATHS}
    missing = sorted(required - set(path_ids))

    return {
        "schema": SCHEMA_REPLAY,
        "decision_id": decision.decision_id,
        "trade_id": decision.trade_id,
        "symbol": decision.symbol,
        "ledger_fingerprint": snap["ledger_fingerprint"],
        "ledger_rewritten": False,
        "replay_label": REPLAY_LABEL,
        "disclaimer": DISCLAIMER,
        "path_count": len(outcomes),
        "required_paths_missing": missing,
        "coverage_complete": len(missing) == 0,
        "outcomes": [o.to_dict() for o in outcomes],
        "any_real_performance_claim": False,
        "counterfactual_profit_is_not_real_performance": True,
    }


def run_counterfactual_replay(
    *,
    seed: str = DEFAULT_SEED,
    decisions: list[DecisionTrade] | None = None,
    bars: list[Bar] | None = None,
) -> dict[str, Any]:
    """Full deterministic fixture replay across all decisions."""
    bars = bars if bars is not None else build_fixture_bars(seed=seed)
    decisions = decisions if decisions is not None else build_fixture_decisions(seed=seed)
    ledger_snapshots: list[dict[str, Any]] = []

    # PIT proof against the full bar set (includes injected future bar).
    as_of = max(d.exit_ts_ms for d in decisions)
    pit_proof = prove_pit_excludes_future(bars, as_of_ms=as_of)

    replays = [replay_decision(d, bars, ledger_snapshots=ledger_snapshots) for d in decisions]

    # Re-verify no ledger mutation across the campaign.
    for d, snap in zip(decisions, ledger_snapshots):
        assert_ledger_unchanged(d, snap)

    compact = {
        "seed": seed,
        "decision_count": len(decisions),
        "bar_count": len(bars),
        "pit_holds": pit_proof["pit_holds"],
        "replays": [
            {
                "decision_id": r["decision_id"],
                "trade_id": r["trade_id"],
                "path_count": r["path_count"],
                "coverage_complete": r["coverage_complete"],
                "ledger_rewritten": r["ledger_rewritten"],
                "outcome_digests": [_digest(o) for o in r["outcomes"]],
            }
            for r in replays
        ],
    }
    fingerprint = _digest(compact)

    return {
        "schema": SCHEMA,
        "seed": seed,
        "disclaimer": DISCLAIMER,
        "replay_label": REPLAY_LABEL,
        "hard_bans": list(HARD_BANS),
        "hard_ban_inventory": hard_ban_inventory(),
        "fixture_manifest": fixture_manifest(seed=seed),
        "pit_proof": pit_proof,
        "ledger_snapshots": ledger_snapshots,
        "ledger_rewritten": False,
        "replays": replays,
        "decision_count": len(decisions),
        "path_inventory": list(ALTERNATE_PATHS),
        "all_decisions_coverage_complete": all(r["coverage_complete"] for r in replays),
        "counterfactual_profit_is_not_real_performance": True,
        "profitability_claimed": False,
        "is_real_performance": False,
        "fingerprint": fingerprint,
        "deterministic": True,
    }


def deterministic_replay_proof(*, seed: str = DEFAULT_SEED, runs: int = 3) -> dict[str, Any]:
    fingerprints = []
    for _ in range(runs):
        result = run_counterfactual_replay(seed=seed)
        fingerprints.append(result["fingerprint"])
    return {
        "schema": SCHEMA_DETERMINISTIC,
        "seed": seed,
        "runs": runs,
        "fingerprints": fingerprints,
        "deterministic": len(set(fingerprints)) == 1,
        "fingerprint": fingerprints[0] if fingerprints else None,
    }


def refuse_banned_artifact_names(paths: list[str]) -> None:
    assert_no_status_json_filenames(paths)
    assert_no_status_report_filenames(paths)

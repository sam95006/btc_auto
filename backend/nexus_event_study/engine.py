"""V14-B blocked Event Study pipeline — fixtures + forensic RO only."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_event_study.bootstrap import bootstrap_mean_ci
from backend.nexus_event_study.completeness import filter_by_completeness
from backend.nexus_event_study.constants import (
    DEFAULT_HORIZONS,
    ENGINE_STATUS,
    REAL_EVENT_STUDY_EXECUTION,
    REAL_EVENT_STUDY_STATUS,
    REAL_STUDY_HOLD_CONDITIONS,
)
from backend.nexus_event_study.definitions import definition_catalog
from backend.nexus_event_study.fixtures import build_synthetic_cohort
from backend.nexus_event_study.grouping import summarize_groups
from backend.nexus_event_study.missing import classify_missing
from backend.nexus_event_study.outcomes import multi_horizon_outcomes, summarize_horizon_outcomes
from backend.nexus_event_study.overlap import exclude_overlapping
from backend.nexus_event_study.pit import filter_pit, prove_pit_excludes_future
from backend.nexus_event_study.types import StudyEvent
from backend.nexus_event_study.windows import build_windows, describe_window_policy


def _fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def run_blocked_fixture_study(
    *,
    seed: str = "v14b-default",
    as_of_ms: int | None = None,
    required_horizon: int = 16,
) -> dict[str, Any]:
    """Execute the full blocked engine on synthetic fixtures.

    Never claims real 14d Event Study execution. Outcomes are descriptive only.
    """
    if REAL_EVENT_STUDY_EXECUTION:
        raise RuntimeError("REAL_EVENT_STUDY_HARD_BLOCK: execution flag must remain False")

    cohort = build_synthetic_cohort(seed=seed)
    events: list[StudyEvent] = list(cohort["_events_objs"])
    paths: dict[str, list[float]] = dict(cohort["_paths_objs"])
    base_ts = int(cohort["base_ts_ms"])
    as_of = int(as_of_ms if as_of_ms is not None else base_ts + 800 * 60_000)

    missing = classify_missing(events, as_of_ms=as_of)
    valid = list(missing["valid"])

    pit_events = filter_pit(valid, as_of_ms=as_of)
    pit_proof = prove_pit_excludes_future(events, as_of_ms=as_of)

    overlap = exclude_overlapping(pit_events)
    after_overlap: list[StudyEvent] = list(overlap["kept"])

    completeness = filter_by_completeness(
        after_overlap,
        paths,
        required_horizon=required_horizon,
    )
    kept: list[StudyEvent] = list(completeness["kept"])

    windows = {e.observation_id: build_windows(e).to_dict() for e in kept}
    groups = summarize_groups(kept)

    outcomes_by_event: list[list[Any]] = []
    outcome_rows: list[dict[str, Any]] = []
    for ev in kept:
        outs = multi_horizon_outcomes(ev, paths[ev.observation_id], horizons=DEFAULT_HORIZONS)
        outcomes_by_event.append(outs)
        outcome_rows.append(
            {
                "observation_id": ev.observation_id,
                "event_id": ev.event_id,
                "symbol": ev.symbol,
                "regime": ev.regime,
                "outcomes": [o.to_dict() for o in outs],
            }
        )

    horizon_summaries = [
        summarize_horizon_outcomes(outcomes_by_event, horizon=h) for h in DEFAULT_HORIZONS
    ]
    # Bootstrap on available net returns at primary horizon.
    primary = 8
    nets = [
        o.net_return
        for bundle in outcomes_by_event
        for o in bundle
        if o.horizon == primary and o.available and o.net_return is not None
    ]
    boot = bootstrap_mean_ci(nets).to_dict()
    boot["profitability_claimed"] = False
    boot["inference_is_descriptive_only"] = True

    summary_payload = {
        "seed": seed,
        "as_of_ms": as_of,
        "input_event_count": len(events),
        "valid_count": missing["valid_count"],
        "missing_count": missing["missing_count"],
        "pit_eligible_count": len(pit_events),
        "overlap_kept_count": overlap["kept_count"],
        "overlap_excluded_count": overlap["excluded_count"],
        "completeness_kept_count": completeness["kept_count"],
        "completeness_dropped_count": completeness["dropped_count"],
        "horizon_summaries": horizon_summaries,
        "bootstrap_primary_horizon": primary,
        "bootstrap": boot,
        "group_summary": {
            k: v
            for k, v in groups.items()
            if k
            not in {
                # keep compact for fingerprint stability
            }
        },
        "engine_status": ENGINE_STATUS,
        "real_event_study_status": REAL_EVENT_STUDY_STATUS,
        "real_event_study_execution": False,
        "profitability_claimed": False,
        "is_trade": False,
    }

    return {
        "schema": "v14_b_blocked_fixture_study",
        "engine_status": ENGINE_STATUS,
        "real_event_study_status": REAL_EVENT_STUDY_STATUS,
        "real_event_study_execution": False,
        "fixture_checksum": cohort["fixture_checksum"],
        "definition_catalog": definition_catalog(),
        "window_policy": describe_window_policy(),
        "missing": {
            "valid_count": missing["valid_count"],
            "missing_count": missing["missing_count"],
            "missing": missing["missing"],
            "silent_impute": False,
        },
        "pit_proof": pit_proof,
        "overlap": {
            "input_count": overlap["input_count"],
            "kept_count": overlap["kept_count"],
            "excluded_count": overlap["excluded_count"],
            "excluded": overlap["excluded"],
        },
        "completeness": {
            "kept_count": completeness["kept_count"],
            "dropped_count": completeness["dropped_count"],
            "dropped": completeness["dropped"],
            "min_completeness": completeness["min_completeness"],
            "required_horizon": completeness["required_horizon"],
        },
        "windows": windows,
        "groups": groups,
        "outcomes": outcome_rows,
        "horizon_summaries": horizon_summaries,
        "bootstrap": boot,
        "hold_conditions": dict(REAL_STUDY_HOLD_CONDITIONS),
        "hold_conditions_satisfied": False,
        "summary": summary_payload,
        "fingerprint": _fingerprint(summary_payload),
        "profitability_claimed": False,
        "is_trade": False,
    }


def verify_deterministic_study(*, seed: str = "v14b-replay") -> dict[str, Any]:
    a = run_blocked_fixture_study(seed=seed)
    b = run_blocked_fixture_study(seed=seed)
    return {
        "schema": "v14_b_deterministic_study_proof",
        "seed": seed,
        "match": a["fingerprint"] == b["fingerprint"],
        "fingerprint": a["fingerprint"],
        "engine_status": ENGINE_STATUS,
        "real_event_study_status": REAL_EVENT_STUDY_STATUS,
        "real_event_study_execution": False,
    }

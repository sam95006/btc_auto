"""Development replay only — not formal Walk-forward.

Replays synthetic development bars deterministically for checksum binding.
Never touches reserved OOS, never places orders, never claims qualification.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.nexus_qualification.dryrun_v13.checksums import sha_obj


def _synthetic_dev_bars(candidate: dict[str, Any], *, seed: str) -> list[dict[str, Any]]:
    interval = candidate.get("development_interval") or {}
    start = int(interval.get("start_ms") or 0)
    end = int(interval.get("end_ms") or start)
    # Fixed small bar set — deterministic from candidate identity + seed.
    n = 8
    step = max(1, (end - start) // n) if end > start else 86_400_000
    bars: list[dict[str, Any]] = []
    base_px = 100.0 + (len(seed) % 17)
    for i in range(n):
        ts = start + i * step
        if ts > end:
            break
        bars.append(
            {
                "ts_ms": ts,
                "symbol": (candidate.get("eligible_symbol_profile") or ["SYNTHUSDT"])[0],
                "open": base_px + i * 0.1,
                "high": base_px + i * 0.1 + 0.5,
                "low": base_px + i * 0.1 - 0.5,
                "close": base_px + i * 0.1 + 0.05,
                "volume": 10.0 + i,
                "fixture_only": True,
            }
        )
    return bars


def run_development_replay(candidate: dict[str, Any], *, seed: str = "v13f-dev") -> dict[str, Any]:
    """Deterministic development replay. Formal WF remains unexecuted."""
    bars = _synthetic_dev_bars(candidate, seed=seed)
    fingerprint = sha_obj(
        {
            "candidate_id": candidate.get("candidate_id"),
            "semantic_checksum": candidate.get("semantic_checksum"),
            "parameter_checksum": candidate.get("parameter_checksum"),
            "code_checksum": candidate.get("code_checksum"),
            "dataset_checksum": candidate.get("dataset_checksum"),
            "bars": bars,
            "seed": seed,
        }
    )
    # Tiny deterministic "signal path" — not a trading result / not profitability.
    signal_path = [
        {
            "bar_index": i,
            "ts_ms": b["ts_ms"],
            "signal": 1 if (i % 3 == 0) else 0,
        }
        for i, b in enumerate(bars)
    ]
    return {
        "candidate_id": candidate.get("candidate_id"),
        "replay_kind": "DEVELOPMENT_ONLY",
        "formal_walk_forward": False,
        "bars": bars,
        "bar_count": len(bars),
        "signal_path": signal_path,
        "replay_fingerprint": fingerprint,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "oos_touched": False,
        "profitability_claimed": False,
        "fixture_only": True,
    }


def verify_development_replay_deterministic(
    candidate: dict[str, Any],
    *,
    seed: str = "v13f-dev",
) -> dict[str, Any]:
    a = run_development_replay(candidate, seed=seed)
    b = run_development_replay(candidate, seed=seed)
    match = a["replay_fingerprint"] == b["replay_fingerprint"]
    return {
        "candidate_id": candidate.get("candidate_id"),
        "match": match,
        "fingerprint": a["replay_fingerprint"],
        "a": {"bar_count": a["bar_count"], "fingerprint": a["replay_fingerprint"]},
        "b": {"bar_count": b["bar_count"], "fingerprint": b["replay_fingerprint"]},
    }


def replay_all_candidates(
    candidates: list[dict[str, Any]],
    *,
    seed: str = "v13f-dev",
) -> dict[str, Any]:
    replays = [run_development_replay(c, seed=seed) for c in candidates]
    verifications = [verify_development_replay_deterministic(c, seed=seed) for c in candidates]
    return {
        "replay_kind": "DEVELOPMENT_ONLY",
        "formal_walk_forward_executed": False,
        "candidate_count": len(candidates),
        "replays": replays,
        "verifications": verifications,
        "all_deterministic": all(v["match"] for v in verifications),
        "demo_order_count": sum(int(r["demo_order_count"]) for r in replays),
        "exchange_write_attempt_count": sum(int(r["exchange_write_attempt_count"]) for r in replays),
        "oos_touched": any(r["oos_touched"] for r in replays),
    }


def freeze_candidate_plan(candidate: dict[str, Any]) -> dict[str, Any]:
    """Candidate Freeze *plan* — stamps identity; formal freeze stage stays BLOCKED."""
    return {
        "candidate_id": candidate.get("candidate_id"),
        "freeze_status": "PLANNED_NOT_EXECUTED",
        "formal_stage": "CANDIDATE_FREEZE",
        "formal_stage_status": "BLOCKED",
        "semantic_checksum": candidate.get("semantic_checksum"),
        "parameter_checksum": candidate.get("parameter_checksum"),
        "code_checksum": candidate.get("code_checksum"),
        "dataset_checksum": candidate.get("dataset_checksum"),
        "discovery_label": candidate.get("discovery_label"),
        "qualified": False,
        "selected": False,
        "promoted": False,
        "fixture_only": True,
        "identity": {
            "candidate_id": candidate.get("candidate_id"),
            "semantic_mechanism_id": candidate.get("semantic_mechanism_id"),
            "preregistration_timestamp": candidate.get("preregistration_timestamp"),
        },
        "note": "Freeze plan prepared from Discovery outputs; formal Candidate Freeze remains BLOCKED.",
    }


def freeze_all_candidates(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    plans = [freeze_candidate_plan(c) for c in candidates]
    return {
        "freeze_plan_count": len(plans),
        "formal_candidate_freeze_executed": False,
        "plans": deepcopy(plans),
        "all_blocked": True,
    }

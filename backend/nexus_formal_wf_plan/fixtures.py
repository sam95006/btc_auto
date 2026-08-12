"""Synthetic development candidates for V15-F plan compilation fixtures."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_formal_wf_plan.constants import MS_PER_DAY


def _sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def synthetic_candidate(
    *,
    candidate_id: str = "SYN_V15F_WF_CAND_001",
    as_of_ms: int = 1_700_000_000_000,
) -> dict[str, Any]:
    params = {"lookback": 24, "threshold": 0.15, "fixture_marker": True}
    code_ref = "backend/nexus_formal_wf_plan"
    dataset_id = "SYNTHETIC_DEV_DATASET_V15F"
    start = as_of_ms - 365 * MS_PER_DAY
    end = as_of_ms - 60 * MS_PER_DAY
    cand = {
        "candidate_id": candidate_id,
        "candidate_label": "synthetic_development_fixture_not_qualified",
        "discovery_label": "DEVELOPMENT_PROMISING_NOT_QUALIFIED",
        "fixture_only": True,
        "selected": False,
        "promoted": False,
        "parameters": params,
        "parameter_checksum": _sha(params),
        "code_ref": code_ref,
        "code_checksum": _sha({"code_ref": code_ref}),
        "dataset_id": dataset_id,
        "dataset_ref": dataset_id,
        "dataset_checksum": _sha({"dataset_id": dataset_id}),
        "cost_version": "private_core.cost_model_v1_1",
        "cost_model_version": "private_core.cost_model_v1_1",
        "risk_version": "private_core.risk.gates_v1_1",
        "execution_version": "AutonomousExecutionSimulatorV11",
        "semantic_mechanism": "synthetic_non_trading_placeholder",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "development_interval": {
            "start_ms": start,
            "end_ms": end,
            "category": "DEVELOPMENT",
        },
        "regime_requirements": {
            "required_regimes": ["TRENDING", "MEAN_REVERTING", "HIGH_VOL"],
            "min_regimes_covered": 2,
        },
        "symbol_requirements": {
            "required_symbols": ["BTCUSDT", "ETHUSDT"],
            "min_symbols": 2,
        },
        "failure_thresholds": {
            "max_drawdown_pct": 20.0,
            "min_positive_fold_ratio": 0.5,
        },
        "minimum_sample_sizes": {
            "min_train_bars": 500,
            "min_validation_bars": 100,
        },
    }
    cand["semantic_checksum"] = _sha(
        {
            "candidate_id": cand["candidate_id"],
            "semantic_mechanism": cand["semantic_mechanism"],
            "parameter_checksum": cand["parameter_checksum"],
            "dataset_checksum": cand["dataset_checksum"],
            "code_checksum": cand["code_checksum"],
        }
    )
    return cand


def synthetic_candidate_bundle(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, Any]:
    cands = [
        synthetic_candidate(candidate_id="SYN_V15F_WF_CAND_001", as_of_ms=as_of_ms),
        synthetic_candidate(candidate_id="SYN_V15F_WF_CAND_002", as_of_ms=as_of_ms),
    ]
    # Second candidate: shorter development window → fewer folds.
    cands[1]["development_interval"] = {
        "start_ms": as_of_ms - 180 * MS_PER_DAY,
        "end_ms": as_of_ms - 60 * MS_PER_DAY,
        "category": "DEVELOPMENT",
    }
    cands[1]["symbols"] = ["BTCUSDT"]
    cands[1]["symbol_requirements"] = {
        "required_symbols": ["BTCUSDT"],
        "min_symbols": 1,
    }
    return {
        "schema": "NEXUS_V15F_WF_PLAN_CANDIDATE_BUNDLE",
        "as_of_ms": as_of_ms,
        "fixture_only": True,
        "candidates": cands,
        "formal_walk_forward_executed": False,
    }

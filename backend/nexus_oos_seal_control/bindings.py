"""Binding surfaces: candidate, code, parameter, dataset."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.nexus_oos_seal_control.constants import BINDING_KINDS
from backend.nexus_oos_seal_control.intervals import sha_obj


def synthetic_candidate() -> dict[str, Any]:
    return {
        "candidate_id": "SYNTHETIC_V15G_OOS_PLAN_CANDIDATE",
        "candidate_label": "synthetic_fixture_not_selected",
        "model_family": "other_models_synthetic_fixture",
        "strategy_family": "SYNTHETIC_OOS_SEAL_CONTROL_FAMILY",
        "economic_mechanism": "synthetic_non_trading_placeholder",
        "parameters": {"lookback": 24, "threshold": 0.0, "fixture_marker": True},
        "parameter_source": "synthetic_fixture",
        "code_ref": "backend/nexus_oos_seal_control",
        "dataset_ref": "SYNTHETIC_V15G_PLAN_DATASET",
        "preregistration_timestamp": "2026-01-01T00:00:00Z",
        "fixture_only": True,
        "selected": False,
        "promoted": False,
        "qualified": False,
    }


def synthetic_dataset(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, Any]:
    source_ts = as_of_ms - 14 * 86_400_000
    retrieval_ts = as_of_ms - 7 * 86_400_000
    availability_ts = as_of_ms - 6 * 86_400_000
    records = [
        {
            "record_id": "SYN_V15G_BAR_001",
            "symbol": "SYNTHUSDT",
            "source_timestamp_ms": source_ts,
            "retrieval_timestamp_ms": retrieval_ts,
            "availability_timestamp_ms": availability_ts,
            "available_as_of_ms": availability_ts,
            "value_kind": "synthetic_ohlcv_bar",
            "fixture_only": True,
        }
    ]
    dataset = {
        "dataset_id": "SYNTHETIC_V15G_PLAN_DATASET",
        "dataset_version": "v15g.synthetic.1",
        "source": "synthetic_fixture_generator",
        "source_timestamp_ms": source_ts,
        "retrieval_timestamp_ms": retrieval_ts,
        "availability_timestamp_ms": availability_ts,
        "as_of_ms": as_of_ms,
        "records": records,
        "real_market_data": False,
        "fixture_only": True,
    }
    dataset["dataset_checksum"] = sha_obj(records)
    dataset["dataset_semantic_checksum"] = sha_obj(
        {
            "dataset_id": dataset["dataset_id"],
            "dataset_version": dataset["dataset_version"],
            "source": dataset["source"],
            "record_shapes": [
                {
                    "symbol": r["symbol"],
                    "value_kind": r["value_kind"],
                    "available_as_of_ms": r["available_as_of_ms"],
                }
                for r in records
            ],
        }
    )
    return dataset


def compute_code_checksum(root: Path | None = None) -> str:
    base = Path(root) if root is not None else Path(__file__).resolve().parent
    payload: list[dict[str, str]] = []
    for path in sorted(base.glob("*.py")):
        payload.append(
            {"path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    return sha_obj(payload)


def build_bindings(
    candidate: dict[str, Any],
    dataset: dict[str, Any],
    *,
    code_checksum: str,
    plan_checksum: str,
) -> dict[str, Any]:
    candidate_binding = {
        "kind": "candidate",
        "candidate_id": candidate["candidate_id"],
        "candidate_checksum": sha_obj(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_label": candidate["candidate_label"],
                "fixture_only": candidate["fixture_only"],
                "preregistration_timestamp": candidate["preregistration_timestamp"],
            }
        ),
        "candidate_semantic_checksum": sha_obj(
            {
                "model_family": candidate["model_family"],
                "strategy_family": candidate["strategy_family"],
                "economic_mechanism": candidate["economic_mechanism"],
                "dataset_ref": candidate["dataset_ref"],
                "code_ref": candidate["code_ref"],
            }
        ),
    }
    code_binding = {
        "kind": "code",
        "code_ref": candidate["code_ref"],
        "code_checksum": code_checksum,
    }
    parameter_binding = {
        "kind": "parameter",
        "parameter_source": candidate["parameter_source"],
        "parameter_checksum": sha_obj(candidate["parameters"]),
        "parameters": dict(candidate["parameters"]),
    }
    dataset_binding = {
        "kind": "dataset",
        "dataset_id": dataset["dataset_id"],
        "dataset_checksum": dataset["dataset_checksum"],
        "dataset_semantic_checksum": dataset["dataset_semantic_checksum"],
        "fixture_only": True,
        "real_market_data": False,
    }
    bindings = {
        "candidate": candidate_binding,
        "code": code_binding,
        "parameter": parameter_binding,
        "dataset": dataset_binding,
        "plan_checksum": plan_checksum,
        "binding_kinds_present": list(BINDING_KINDS),
        "all_required_bindings_present": set(BINDING_KINDS)
        <= {"candidate", "code", "parameter", "dataset"},
    }
    bindings["bindings_checksum"] = sha_obj(
        {
            "candidate": candidate_binding,
            "code": code_binding,
            "parameter": {k: v for k, v in parameter_binding.items() if k != "parameters"},
            "dataset": dataset_binding,
            "plan_checksum": plan_checksum,
        }
    )
    return bindings


def verify_bindings_intact(bindings: dict[str, Any]) -> dict[str, Any]:
    required = set(BINDING_KINDS)
    present = set(bindings.get("binding_kinds_present") or [])
    missing = sorted(required - present)
    recomputed = sha_obj(
        {
            "candidate": bindings.get("candidate"),
            "code": bindings.get("code"),
            "parameter": {
                k: v
                for k, v in (bindings.get("parameter") or {}).items()
                if k != "parameters"
            },
            "dataset": bindings.get("dataset"),
            "plan_checksum": bindings.get("plan_checksum"),
        }
    )
    intact = (
        not missing
        and recomputed == bindings.get("bindings_checksum")
        and bindings.get("all_required_bindings_present") is True
    )
    return {
        "intact": intact,
        "missing_kinds": missing,
        "expected_bindings_checksum": recomputed,
        "provided_bindings_checksum": bindings.get("bindings_checksum"),
    }

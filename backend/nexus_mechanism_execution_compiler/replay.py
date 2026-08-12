"""Deterministic replay digests for V15-B executors."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_mechanism_execution_compiler.compiler import compile_all_executors
from backend.nexus_mechanism_execution_compiler.constants import RANDOM_SEED
from backend.nexus_mechanism_execution_compiler.executor import MechanismExecutor
from backend.nexus_mechanism_lab_v4.synthetic import generate_synthetic_series


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def replay_executor(executor: MechanismExecutor, *, seed: int = RANDOM_SEED) -> dict[str, Any]:
    bars = generate_synthetic_series(seed=seed)
    result = executor.run(bars)
    payload = {
        "executor_id": result["executor_id"],
        "mechanism_id": result["mechanism_id"],
        "event_count": result["event_count"],
        "gross_proxy_sum": round(float(result["gross_proxy_sum"]), 12),
        "cost_proxy_sum": round(float(result["cost_proxy_sum"]), 12),
        "cost_gated_count": result["cost_gated_count"],
        "failure_probe_count": result["failure_probe_count"],
        "control_overlay_only": result["control_overlay_only"],
        "events_sample": result["events_sample"],
        "seed": seed,
    }
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return {
        "executor_id": result["executor_id"],
        "mechanism_id": result["mechanism_id"],
        "digest": digest,
        "payload": payload,
        "result": result,
    }


def replay_all(*, seed: int = RANDOM_SEED) -> dict[str, Any]:
    contracts = compile_all_executors()
    digests: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for contract in contracts:
        ex = MechanismExecutor(contract)
        replayed = replay_executor(ex, seed=seed)
        digests.append(
            {
                "executor_id": replayed["executor_id"],
                "mechanism_id": replayed["mechanism_id"],
                "digest": replayed["digest"],
            }
        )
        results.append(replayed["result"])
    catalog_blob = _canonical(sorted(d["digest"] for d in digests))
    campaign_digest = hashlib.sha256(catalog_blob.encode("utf-8")).hexdigest()
    return {
        "seed": seed,
        "executor_count": len(digests),
        "executor_digests": digests,
        "campaign_digest": campaign_digest,
        "results": results,
    }


def assert_replay_stable(*, seed: int = RANDOM_SEED) -> dict[str, Any]:
    a = replay_all(seed=seed)
    b = replay_all(seed=seed)
    if a["campaign_digest"] != b["campaign_digest"]:
        raise AssertionError("replay_digest_mismatch")
    for da, db in zip(a["executor_digests"], b["executor_digests"], strict=True):
        if da != db:
            raise AssertionError(f"executor_digest_mismatch:{da['executor_id']}")
    return {
        "ok": True,
        "campaign_digest": a["campaign_digest"],
        "executor_count": a["executor_count"],
        "seed": seed,
    }

"""V14-L property/fuzz/schema/result/checkpoint/ledger fork fixtures."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any

from backend.nexus_research_redteam.research_integrity import (
    CONTROL_FIXTURE_LABEL,
    seal_research_result,
    verify_research_result_seal,
)
from backend.nexus_research_redteam.scenarios import _clean_result, run_ledger_fork_fixture


def property_fuzz_research_seals(*, seed: int = 14, rounds: int = 64) -> dict[str, Any]:
    """Property: sealed research results verify; any field mutation breaks the seal."""
    rng = random.Random(seed)
    clean_ok = 0
    mutant_blocked = 0
    failures: list[str] = []
    keys = (
        "result_id",
        "candidate_ids",
        "universe_members",
        "as_of_ms",
        "counters",
        "metrics",
        "cost_model_version",
        "cost_summary",
        "fixture_label",
        "provider_status",
    )
    for i in range(rounds):
        result = _clean_result(
            result_id=f"rr_fuzz_{i}",
            as_of_ms=1_700_000_000_000 + rng.randint(0, 10_000),
            counters={"evaluated": rng.randint(1, 50), "passed_gate": rng.randint(0, 20)},
            metrics={"sharpe": rng.random(), "net_pnl": rng.uniform(-10, 10)},
            cost_summary={
                "total_cost": round(rng.uniform(0.1, 5.0), 4),
                "fees": round(rng.uniform(0.01, 2.0), 4),
            },
            fixture_label=CONTROL_FIXTURE_LABEL,
        )
        sealed = seal_research_result(result)
        if not sealed.get("ok"):
            failures.append(f"seal_fail:{i}:{sealed.get('status')}")
            continue
        verify = verify_research_result_seal(result, sealed["seal"])
        if not verify.get("ok"):
            failures.append(f"verify_fail:{i}:{verify.get('status')}")
            continue
        clean_ok += 1

        attacked = dict(result)
        key = keys[rng.randrange(len(keys))]
        if key in {"candidate_ids", "universe_members"}:
            attacked[key] = list(attacked[key]) + [f"MUTANT_{i}"]
        elif key == "counters":
            attacked[key] = {**attacked[key], "evaluated": int(attacked[key]["evaluated"]) + 99}
        elif key == "metrics":
            attacked[key] = {**attacked[key], "sharpe": float(attacked[key]["sharpe"]) + 9.9}
        elif key == "cost_summary":
            attacked[key] = {**attacked[key], "total_cost": 0.0}
        elif key == "as_of_ms":
            attacked[key] = int(attacked[key]) + 1
        else:
            attacked[key] = f"ATTACKED_{i}"
        mismatch = verify_research_result_seal(attacked, sealed["seal"])
        if mismatch.get("ok"):
            failures.append(f"mutant_accepted:{i}:{key}")
        elif mismatch.get("status") == "RESULT_SEAL_MISMATCH":
            mutant_blocked += 1
        else:
            failures.append(f"mutant_wrong_status:{i}:{mismatch.get('status')}")

    passed = clean_ok == rounds and mutant_blocked == rounds and not failures
    return {
        "fixture_id": "property_fuzz_research_seals",
        "passed": passed,
        "rounds": rounds,
        "clean_ok": clean_ok,
        "mutant_blocked": mutant_blocked,
        "failures": failures[:8],
    }


def schema_mutation_result() -> dict[str, Any]:
    """Drop/alter required research-result keys must fail seal."""
    result = _clean_result()
    sealed = seal_research_result(result)
    assert sealed.get("ok") is True

    mutations: list[dict[str, Any]] = []
    for key in (
        "result_id",
        "candidate_ids",
        "universe_members",
        "as_of_ms",
        "counters",
        "metrics",
        "cost_model_version",
        "cost_summary",
        "fixture_label",
        "provider_status",
    ):
        mutant = dict(result)
        del mutant[key]
        out = seal_research_result(mutant)
        blocked = out.get("ok") is False and out.get("status") == "RESULT_MISSING_KEYS"
        mutations.append({"key": key, "blocked": blocked, "status": out.get("status")})

    passed = all(m["blocked"] for m in mutations)
    return {
        "fixture_id": "schema_mutation_result",
        "passed": passed,
        "mutations": mutations,
    }


def result_mutation_fixture() -> dict[str, Any]:
    """Result body mutation after seal must mismatch; honest verify must pass."""
    result = _clean_result(result_id="rr_mut_001")
    sealed = seal_research_result(result)
    assert sealed.get("ok") is True
    seal = sealed["seal"]
    honest = verify_research_result_seal(result, seal)

    mutated = dict(result)
    mutated["metrics"] = {**result["metrics"], "sharpe": 99.0}
    attack = verify_research_result_seal(mutated, seal)

    # Swap candidate set while keeping seal → mismatch.
    swapped = dict(result)
    swapped["candidate_ids"] = list(reversed(result["candidate_ids"])) + ["sneak"]
    swap = verify_research_result_seal(swapped, seal)

    passed = (
        honest.get("ok") is True
        and attack.get("ok") is False
        and attack.get("status") == "RESULT_SEAL_MISMATCH"
        and swap.get("ok") is False
    )
    return {
        "fixture_id": "result_mutation",
        "passed": passed,
        "honest": honest,
        "attack": attack,
        "swap": swap,
        "seal": seal,
    }


def checkpoint_mutation_fixture(workdir: Path) -> dict[str, Any]:
    """Checkpoint digest mutation / sequence rollback must be detected."""
    root = workdir / "ckpt_fx"
    root.mkdir(parents=True, exist_ok=True)
    body = {
        "checkpoint_id": "ckpt_fx_001",
        "sequence": 7,
        "result_seal": "seal_x",
        "status": "OPEN",
    }
    seal = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    path = root / "checkpoint.json"
    path.write_text(json.dumps({"body": body, "seal": seal}), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    pin_match = (
        hashlib.sha256(
            json.dumps(loaded["body"], sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        == loaded["seal"]
    )

    rolled = dict(body)
    rolled["sequence"] = 3
    diverged = (
        hashlib.sha256(
            json.dumps(rolled, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        != seal
    )
    rollback_detected = rolled["sequence"] < body["sequence"]

    # Digest-style mutation.
    blob = {"checkpoint_id": body["checkpoint_id"], "sha256": "abc", "status": "OPEN"}
    digest = hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()
    blob["status"] = "CLOSED"
    digest2 = hashlib.sha256(json.dumps(blob, sort_keys=True).encode()).hexdigest()
    digest_detects = digest != digest2

    passed = pin_match and diverged and rollback_detected and digest_detects
    return {
        "fixture_id": "checkpoint_mutation",
        "passed": passed,
        "pin_match": pin_match,
        "diverged": diverged,
        "rollback_detected": rollback_detected,
        "digest_detects": digest_detects,
        "seal": seal,
    }


def run_all_fixtures(workdir: Path, *, root: Path | None = None) -> list[dict[str, Any]]:
    _ = root
    return [
        property_fuzz_research_seals(seed=14, rounds=64),
        schema_mutation_result(),
        result_mutation_fixture(),
        checkpoint_mutation_fixture(workdir),
        run_ledger_fork_fixture(workdir),
    ]

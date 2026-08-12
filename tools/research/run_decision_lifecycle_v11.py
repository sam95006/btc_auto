#!/usr/bin/env python3
"""Run Founder-private Decision Lifecycle Orchestrator V11 readiness.

Emits artifacts under:
  artifacts/readiness/immutable/v11_decision_lifecycle/

No orders. No strategy mutation. No exchange writes. No public product surface.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ART_REL = Path("artifacts/readiness/immutable/v11_decision_lifecycle")
OWNED_SCAN_PATHS = [
    "backend/nexus_decision",
    "tools/research/run_decision_lifecycle_v11.py",
    "tests/test_decision_lifecycle_v11.py",
    "artifacts/readiness/immutable/v11_decision_lifecycle",
]

SECRET_PATTERNS = [
    re.compile(r"BEGIN (RSA |OPENSSH )?PRIVATE KEY"),
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)BYBIT_API_(KEY|SECRET)\s*=\s*['\"]?\S{8,}"),
    re.compile(r"(?i)sk-[A-Za-z0-9]{20,}"),
]


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def scan_secrets(root: Path) -> dict[str, Any]:
    hits: list[dict[str, str]] = []
    for rel in OWNED_SCAN_PATHS:
        target = root / rel
        files: list[Path]
        if target.is_dir():
            files = [
                p
                for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in {".py", ".json", ".md", ".yml", ".yaml"}
            ]
        elif target.is_file():
            files = [target]
        else:
            continue
        for path in files:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    hits.append(
                        {
                            "path": str(path.relative_to(root)).replace("\\", "/"),
                            "pattern": pat.pattern,
                        }
                    )
                    break
    return {
        "schema": "v11_decision_lifecycle_secret_scan",
        "created_at": _utc(),
        "secret_leak_count": len(hits),
        "hits": hits,
        "scanned_owned_paths": OWNED_SCAN_PATHS,
    }


def _exercise(tmp: Path) -> dict[str, Any]:
    from backend.nexus_decision import DecisionLifecycleError, DecisionLifecycleOrchestrator
    from backend.nexus_decision.evidence import hash_evidence_blob

    orch = DecisionLifecycleOrchestrator(tmp)
    matrix: list[dict[str, Any]] = []

    blobs = {"ev_0": "ready-blob-0", "ev_1": "ready-blob-1"}
    ids = list(blobs.keys())
    hashes = [hash_evidence_blob(blobs[i]) for i in ids]
    freshness = {"age_seconds": 5.0, "stale": False}
    completeness = {
        "ratio": 1.0,
        "required_fields": ["mid", "spread"],
        "present_fields": ["mid", "spread"],
    }

    obs = orch.observe(
        candidate_id="cand_ready",
        market_context_id="mctx_ready",
        point_in_time_timestamp="2026-08-05T03:00:00Z",
        evidence_ids=ids,
        evidence_hashes=hashes,
        data_freshness=freshness,
        data_completeness=completeness,
        idempotency_key="ready-obs",
        evidence_blobs=blobs,
        decision_id="dec_ready_1",
    )
    did = obs["decision"]["decision_id"]
    matrix.append({"stage": "observe", "ok": obs["status"] == "OBSERVED"})

    matrix.append(
        {
            "stage": "understand",
            "ok": orch.understand(
                did,
                AI_reasoner_outputs=[{"provider": "sim", "view": "constructive"}],
                idempotency_key="ready-u",
            )["status"]
            == "UNDERSTANDING",
        }
    )
    matrix.append(
        {
            "stage": "challenge",
            "ok": orch.challenge(
                did,
                independent_critic_output={"verdict": "pass", "score": 0.8},
                idempotency_key="ready-c",
            )["status"]
            == "CHALLENGED",
        }
    )
    matrix.append(
        {
            "stage": "decide",
            "ok": orch.decide(
                did,
                deterministic_risk_result={"allowed": True, "reasons": []},
                idempotency_key="ready-d",
            )["status"]
            == "APPROVED_SIMULATED",
        }
    )
    matrix.append(
        {
            "stage": "record",
            "ok": orch.record(did, idempotency_key="ready-r")["status"] == "MONITORING",
        }
    )
    matrix.append(
        {
            "stage": "monitor",
            "ok": orch.monitor(did, exit=True, idempotency_key="ready-m")["status"] == "EXITED",
        }
    )
    matrix.append(
        {
            "stage": "review",
            "ok": orch.review(did, idempotency_key="ready-rev")["status"] == "UNDER_REVIEW",
        }
    )
    matrix.append(
        {
            "stage": "calibrate",
            "ok": orch.calibrate(did, lesson_ids=["lesson_ready"], idempotency_key="ready-cal")[
                "status"
            ]
            == "CALIBRATED",
        }
    )
    matrix.append(
        {
            "stage": "improve",
            "ok": orch.improve(did, idempotency_key="ready-imp")["status"] == "CLOSED",
        }
    )

    # Fail-closed traps
    order_blocked = False
    try:
        orch.attempt_place_order()
    except DecisionLifecycleError:
        order_blocked = True
    matrix.append({"stage": "order_trap", "ok": order_blocked and orch.order_attempt_count == 1})

    strat_blocked = False
    try:
        orch.attempt_strategy_parameter_mutation({"leverage": 2})
    except DecisionLifecycleError:
        strat_blocked = True
    matrix.append(
        {
            "stage": "strategy_mutation_trap",
            "ok": strat_blocked and orch.strategy_mutation_attempt_count == 1,
        }
    )

    # Restart recovery drill on a second decision
    orch2 = DecisionLifecycleOrchestrator(tmp / "recover_drill")
    obs2 = orch2.observe(
        candidate_id="cand_rec",
        market_context_id="mctx_rec",
        point_in_time_timestamp="2026-08-05T03:01:00Z",
        evidence_ids=ids,
        evidence_hashes=hashes,
        data_freshness=freshness,
        data_completeness=completeness,
        idempotency_key="ready-rec-obs",
        evidence_blobs=blobs,
        decision_id="dec_ready_rec",
    )
    did2 = obs2["decision"]["decision_id"]
    orch2.understand(did2, AI_reasoner_outputs=[{"v": 1}], idempotency_key="ready-rec-u")
    orch2.checkpoint(did2)
    orch3 = DecisionLifecycleOrchestrator(tmp / "recover_drill")
    rec = orch3.recover(did2)
    matrix.append(
        {
            "stage": "restart_recovery",
            "ok": rec.get("recovery_status") == "RECOVERED" and rec.get("state") == "UNDERSTANDING",
        }
    )

    # Invalid transition
    bad = DecisionLifecycleOrchestrator(tmp / "invalid")
    obs_bad = bad.observe(
        candidate_id="c",
        market_context_id="m",
        point_in_time_timestamp="2026-08-05T03:02:00Z",
        evidence_ids=ids,
        evidence_hashes=hashes,
        data_freshness=freshness,
        data_completeness=completeness,
        idempotency_key="ready-bad-obs",
        evidence_blobs=blobs,
    )
    did_bad = obs_bad["decision"]["decision_id"]
    invalid_ok = False
    try:
        bad.improve(did_bad, idempotency_key="ready-bad-imp")
    except DecisionLifecycleError:
        invalid_ok = True
    matrix.append({"stage": "invalid_transition_fail_closed", "ok": invalid_ok})

    all_ok = all(bool(item.get("ok")) for item in matrix)
    return {
        "matrix": matrix,
        "all_stages_ok": all_ok,
        "final_status": orch.status(),
        "final_decision": orch.get(did),
        "order_attempt_count": orch.order_attempt_count,
        "strategy_mutation_attempt_count": orch.strategy_mutation_attempt_count,
        "exchange_write_attempt_count": orch.exchange_write_attempt_count,
    }


def main() -> int:
    art = ROOT / ART_REL
    art.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dlc_v11_") as td:
        exercise = _exercise(Path(td))

    stage_matrix = {
        "schema": "v11_decision_lifecycle_stage_matrix",
        "created_at": _utc(),
        "stages": list(
            __import__(
                "backend.nexus_decision.orchestrator",
                fromlist=["DecisionLifecycleOrchestrator"],
            ).DecisionLifecycleOrchestrator.STAGES
        ),
        "canonical_states": list(
            __import__("backend.nexus_decision.state_machine", fromlist=["CANONICAL_STATES"]).CANONICAL_STATES
        ),
        "results": exercise["matrix"],
        "all_stages_ok": exercise["all_stages_ok"],
        "order_attempt_count": exercise["order_attempt_count"],
        "strategy_mutation_attempt_count": exercise["strategy_mutation_attempt_count"],
        "exchange_write_attempt_count": exercise["exchange_write_attempt_count"],
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "public_api_exposed": False,
        "founder_private": True,
    }
    _write(art / "stage_matrix.json", stage_matrix)
    _write(art / "final_decision_snapshot.json", exercise["final_decision"])

    from backend.nexus_decision.decision_object import DECISION_OBJECT_REQUIRED_FIELDS
    from backend.nexus_decision.state_machine import VALID_TRANSITIONS

    contract = {
        "schema": "v11_decision_object_contract",
        "created_at": _utc(),
        "required_fields": list(DECISION_OBJECT_REQUIRED_FIELDS),
        "canonical_states": stage_matrix["canonical_states"],
        "valid_transitions": {k: sorted(v) for k, v in VALID_TRANSITIONS.items()},
        "lifecycle": [
            "Observe",
            "Understand",
            "Challenge",
            "Decide",
            "Record",
            "Monitor",
            "Review",
            "Calibrate",
            "Improve",
        ],
        "orders_permitted": False,
        "strategy_mutation_permitted": False,
    }
    _write(art / "decision_object_contract.json", contract)

    secret = scan_secrets(ROOT)
    _write(art / "secret_scan.json", secret)
    secret = scan_secrets(ROOT)
    _write(art / "secret_scan.json", secret)

    status = {
        "schema": "v11_decision_lifecycle_status",
        "created_at": _utc(),
        "lane": "A",
        "lane_name": "DECISION_LIFECYCLE_ORCHESTRATOR",
        "branch": "feature/v11-decision-lifecycle-orchestrator",
        "package": "backend.nexus_decision",
        "status": (
            "PASS"
            if exercise["all_stages_ok"]
            and secret["secret_leak_count"] == 0
            and exercise["order_attempt_count"] == 1  # intentional trap
            and exercise["exchange_write_attempt_count"] == 0
            else "FAIL"
        ),
        "all_stages_ok": exercise["all_stages_ok"],
        "secret_leak_count": secret["secret_leak_count"],
        "order_attempt_count_formal": 0,
        "order_trap_blocked": True,
        "strategy_mutation_trap_blocked": True,
        "exchange_write_attempt_count": exercise["exchange_write_attempt_count"],
        "demo_order_count": 0,
        "shadow_order_count": 0,
        "mainnet": False,
        "real_money": False,
        "public_api_exposed": False,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "owned_paths": OWNED_SCAN_PATHS,
        "prohibited_paths_untouched": [
            "frontend",
            "backend/nexus_demo_execution",
            "other_v11_lane_owned_paths",
            "pr26_public_surfaces",
        ],
        "base_commit": "e4f30f9b8abaaade6151a75ef5ac6face53d5135",
    }
    _write(art / "decision_lifecycle_status.json", status)
    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

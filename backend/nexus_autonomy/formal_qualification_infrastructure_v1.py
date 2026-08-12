"""NEXUS_FORMAL_QUALIFICATION_INFRASTRUCTURE_V1

Infrastructure-only state machine for a *future* candidate qualification path:

  Candidate Freeze → Replay → chronological Walk-forward → concentration review
  → cost stress → Risk Review → untouched OOS reservation → OOS execution
  authorization → Demo eligibility

ALL stages default to BLOCKED.

Does NOT:
  - execute formal Walk-forward
  - download or execute OOS
  - place Demo / Shadow / exchange orders
  - select or promote a real strategy

Synthetic fixtures only.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_autonomy.qualification_checksums import (
    stamp_checksums,
    validate_checksums,
)
from backend.nexus_autonomy.qualification_interval_registry import (
    IntervalRecord,
    IntervalRegistry,
    assert_future_data_excluded,
    assert_no_overlap_with_consumed,
    build_empty_registries,
    prove_oos_non_consumption,
)
from backend.nexus_autonomy.qualification_promotion_sm import (
    QUALIFICATION_STAGES,
    STAGE_STATUS_BLOCKED,
    FounderAuthorizationGate,
    PromotionStateMachine,
)

SCHEMA_ID = "NEXUS_FORMAL_QUALIFICATION_INFRASTRUCTURE_V1"
INFRA_STATUS_BLOCKED_READY = "BLOCKED_READY"
ARTIFACT_REL = Path("artifacts/readiness/immutable/formal_qualification_infrastructure_v1")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def synthetic_candidate_fixture() -> dict[str, Any]:
    """Non-selected synthetic candidate — fixture_only=True always."""
    return {
        "candidate_id": "SYNTHETIC_QUAL_CANDIDATE_V1",
        "candidate_label": "synthetic_fixture_not_selected",
        "strategy_family": "SYNTHETIC_FAMILY",
        "economic_mechanism": "SYNTHETIC_MECHANISM_PLACEHOLDER",
        "required_data_capabilities": ["ohlcv_1h"],
        "eligible_symbol_profile": ["SYNTHUSDT"],
        "eligible_regimes": ["synthetic_regime"],
        "context_timeframe": "240",
        "event_timeframe": "60",
        "entry_timeframe": "15",
        "parameter_source": "synthetic_fixture",
        "economic_rationale": "infrastructure_dry_run_only",
        "parameters": {
            "lookback": 20,
            "threshold": 0.0,
            "fixture_marker": True,
        },
        "preregistration_timestamp": "2026-01-01T00:00:00Z",
        "fixture_only": True,
        "selected": False,
        "promoted": False,
    }


def synthetic_interval_fixture(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, IntervalRegistry]:
    """Build non-overlapping data / consumed / reserved registries."""
    regs = build_empty_registries()
    # Historical development data (closed, before as_of)
    regs["data"].add(
        IntervalRecord(
            interval_id="SYN_DATA_DEV_001",
            label="synthetic_development",
            start_ms=as_of_ms - 90 * 86_400_000,
            end_ms=as_of_ms - 40 * 86_400_000,
            category="data",
        )
    )
    regs["consumed"].add(
        IntervalRecord(
            interval_id="SYN_CONSUMED_001",
            label="synthetic_consumed_research",
            start_ms=as_of_ms - 90 * 86_400_000,
            end_ms=as_of_ms - 40 * 86_400_000,
            category="consumed",
        )
    )
    # Untouched OOS reservation — after consumed, still before as_of
    regs["reserved"].add(
        IntervalRecord(
            interval_id="SYN_OOS_RESERVED_001",
            label="synthetic_untouched_oos",
            start_ms=as_of_ms - 30 * 86_400_000,
            end_ms=as_of_ms - 1 * 86_400_000,
            category="reserved",
        )
    )
    return regs


class FormalQualificationInfrastructureV1:
    """Orchestrates registries, checksums, gates, and the blocked stage machine."""

    def __init__(self) -> None:
        self.schema = SCHEMA_ID
        self.status = INFRA_STATUS_BLOCKED_READY
        self.candidate: dict[str, Any] | None = None
        self.registries: dict[str, IntervalRegistry] = build_empty_registries()
        self.promotion_sm = PromotionStateMachine()
        self.founder_gate = FounderAuthorizationGate()
        self.proofs: dict[str, Any] = {}
        self.formal_walk_forward_executed = False
        self.oos_executed = False
        self.exchange_write_attempt_count = 0
        self.demo_order_count = 0
        self.selected_strategy = None
        self.created_at = _utc()

    def bootstrap_synthetic(self, *, as_of_ms: int = 1_700_000_000_000) -> dict[str, Any]:
        """Wire infrastructure with synthetic fixtures. All stages stay BLOCKED."""
        self.promotion_sm.mark_infrastructure_ready()

        raw = synthetic_candidate_fixture()
        stamped = stamp_checksums(raw)
        checksum_errors = validate_checksums(stamped)
        if checksum_errors:
            raise RuntimeError(f"synthetic_checksum_errors:{checksum_errors}")
        self.candidate = stamped
        self.promotion_sm.register_synthetic_candidate(stamped["candidate_id"])

        self.registries = synthetic_interval_fixture(as_of_ms=as_of_ms)

        # Future-data exclusion on a proposed look-ahead (must fail)
        future_violation = assert_future_data_excluded(
            proposed_start_ms=as_of_ms - 1_000,
            proposed_end_ms=as_of_ms + 86_400_000,
            as_of_ms=as_of_ms,
        )
        # Valid past interval (must pass)
        future_ok = assert_future_data_excluded(
            proposed_start_ms=as_of_ms - 10 * 86_400_000,
            proposed_end_ms=as_of_ms - 5 * 86_400_000,
            as_of_ms=as_of_ms,
        )

        reserved = self.registries["reserved"].intervals[0]
        no_consumed_overlap = assert_no_overlap_with_consumed(
            self.registries["consumed"],
            start_ms=reserved.start_ms,
            end_ms=reserved.end_ms,
        )
        oos_proof = prove_oos_non_consumption(
            reserved=self.registries["reserved"],
            consumed=self.registries["consumed"],
            data=self.registries["data"],
        )

        # Founder gate: evaluate empty request → missing auth (fail-closed)
        gate_missing = self.founder_gate.evaluate(None)
        self.promotion_sm.request_founder_authorization(None)

        # Attempt stage advances — all refused
        advance_results = {
            stage: self.promotion_sm.attempt_advance_stage(stage) for stage in QUALIFICATION_STAGES
        }
        promote_result = self.promotion_sm.attempt_promote()

        self.proofs = {
            "checksum_errors": checksum_errors,
            "future_data_exclusion_violation_case": future_violation,
            "future_data_exclusion_valid_case": future_ok,
            "reserved_vs_consumed": no_consumed_overlap,
            "oos_non_consumption": oos_proof,
            "founder_gate_missing": gate_missing,
            "stage_advance_attempts": advance_results,
            "promote_attempt": promote_result,
        }
        self.status = INFRA_STATUS_BLOCKED_READY
        self.formal_walk_forward_executed = False
        self.oos_executed = False
        return self.summary()

    def summary(self) -> dict[str, Any]:
        stages = {
            s: STAGE_STATUS_BLOCKED for s in QUALIFICATION_STAGES
        }
        # Prefer SM stages if present
        if self.promotion_sm.stages:
            stages = dict(self.promotion_sm.stages)

        return {
            "schema": self.schema,
            "status": self.status,
            "Qualification_Infrastructure_status": self.status,
            "created_at": self.created_at,
            "updated_at": _utc(),
            "candidate": deepcopy(self.candidate) if self.candidate else None,
            "selected_strategy": self.selected_strategy,
            "stages": stages,
            "stage_order": list(QUALIFICATION_STAGES),
            "all_stages_blocked": all(v == STAGE_STATUS_BLOCKED for v in stages.values()),
            "registries": {k: v.to_dict() for k, v in self.registries.items()},
            "promotion_state_machine": self.promotion_sm.to_dict(),
            "founder_authorization_gate": self.founder_gate.to_dict(),
            "proofs": deepcopy(self.proofs),
            "formal_walk_forward_executed": self.formal_walk_forward_executed,
            "oos_executed": self.oos_executed,
            "demo_order_count": self.demo_order_count,
            "exchange_write_attempt_count": self.exchange_write_attempt_count,
            "demo_eligibility": False,
            "strategy_promoted": False,
            "prohibitions": {
                "formal_walk_forward": "NOT_EXECUTED",
                "oos_download_or_execution": "NOT_EXECUTED",
                "demo_shadow_exchange_writes": "NOT_ATTEMPTED",
                "real_strategy_selection": "NOT_PERFORMED",
                "promotion": "BLOCKED",
            },
        }


def run_infrastructure_dry_run(*, as_of_ms: int = 1_700_000_000_000) -> dict[str, Any]:
    infra = FormalQualificationInfrastructureV1()
    return infra.bootstrap_synthetic(as_of_ms=as_of_ms)


def write_immutable_artifacts(
    summary: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Path]:
    """Write immutable readiness JSON under owned artifact path."""
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    status_path = out_dir / "qualification_infrastructure_status.json"
    stages_path = out_dir / "qualification_stages_blocked.json"
    registries_path = out_dir / "interval_registries.json"
    checksums_path = out_dir / "candidate_checksums.json"
    founder_path = out_dir / "founder_authorization_gate.json"
    promotion_path = out_dir / "promotion_state_machine.json"
    proofs_path = out_dir / "safety_proofs.json"

    status_doc = {
        "schema": SCHEMA_ID,
        "status": summary.get("status"),
        "Qualification_Infrastructure_status": summary.get("Qualification_Infrastructure_status"),
        "all_stages_blocked": summary.get("all_stages_blocked"),
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "selected_strategy": None,
        "strategy_promoted": False,
        "demo_eligibility": False,
        "prohibitions": summary.get("prohibitions"),
        "created_at": summary.get("created_at"),
        "updated_at": summary.get("updated_at"),
    }
    stages_doc = {
        "schema": SCHEMA_ID,
        "stage_order": summary.get("stage_order"),
        "stages": summary.get("stages"),
        "note": "All stages default BLOCKED; V1 does not execute any stage.",
    }
    cand = summary.get("candidate") or {}
    checksums_doc = {
        "schema": SCHEMA_ID,
        "candidate_id": cand.get("candidate_id"),
        "fixture_only": cand.get("fixture_only", True),
        "selected": False,
        "candidate_checksum": cand.get("candidate_checksum"),
        "semantic_checksum": cand.get("semantic_checksum"),
        "parameter_checksum": cand.get("parameter_checksum"),
    }

    def _dump(path: Path, doc: Any) -> None:
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    _dump(status_path, status_doc)
    _dump(stages_path, stages_doc)
    _dump(registries_path, summary.get("registries") or {})
    _dump(checksums_path, checksums_doc)
    _dump(founder_path, summary.get("founder_authorization_gate") or {})
    _dump(promotion_path, summary.get("promotion_state_machine") or {})
    _dump(proofs_path, summary.get("proofs") or {})

    return {
        "status": status_path,
        "stages": stages_path,
        "registries": registries_path,
        "checksums": checksums_path,
        "founder": founder_path,
        "promotion": promotion_path,
        "proofs": proofs_path,
    }


def main() -> int:
    summary = run_infrastructure_dry_run()
    paths = write_immutable_artifacts(summary)
    print(json.dumps({"status": summary["status"], "artifacts": {k: str(v) for k, v in paths.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

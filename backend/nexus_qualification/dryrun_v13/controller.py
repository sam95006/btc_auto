"""Founder V13-F Qualification Dry-Run Control.

Connects Discovery outputs to blocked-only Qualification infrastructure.
Supports Candidate Freeze planning, checksums, development replay,
future-data exclusion, and WF/Risk/OOS/Demo eligibility *plans* only.

Hard bans: no formal WF, no real OOS reserve/consume, no strategy
select/promote, no Demo orders, no PR27 merge.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_qualification.dryrun_v13.checksums import validate_checksums
from backend.nexus_qualification.dryrun_v13.constants import (
    ARTIFACT_REL,
    BLOCK_REASON,
    FORMAL_STAGES,
    FORMAL_STATUS_BLOCKED,
    HARD_BANS,
    INFRA_STATUS_BLOCKED_READY,
    LANE,
    SCHEMA_ID,
    STAGE_LABELS,
    STAGE_STATUS_BLOCKED,
)
from backend.nexus_qualification.dryrun_v13.discovery_ingest import (
    build_synthetic_discovery_bundle,
    ingest_discovery_bundle,
)
from backend.nexus_qualification.dryrun_v13.future_data import (
    assert_future_data_excluded,
    prove_candidate_development_intervals,
    prove_market_universe_pit,
)
from backend.nexus_qualification.dryrun_v13.plans import build_all_eligibility_plans
from backend.nexus_qualification.dryrun_v13.replay import (
    freeze_all_candidates,
    replay_all_candidates,
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_control_flags() -> dict[str, Any]:
    return {
        "Founder_authorization_present": False,
        "founder_authorization_present": False,
        "formal_walk_forward_executed": False,
        "oos_reservation_created": False,
        "oos_executed": False,
        "oos_consumed": False,
        "strategy_selected": False,
        "strategy_promoted": False,
        "demo_eligibility": False,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "pr27_merged": False,
        "mainnet": False,
        "real_money": False,
        "qualification_ready_count": 0,
    }


class BlockedStageControllerV13F:
    """Refuse all formal stage advances. Fail-closed."""

    def __init__(self) -> None:
        self.stages: dict[str, str] = {s: STAGE_STATUS_BLOCKED for s in FORMAL_STAGES}
        self.attempt_log: list[dict[str, Any]] = []

    def attempt_execute_stage(self, stage: str) -> dict[str, Any]:
        if stage not in FORMAL_STAGES:
            result = {
                "allowed": False,
                "executed": False,
                "reason": "UNKNOWN_STAGE",
                "stage": stage,
                "status": STAGE_STATUS_BLOCKED,
            }
            self.attempt_log.append(deepcopy(result))
            return result
        self.stages[stage] = STAGE_STATUS_BLOCKED
        result = {
            "allowed": False,
            "executed": False,
            "reason": BLOCK_REASON,
            "stage": stage,
            "label": STAGE_LABELS[stage],
            "status": self.stages[stage],
            **default_control_flags(),
        }
        self.attempt_log.append(deepcopy(result))
        return result

    def attempt_all_stages(self) -> dict[str, dict[str, Any]]:
        return {stage: self.attempt_execute_stage(stage) for stage in FORMAL_STAGES}

    def all_blocked(self) -> bool:
        return all(v == STAGE_STATUS_BLOCKED for v in self.stages.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_order": list(FORMAL_STAGES),
            "stage_labels": dict(STAGE_LABELS),
            "stages": dict(self.stages),
            "all_stages_blocked": self.all_blocked(),
            "block_reason": BLOCK_REASON,
            "hard_bans": list(HARD_BANS),
            "attempt_count": len(self.attempt_log),
            "attempts": list(self.attempt_log),
        }


class QualificationDryRunControlV13F:
    """Blocked-only dry-run control connecting Discovery → Qualification plans."""

    def __init__(self) -> None:
        self.schema = SCHEMA_ID
        self.lane = LANE
        self.qualification_status = FORMAL_STATUS_BLOCKED
        self.infrastructure_status = INFRA_STATUS_BLOCKED_READY
        self.stage_controller = BlockedStageControllerV13F()
        self.flags = default_control_flags()
        self.ingested: dict[str, Any] | None = None
        self.proofs: dict[str, Any] = {}
        self.created_at = _utc()

    def attempt_select_strategy(self, candidate_id: str) -> dict[str, Any]:
        return {
            "allowed": False,
            "selected": False,
            "candidate_id": candidate_id,
            "reason": "STRATEGY_SELECTION_BANNED_V13_F",
        }

    def attempt_promote_strategy(self, candidate_id: str) -> dict[str, Any]:
        return {
            "allowed": False,
            "promoted": False,
            "candidate_id": candidate_id,
            "reason": "STRATEGY_PROMOTION_BANNED_V13_F",
        }

    def bootstrap(
        self,
        discovery_bundle: dict[str, Any] | None = None,
        *,
        as_of_ms: int | None = None,
    ) -> dict[str, Any]:
        if discovery_bundle is None:
            discovery_bundle = build_synthetic_discovery_bundle(
                as_of_ms=as_of_ms or 1_700_000_000_000
            )
        elif as_of_ms is not None:
            discovery_bundle = deepcopy(discovery_bundle)
            discovery_bundle["as_of_ms"] = as_of_ms

        self.ingested = ingest_discovery_bundle(discovery_bundle)
        as_of = int(self.ingested["as_of_ms"])
        candidates = self.ingested["strategy_discovery"]["candidates"]
        market = self.ingested["market_discovery"]

        checksum_errors: list[str] = []
        for cand in candidates:
            checksum_errors.extend(
                f"{cand['candidate_id']}:{e}" for e in validate_checksums(cand, market=market)
            )
        if checksum_errors:
            raise RuntimeError(f"checksum_errors:{checksum_errors}")

        freeze = freeze_all_candidates(candidates)
        replays = replay_all_candidates(candidates)
        future_dev = prove_candidate_development_intervals(candidates, as_of_ms=as_of)
        universe_pit = prove_market_universe_pit(market)
        future_violation_case = assert_future_data_excluded(
            proposed_start_ms=as_of - 1_000,
            proposed_end_ms=as_of + 86_400_000,
            as_of_ms=as_of,
        )
        future_ok_case = assert_future_data_excluded(
            proposed_start_ms=as_of - 10 * 86_400_000,
            proposed_end_ms=as_of - 5 * 86_400_000,
            as_of_ms=as_of,
        )
        plans = build_all_eligibility_plans(candidates, as_of_ms=as_of)

        advance_results = self.stage_controller.attempt_all_stages()
        select_attempts = {
            c["candidate_id"]: self.attempt_select_strategy(c["candidate_id"]) for c in candidates
        }
        promote_attempts = {
            c["candidate_id"]: self.attempt_promote_strategy(c["candidate_id"]) for c in candidates
        }

        self.flags = default_control_flags()
        self.qualification_status = FORMAL_STATUS_BLOCKED
        self.infrastructure_status = INFRA_STATUS_BLOCKED_READY

        self.proofs = {
            "checksum_errors": checksum_errors,
            "candidate_freeze": freeze,
            "development_replay": replays,
            "future_data_exclusion_development": future_dev,
            "market_universe_pit": universe_pit,
            "future_data_exclusion_violation_case": future_violation_case,
            "future_data_exclusion_valid_case": future_ok_case,
            "eligibility_plans": plans,
            "stage_execute_attempts": advance_results,
            "select_attempts": select_attempts,
            "promote_attempts": promote_attempts,
            "all_attempts_refused": all(
                (not r.get("allowed")) and (not r.get("executed"))
                for r in advance_results.values()
            ),
            "all_stages_blocked_after_attempts": self.stage_controller.all_blocked(),
            "all_selects_refused": all(not r["allowed"] for r in select_attempts.values()),
            "all_promotes_refused": all(not r["allowed"] for r in promote_attempts.values()),
            "development_replay_deterministic": replays.get("all_deterministic"),
            "future_data_excluded": bool(future_dev.get("all_excluded"))
            and bool(universe_pit.get("ok"))
            and future_ok_case.get("allowed") is True
            and future_violation_case.get("allowed") is False,
        }
        return self.summary()

    def summary(self) -> dict[str, Any]:
        stages = dict(self.stage_controller.stages)
        # Hard-ban flags are canonical constants — never trust mutable self.flags.
        flags = default_control_flags()
        self.flags = deepcopy(flags)
        self.qualification_status = FORMAL_STATUS_BLOCKED
        self.infrastructure_status = INFRA_STATUS_BLOCKED_READY
        ingested = deepcopy(self.ingested) if self.ingested else None
        candidates = (
            (ingested or {}).get("strategy_discovery", {}).get("candidates", []) if ingested else []
        )
        return {
            "schema": self.schema,
            "lane": self.lane,
            "qualification_status": FORMAL_STATUS_BLOCKED,
            "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
            "status": INFRA_STATUS_BLOCKED_READY,
            "created_at": self.created_at,
            "updated_at": _utc(),
            "stage_order": list(FORMAL_STAGES),
            "stages": stages,
            "all_stages_blocked": all(v == STAGE_STATUS_BLOCKED for v in stages.values()),
            "blocked_stage_controller": self.stage_controller.to_dict(),
            "discovery_ingest": {
                "bundle_checksum": (ingested or {}).get("bundle_checksum"),
                "ingested_candidate_count": (ingested or {}).get("ingested_candidate_count", 0),
                "qualification_ready_count": 0,
                "fixture_only": True,
                "as_of_ms": (ingested or {}).get("as_of_ms"),
                "universe_checksum": ((ingested or {}).get("market_discovery") or {}).get(
                    "universe_checksum"
                ),
                "candidate_ids": [c.get("candidate_id") for c in candidates],
                "checksums": [
                    {
                        "candidate_id": c.get("candidate_id"),
                        "semantic_checksum": c.get("semantic_checksum"),
                        "parameter_checksum": c.get("parameter_checksum"),
                        "code_checksum": c.get("code_checksum"),
                        "dataset_checksum": c.get("dataset_checksum"),
                        "discovery_label": c.get("discovery_label"),
                    }
                    for c in candidates
                ],
            },
            "proofs": deepcopy(self.proofs),
            "hard_bans": list(HARD_BANS),
            **flags,
            "selected_strategy": None,
            "prohibitions": {
                "candidate_freeze": "PLANNED_NOT_EXECUTED_FORMAL_BLOCKED",
                "development_replay": "EXECUTED_DEVELOPMENT_ONLY",
                "walk_forward": "PLAN_ONLY_NOT_EXECUTED",
                "risk_review": "PLAN_ONLY_NOT_EXECUTED",
                "oos_reservation": "PLAN_ONLY_NOT_CREATED",
                "oos_execution": "NOT_EXECUTED",
                "oos_consumption": "NOT_CONSUMED",
                "demo_eligibility": "PLAN_ONLY_NOT_GRANTED",
                "demo_shadow_exchange_writes": "NOT_ATTEMPTED",
                "strategy_selection": "NOT_PERFORMED",
                "strategy_promotion": "BLOCKED",
                "pr27_merge": "NOT_PERFORMED",
            },
        }


def run_qualification_dry_run_control(
    discovery_bundle: dict[str, Any] | None = None,
    *,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    ctrl = QualificationDryRunControlV13F()
    return ctrl.bootstrap(discovery_bundle, as_of_ms=as_of_ms)


def run_two_pass_dry_run(
    discovery_bundle: dict[str, Any] | None = None,
    *,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    """PASS 1: dry-run evidence. PASS 2: adversarial refusal + stability re-run."""
    pass1 = run_qualification_dry_run_control(discovery_bundle, as_of_ms=as_of_ms)

    ctrl = QualificationDryRunControlV13F()
    # Rebuild state then adversarially probe.
    ctrl.bootstrap(discovery_bundle, as_of_ms=as_of_ms)
    adversarial: dict[str, Any] = {
        "force_execute_walk_forward": ctrl.stage_controller.attempt_execute_stage("WALK_FORWARD"),
        "force_execute_oos": ctrl.stage_controller.attempt_execute_stage("OOS_RESERVATION"),
        "force_execute_demo": ctrl.stage_controller.attempt_execute_stage("DEMO_ELIGIBILITY"),
        "force_select": ctrl.attempt_select_strategy("SYN_V13F_DISC_001"),
        "force_promote": ctrl.attempt_promote_strategy("SYN_V13F_DISC_001"),
        "future_data_injection": assert_future_data_excluded(
            proposed_start_ms=int(pass1["discovery_ingest"]["as_of_ms"]) - 1000,
            proposed_end_ms=int(pass1["discovery_ingest"]["as_of_ms"]) + 86_400_000,
            as_of_ms=int(pass1["discovery_ingest"]["as_of_ms"]),
        ),
    }
    pass2_summary = ctrl.summary()
    pass2_stable = run_qualification_dry_run_control(discovery_bundle, as_of_ms=as_of_ms)

    stability = {
        "qualification_status_stable": pass1["qualification_status"]
        == pass2_stable["qualification_status"]
        == FORMAL_STATUS_BLOCKED,
        "infrastructure_status_stable": pass1["infrastructure_status"]
        == pass2_stable["infrastructure_status"]
        == INFRA_STATUS_BLOCKED_READY,
        "ready_count_stable_zero": pass1["qualification_ready_count"]
        == pass2_stable["qualification_ready_count"]
        == 0,
        "candidate_count_stable": pass1["discovery_ingest"]["ingested_candidate_count"]
        == pass2_stable["discovery_ingest"]["ingested_candidate_count"],
        "checksums_stable": pass1["discovery_ingest"]["checksums"]
        == pass2_stable["discovery_ingest"]["checksums"],
    }

    adversarial_ok = (
        all(not adversarial[k]["allowed"] for k in (
            "force_execute_walk_forward",
            "force_execute_oos",
            "force_execute_demo",
            "force_select",
            "force_promote",
        ))
        and adversarial["future_data_injection"]["allowed"] is False
        and all(stability.values())
        and pass2_summary["all_stages_blocked"] is True
        and pass2_summary["qualification_ready_count"] == 0
    )

    return {
        "schema": SCHEMA_ID,
        "lane": LANE,
        "pass1": pass1,
        "pass2": {
            "summary": pass2_summary,
            "adversarial": adversarial,
            "stability": stability,
            "stable_rerun": {
                "qualification_status": pass2_stable["qualification_status"],
                "infrastructure_status": pass2_stable["infrastructure_status"],
                "qualification_ready_count": pass2_stable["qualification_ready_count"],
                "ingested_candidate_count": pass2_stable["discovery_ingest"][
                    "ingested_candidate_count"
                ],
            },
            "adversarial_ok": adversarial_ok,
        },
        "qualification_status": FORMAL_STATUS_BLOCKED,
        "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
        "qualification_ready_count": 0,
        "both_passes_ok": bool(
            pass1["all_stages_blocked"]
            and pass1["qualification_ready_count"] == 0
            and pass1["proofs"].get("all_attempts_refused")
            and pass1["proofs"].get("development_replay_deterministic")
            and pass1["proofs"].get("future_data_excluded")
            and adversarial_ok
        ),
    }


def write_immutable_artifacts(
    two_pass: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Path]:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    pass1 = two_pass["pass1"]

    def _dump(path: Path, doc: Any) -> None:
        path.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    status_path = out_dir / "qualification_dry_run_status.json"
    stages_path = out_dir / "formal_stages_blocked.json"
    flags_path = out_dir / "control_flags.json"
    discovery_path = out_dir / "discovery_ingest.json"
    checksums_path = out_dir / "candidate_checksums.json"
    freeze_path = out_dir / "candidate_freeze_plans.json"
    replay_path = out_dir / "development_replay.json"
    future_path = out_dir / "future_data_exclusion.json"
    plans_path = out_dir / "eligibility_plans.json"
    proofs_path = out_dir / "block_proofs.json"
    two_pass_path = out_dir / "two_pass_report.json"
    summary_path = out_dir / "qualification_dry_run_summary.json"

    _dump(
        status_path,
        {
            "schema": SCHEMA_ID,
            "lane": LANE,
            "qualification_status": pass1["qualification_status"],
            "infrastructure_status": pass1["infrastructure_status"],
            "all_stages_blocked": pass1["all_stages_blocked"],
            "qualification_ready_count": 0,
            **default_control_flags(),
            "prohibitions": pass1["prohibitions"],
            "created_at": pass1["created_at"],
            "updated_at": pass1["updated_at"],
        },
    )
    _dump(
        stages_path,
        {
            "schema": SCHEMA_ID,
            "stage_order": pass1["stage_order"],
            "stage_labels": STAGE_LABELS,
            "stages": pass1["stages"],
            "all_stages_blocked": True,
            "block_reason": BLOCK_REASON,
            "note": "All formal stages remain BLOCKED; only plans/replay/checksums run.",
        },
    )
    _dump(flags_path, {"schema": SCHEMA_ID, **default_control_flags()})
    _dump(discovery_path, pass1["discovery_ingest"])
    _dump(
        checksums_path,
        {
            "schema": SCHEMA_ID,
            "checksums": pass1["discovery_ingest"]["checksums"],
            "qualification_ready_count": 0,
        },
    )
    _dump(freeze_path, pass1["proofs"].get("candidate_freeze") or {})
    _dump(replay_path, pass1["proofs"].get("development_replay") or {})
    _dump(
        future_path,
        {
            "development": pass1["proofs"].get("future_data_exclusion_development"),
            "universe_pit": pass1["proofs"].get("market_universe_pit"),
            "violation_case": pass1["proofs"].get("future_data_exclusion_violation_case"),
            "valid_case": pass1["proofs"].get("future_data_exclusion_valid_case"),
        },
    )
    _dump(plans_path, pass1["proofs"].get("eligibility_plans") or {})
    _dump(
        proofs_path,
        {
            "schema": SCHEMA_ID,
            "all_attempts_refused": pass1["proofs"].get("all_attempts_refused"),
            "all_selects_refused": pass1["proofs"].get("all_selects_refused"),
            "all_promotes_refused": pass1["proofs"].get("all_promotes_refused"),
            "stage_execute_attempts": pass1["proofs"].get("stage_execute_attempts"),
            "select_attempts": pass1["proofs"].get("select_attempts"),
            "promote_attempts": pass1["proofs"].get("promote_attempts"),
            "blocked_stage_controller": pass1.get("blocked_stage_controller"),
        },
    )
    _dump(
        two_pass_path,
        {
            "schema": SCHEMA_ID,
            "both_passes_ok": two_pass.get("both_passes_ok"),
            "pass2_adversarial_ok": two_pass["pass2"].get("adversarial_ok"),
            "pass2_stability": two_pass["pass2"].get("stability"),
            "pass2_adversarial": two_pass["pass2"].get("adversarial"),
            "qualification_ready_count": 0,
        },
    )
    _dump(summary_path, pass1)

    return {
        "status": status_path,
        "stages": stages_path,
        "flags": flags_path,
        "discovery": discovery_path,
        "checksums": checksums_path,
        "freeze": freeze_path,
        "replay": replay_path,
        "future_data": future_path,
        "plans": plans_path,
        "proofs": proofs_path,
        "two_pass": two_pass_path,
        "summary": summary_path,
    }

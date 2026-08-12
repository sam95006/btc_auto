"""Founder V15-E Candidate Dossier Builder control plane.

Builds development dossiers with full lineage/checksums/versions/failed siblings/
regime/symbol/cost breakdowns. Status ceiling: DEVELOPMENT_REVIEW or
DEVELOPMENT_PROMISING_NOT_QUALIFIED. Never writes *_status.json lane reports.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_candidate_dossier.bans import (
    default_control_flags,
    hard_ban_probe_matrix,
    refuse_auto_integrate,
    refuse_demo,
    refuse_demo_ready,
    refuse_exchange_write,
    refuse_formal_walk_forward,
    refuse_oos,
    refuse_promote,
    refuse_qualify,
    refuse_select,
    refuse_shadow,
    refuse_status_json_write,
)
from backend.nexus_candidate_dossier.builder import (
    build_dossier_bundle,
    expect_histogram_coverage,
    inject_forbidden_status_attempt,
)
from backend.nexus_candidate_dossier.constants import (
    ALLOWED_DOSSIER_STATUSES,
    ARTIFACT_REL,
    BLOCK_REASON,
    DOSSIER_BUILDER_STATUS,
    EVIDENCE_CLASS,
    FORBIDDEN_OUTPUT_STATUSES,
    FORMAL_STATUS_BLOCKED,
    HARD_BANS,
    INFRA_STATUS_BLOCKED_READY,
    LANE,
    OWNED_PATHS,
    REQUIRED_DOSSIER_FIELDS,
    SCHEMA_ID,
)
from backend.nexus_candidate_dossier.fixtures import build_synthetic_dossier_inputs


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CandidateDossierBuilderV15E:
    """Development-only dossier builder. Fail-closed on forbidden outputs."""

    def __init__(self) -> None:
        self.schema = SCHEMA_ID
        self.lane = LANE
        self.qualification_status = FORMAL_STATUS_BLOCKED
        self.infrastructure_status = INFRA_STATUS_BLOCKED_READY
        self.builder_status = DOSSIER_BUILDER_STATUS
        self.flags = default_control_flags()
        self.inputs: dict[str, Any] | None = None
        self.bundle: dict[str, Any] | None = None
        self.proofs: dict[str, Any] = {}
        self.created_at = _utc()

    def attempt_select_strategy(self, candidate_id: str) -> dict[str, Any]:
        return refuse_select(candidate_id)

    def attempt_promote_strategy(self, candidate_id: str) -> dict[str, Any]:
        return refuse_promote(candidate_id)

    def attempt_qualify(self, candidate_id: str) -> dict[str, Any]:
        return refuse_qualify(candidate_id)

    def attempt_demo_ready(self, candidate_id: str) -> dict[str, Any]:
        return refuse_demo_ready(candidate_id)

    def attempt_formal_walk_forward(self, candidate_id: str | None = None) -> dict[str, Any]:
        return refuse_formal_walk_forward(candidate_id)

    def attempt_oos(self, candidate_id: str | None = None) -> dict[str, Any]:
        return refuse_oos(candidate_id=candidate_id)

    def attempt_demo_order(self, candidate_id: str | None = None) -> dict[str, Any]:
        return refuse_demo(candidate_id)

    def attempt_shadow_order(self, candidate_id: str | None = None) -> dict[str, Any]:
        return refuse_shadow(candidate_id)

    def attempt_auto_integrate(self) -> dict[str, Any]:
        return refuse_auto_integrate()

    def attempt_exchange_write(self) -> dict[str, Any]:
        return refuse_exchange_write()

    def attempt_status_json_write(self, path: str = "v15_e_status.json") -> dict[str, Any]:
        return refuse_status_json_write(path)

    def bootstrap(
        self,
        input_bundle: dict[str, Any] | None = None,
        *,
        as_of_ms: int | None = None,
    ) -> dict[str, Any]:
        if input_bundle is None:
            input_bundle = build_synthetic_dossier_inputs(
                as_of_ms=as_of_ms or 1_700_000_000_000
            )
        elif as_of_ms is not None:
            input_bundle = deepcopy(input_bundle)
            input_bundle["as_of_ms"] = as_of_ms

        self.inputs = deepcopy(input_bundle)
        candidates = list(self.inputs.get("candidates") or [])
        self.bundle = build_dossier_bundle(candidates)

        cid0 = candidates[0]["candidate_id"] if candidates else "NONE"
        select_attempts = {
            c["candidate_id"]: self.attempt_select_strategy(c["candidate_id"])
            for c in candidates
        }
        promote_attempts = {
            c["candidate_id"]: self.attempt_promote_strategy(c["candidate_id"])
            for c in candidates
        }
        qualify_attempts = {
            c["candidate_id"]: self.attempt_qualify(c["candidate_id"]) for c in candidates
        }
        demo_ready_attempts = {
            c["candidate_id"]: self.attempt_demo_ready(c["candidate_id"]) for c in candidates
        }

        ban_matrix = hard_ban_probe_matrix(cid0)
        self.flags = default_control_flags()
        self.qualification_status = FORMAL_STATUS_BLOCKED
        self.infrastructure_status = INFRA_STATUS_BLOCKED_READY
        self.builder_status = DOSSIER_BUILDER_STATUS

        self.proofs = {
            "dossier_bundle": deepcopy(self.bundle),
            "histogram_covers_all_allowed": expect_histogram_coverage(
                self.bundle["status_histogram"]
            ),
            "forbidden_statuses_absent": self.bundle["forbidden_output_count"] == 0,
            "status_ceiling_ok": self.bundle.get("status_ceiling_ok") is True,
            "all_required_fields_present": self.bundle.get("all_required_fields_present"),
            "all_have_failed_siblings": self.bundle.get("all_have_failed_siblings"),
            "required_fields": list(REQUIRED_DOSSIER_FIELDS),
            "select_attempts": select_attempts,
            "promote_attempts": promote_attempts,
            "qualify_attempts": qualify_attempts,
            "demo_ready_attempts": demo_ready_attempts,
            "all_selects_refused": all(not r["allowed"] for r in select_attempts.values()),
            "all_promotes_refused": all(not r["allowed"] for r in promote_attempts.values()),
            "all_qualifies_refused": all(not r["allowed"] for r in qualify_attempts.values()),
            "all_demo_ready_refused": all(
                not r["allowed"] for r in demo_ready_attempts.values()
            ),
            "hard_ban_probe": ban_matrix,
            "status_json_write_refused": self.attempt_status_json_write(),
            "block_reason": BLOCK_REASON,
        }
        return self.summary()

    def summary(self) -> dict[str, Any]:
        flags = default_control_flags()
        self.flags = deepcopy(flags)
        bundle = deepcopy(self.bundle) if self.bundle else None
        inputs = deepcopy(self.inputs) if self.inputs else None
        return {
            "schema": self.schema,
            "lane": self.lane,
            "qualification_status": FORMAL_STATUS_BLOCKED,
            "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
            "dossier_builder_status": DOSSIER_BUILDER_STATUS,
            "created_at": self.created_at,
            "updated_at": _utc(),
            "evidence_class": EVIDENCE_CLASS,
            "allowed_dossier_statuses": list(ALLOWED_DOSSIER_STATUSES),
            "forbidden_output_statuses": list(FORBIDDEN_OUTPUT_STATUSES),
            "required_dossier_fields": list(REQUIRED_DOSSIER_FIELDS),
            "ingest": {
                "bundle_checksum": (inputs or {}).get("bundle_checksum"),
                "input_candidate_count": len((inputs or {}).get("candidates") or []),
                "qualification_ready_count": 0,
                "fixture_only": True,
                "as_of_ms": (inputs or {}).get("as_of_ms"),
                "candidate_ids": [
                    c.get("candidate_id") for c in (inputs or {}).get("candidates", [])
                ],
            },
            "dossiers": bundle,
            "proofs": deepcopy(self.proofs),
            "hard_bans": list(HARD_BANS),
            "owned_paths": list(OWNED_PATHS),
            "lane_status_json_written": False,
            **flags,
            "selected_strategy": None,
            "promoted_strategy": None,
            "qualification_ready_count": 0,
            "prohibitions": {
                "formal_walk_forward": "NOT_EXECUTED",
                "oos_reservation": "NOT_CREATED",
                "oos_execution": "NOT_EXECUTED",
                "oos_consumption": "NOT_CONSUMED",
                "strategy_selection": "NOT_PERFORMED",
                "strategy_promotion": "BLOCKED",
                "qualified_output": "FORBIDDEN",
                "promoted_output": "FORBIDDEN",
                "demo_ready_output": "FORBIDDEN",
                "demo_orders": "NOT_ATTEMPTED",
                "shadow_orders": "NOT_ATTEMPTED",
                "exchange_writes": "NOT_ATTEMPTED",
                "auto_integrate": "BANNED",
                "pr27_merge": "NOT_PERFORMED",
                "lane_status_json": "BANNED",
                "status_ceiling": "DEVELOPMENT_REVIEW|DEVELOPMENT_PROMISING_NOT_QUALIFIED",
            },
        }


def run_candidate_dossier_builder(
    input_bundle: dict[str, Any] | None = None,
    *,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    ctrl = CandidateDossierBuilderV15E()
    return ctrl.bootstrap(input_bundle, as_of_ms=as_of_ms)


def run_two_pass_dossier(
    input_bundle: dict[str, Any] | None = None,
    *,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    """PASS 1: build dossiers. PASS 2: adversarial bans + deterministic re-run."""
    pass1 = run_candidate_dossier_builder(input_bundle, as_of_ms=as_of_ms)

    ctrl = CandidateDossierBuilderV15E()
    ctrl.bootstrap(input_bundle, as_of_ms=as_of_ms)
    cid = (pass1.get("ingest") or {}).get("candidate_ids", ["SYN_V15E_PROBE"])[0]
    cand0 = (ctrl.inputs or {}).get("candidates", [{}])[0]

    adversarial: dict[str, Any] = {
        "force_walk_forward": ctrl.attempt_formal_walk_forward(cid),
        "force_oos": ctrl.attempt_oos(cid),
        "force_select": ctrl.attempt_select_strategy(cid),
        "force_promote": ctrl.attempt_promote_strategy(cid),
        "force_qualify": ctrl.attempt_qualify(cid),
        "force_demo_ready": ctrl.attempt_demo_ready(cid),
        "force_demo_order": ctrl.attempt_demo_order(cid),
        "force_shadow_order": ctrl.attempt_shadow_order(cid),
        "force_auto_integrate": ctrl.attempt_auto_integrate(),
        "force_exchange_write": ctrl.attempt_exchange_write(),
        "force_status_json": ctrl.attempt_status_json_write(),
        "inject_qualified": inject_forbidden_status_attempt(cand0, "QUALIFIED"),
        "inject_promoted": inject_forbidden_status_attempt(cand0, "PROMOTED"),
        "inject_demo_ready": inject_forbidden_status_attempt(cand0, "DEMO_READY"),
        "inject_oos_ready": inject_forbidden_status_attempt(cand0, "OOS_READY"),
        "hard_ban_probe": hard_ban_probe_matrix(cid),
    }
    pass2_summary = ctrl.summary()
    pass2_stable = run_candidate_dossier_builder(input_bundle, as_of_ms=as_of_ms)

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
        "candidate_count_stable": pass1["ingest"]["input_candidate_count"]
        == pass2_stable["ingest"]["input_candidate_count"],
        "histogram_stable": pass1["dossiers"]["status_histogram"]
        == pass2_stable["dossiers"]["status_histogram"],
        "bundle_checksum_stable": pass1["ingest"]["bundle_checksum"]
        == pass2_stable["ingest"]["bundle_checksum"],
        "dossier_digest_stable": pass1["dossiers"]["bundle_digest"]
        == pass2_stable["dossiers"]["bundle_digest"],
        "lane_status_json_still_false": pass1["lane_status_json_written"] is False
        and pass2_stable["lane_status_json_written"] is False,
    }

    refusal_keys = (
        "force_walk_forward",
        "force_oos",
        "force_select",
        "force_promote",
        "force_qualify",
        "force_demo_ready",
        "force_demo_order",
        "force_shadow_order",
        "force_auto_integrate",
        "force_exchange_write",
        "force_status_json",
    )
    inject_keys = (
        "inject_qualified",
        "inject_promoted",
        "inject_demo_ready",
        "inject_oos_ready",
    )
    adversarial_ok = (
        all(not adversarial[k].get("allowed") for k in refusal_keys)
        and all(adversarial[k]["forbidden_accepted"] is False for k in inject_keys)
        and adversarial["hard_ban_probe"]["all_refused"] is True
        and all(stability.values())
        and pass2_summary["qualification_ready_count"] == 0
        and pass2_summary["dossiers"]["forbidden_output_count"] == 0
    )

    both_ok = bool(
        pass1["qualification_ready_count"] == 0
        and pass1["proofs"].get("all_selects_refused")
        and pass1["proofs"].get("all_promotes_refused")
        and pass1["proofs"].get("all_qualifies_refused")
        and pass1["proofs"].get("all_demo_ready_refused")
        and pass1["proofs"].get("forbidden_statuses_absent")
        and pass1["proofs"].get("histogram_covers_all_allowed")
        and pass1["proofs"].get("status_ceiling_ok")
        and pass1["proofs"].get("all_required_fields_present")
        and pass1["proofs"].get("all_have_failed_siblings")
        and pass1["lane_status_json_written"] is False
        and adversarial_ok
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
                "input_candidate_count": pass2_stable["ingest"]["input_candidate_count"],
                "status_histogram": pass2_stable["dossiers"]["status_histogram"],
                "bundle_digest": pass2_stable["dossiers"]["bundle_digest"],
            },
            "adversarial_ok": adversarial_ok,
        },
        "qualification_status": FORMAL_STATUS_BLOCKED,
        "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
        "dossier_builder_status": DOSSIER_BUILDER_STATUS,
        "qualification_ready_count": 0,
        "lane_status_json_written": False,
        "both_passes_ok": both_ok,
    }


def write_immutable_artifacts(
    two_pass: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Path]:
    """Write dossier evidence artifacts. Never writes *_status.json."""
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    pass1 = two_pass["pass1"]

    def _dump(path: Path, doc: Any) -> None:
        if path.name.endswith("_status.json") or path.name.endswith("status.json"):
            raise RuntimeError(f"LANE_STATUS_JSON_BANNED:{path.name}")
        path.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    paths = {
        "dossiers": out_dir / "candidate_dossiers.json",
        "histogram": out_dir / "dossier_histogram.json",
        "lineage": out_dir / "dossier_lineage_checksums.json",
        "siblings": out_dir / "failed_sibling_experiments.json",
        "breakdowns": out_dir / "regime_symbol_cost_breakdowns.json",
        "bans": out_dir / "hard_ban_proofs.json",
        "flags": out_dir / "control_flags.json",
        "two_pass": out_dir / "two_pass_report.json",
        "summary": out_dir / "candidate_dossier_summary.json",
        "ingest": out_dir / "dossier_input_ingest.json",
    }

    dossiers = pass1["dossiers"]["dossiers"]
    _dump(paths["dossiers"], pass1["dossiers"])
    _dump(
        paths["histogram"],
        {
            "schema": SCHEMA_ID,
            "status_histogram": pass1["dossiers"]["status_histogram"],
            "covers_all_allowed": pass1["proofs"].get("histogram_covers_all_allowed"),
            "qualification_ready_count": 0,
            "forbidden_output_count": 0,
            "status_ceiling_ok": True,
            "allowed_dossier_statuses": list(ALLOWED_DOSSIER_STATUSES),
        },
    )
    _dump(
        paths["lineage"],
        {
            "schema": SCHEMA_ID,
            "entries": [
                {
                    "candidate_id": d["candidate_id"],
                    "dossier_status": d["dossier_status"],
                    "data_lineage": d["data_lineage"],
                    "universe_checksum": d["universe_checksum"],
                    "feature_version": d["feature_version"],
                    "code_checksum": d["code_checksum"],
                    "parameter_checksum": d["parameter_checksum"],
                    "cost_version": d["cost_version"],
                    "risk_version": d["risk_version"],
                    "execution_version": d["execution_version"],
                    "dossier_checksum": d["dossier_checksum"],
                    "candidate_checksum": d["candidate_checksum"],
                }
                for d in dossiers
            ],
        },
    )
    _dump(
        paths["siblings"],
        {
            "schema": SCHEMA_ID,
            "entries": [
                {
                    "candidate_id": d["candidate_id"],
                    "failed_sibling_experiments": d["failed_sibling_experiments"],
                }
                for d in dossiers
            ],
        },
    )
    _dump(
        paths["breakdowns"],
        {
            "schema": SCHEMA_ID,
            "entries": [
                {
                    "candidate_id": d["candidate_id"],
                    "regime_breakdown": d["regime_breakdown"],
                    "symbol_breakdown": d["symbol_breakdown"],
                    "cost_breakdown": d["cost_breakdown"],
                    "capacity_assumptions": d["capacity_assumptions"],
                    "known_failure_conditions": d["known_failure_conditions"],
                    "multiple_testing_status": d["multiple_testing_status"],
                    "remaining_blockers": d["remaining_blockers"],
                    "development_intervals": d["development_intervals"],
                }
                for d in dossiers
            ],
        },
    )
    _dump(
        paths["bans"],
        {
            "schema": SCHEMA_ID,
            "hard_bans": list(HARD_BANS),
            "select_attempts": pass1["proofs"].get("select_attempts"),
            "promote_attempts": pass1["proofs"].get("promote_attempts"),
            "qualify_attempts": pass1["proofs"].get("qualify_attempts"),
            "demo_ready_attempts": pass1["proofs"].get("demo_ready_attempts"),
            "hard_ban_probe": pass1["proofs"].get("hard_ban_probe"),
            "status_json_write_refused": pass1["proofs"].get("status_json_write_refused"),
            "all_selects_refused": pass1["proofs"].get("all_selects_refused"),
            "all_promotes_refused": pass1["proofs"].get("all_promotes_refused"),
            "all_qualifies_refused": pass1["proofs"].get("all_qualifies_refused"),
            "all_demo_ready_refused": pass1["proofs"].get("all_demo_ready_refused"),
        },
    )
    _dump(paths["flags"], {"schema": SCHEMA_ID, **default_control_flags()})
    _dump(
        paths["two_pass"],
        {
            "schema": SCHEMA_ID,
            "both_passes_ok": two_pass.get("both_passes_ok"),
            "pass2_adversarial_ok": two_pass["pass2"].get("adversarial_ok"),
            "pass2_stability": two_pass["pass2"].get("stability"),
            "pass2_adversarial": {
                k: (
                    {sk: sv for sk, sv in v.items() if sk != "record"}
                    if isinstance(v, dict) and "record" in v
                    else v
                )
                for k, v in (two_pass["pass2"].get("adversarial") or {}).items()
            },
            "qualification_ready_count": 0,
            "lane_status_json_written": False,
        },
    )
    _dump(paths["summary"], pass1)
    _dump(paths["ingest"], pass1["ingest"])

    # Guard: refuse any accidental *status*.json under artifact dir.
    for p in out_dir.glob("*status*.json"):
        raise RuntimeError(f"LANE_STATUS_JSON_PRESENT:{p.name}")

    return paths

"""Founder V14-H Candidate Triage Control.

Connects mechanism defs, Feature Lab, dynamic universe, cost sensitivity,
robustness, and blocked Qualification planning. Emits development triage
statuses only — never QUALIFIED / PROMOTED / DEMO_READY.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_candidate_triage.bans import (
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
)
from backend.nexus_candidate_triage.connectors import ingest_research_bundle
from backend.nexus_candidate_triage.constants import (
    ALLOWED_TRIAGE_STATUSES,
    ARTIFACT_REL,
    BLOCK_REASON,
    CONNECTION_SURFACES,
    EVIDENCE_CLASS,
    FORBIDDEN_OUTPUT_STATUSES,
    FORMAL_STATUS_BLOCKED,
    HARD_BANS,
    INFRA_STATUS_BLOCKED_READY,
    LANE,
    OWNED_PATHS,
    SCHEMA_ID,
    TRIAGE_STATUS_READY,
)
from backend.nexus_candidate_triage.engine import (
    expect_histogram_coverage,
    inject_forbidden_status_attempt,
    triage_bundle,
)
from backend.nexus_candidate_triage.fixtures import build_synthetic_research_bundle


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CandidateTriageControlV14H:
    """Development-only triage control. Fail-closed on forbidden outputs."""

    def __init__(self) -> None:
        self.schema = SCHEMA_ID
        self.lane = LANE
        self.qualification_status = FORMAL_STATUS_BLOCKED
        self.infrastructure_status = INFRA_STATUS_BLOCKED_READY
        self.triage_status = TRIAGE_STATUS_READY
        self.flags = default_control_flags()
        self.ingested: dict[str, Any] | None = None
        self.triage: dict[str, Any] | None = None
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

    def attempt_auto_integrate(self) -> dict[str, Any]:
        return refuse_auto_integrate()

    def attempt_exchange_write(self) -> dict[str, Any]:
        return refuse_exchange_write()

    def bootstrap(
        self,
        research_bundle: dict[str, Any] | None = None,
        *,
        as_of_ms: int | None = None,
    ) -> dict[str, Any]:
        if research_bundle is None:
            research_bundle = build_synthetic_research_bundle(
                as_of_ms=as_of_ms or 1_700_000_000_000
            )
        elif as_of_ms is not None:
            research_bundle = deepcopy(research_bundle)
            research_bundle["as_of_ms"] = as_of_ms

        self.ingested = ingest_research_bundle(research_bundle, as_of_ms=as_of_ms)
        candidates = list(self.ingested["candidates"])
        self.triage = triage_bundle(candidates)

        cid0 = candidates[0]["candidate_id"] if candidates else "NONE"
        select_attempts = {
            c["candidate_id"]: self.attempt_select_strategy(c["candidate_id"]) for c in candidates
        }
        promote_attempts = {
            c["candidate_id"]: self.attempt_promote_strategy(c["candidate_id"]) for c in candidates
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
        self.triage_status = TRIAGE_STATUS_READY

        blocked_plans = [
            conn["connections"]["blocked_qualification_planning"]
            for conn in self.ingested["connections"]
        ]

        self.proofs = {
            "connections": deepcopy(self.ingested["connections"]),
            "all_candidates_connected": self.ingested.get("all_candidates_connected"),
            "connection_surfaces": list(CONNECTION_SURFACES),
            "triage": deepcopy(self.triage),
            "histogram_covers_all_allowed": expect_histogram_coverage(
                self.triage["status_histogram"]
            ),
            "forbidden_statuses_absent": self.triage["forbidden_output_count"] == 0,
            "select_attempts": select_attempts,
            "promote_attempts": promote_attempts,
            "qualify_attempts": qualify_attempts,
            "demo_ready_attempts": demo_ready_attempts,
            "all_selects_refused": all(not r["allowed"] for r in select_attempts.values()),
            "all_promotes_refused": all(not r["allowed"] for r in promote_attempts.values()),
            "all_qualifies_refused": all(not r["allowed"] for r in qualify_attempts.values()),
            "all_demo_ready_refused": all(not r["allowed"] for r in demo_ready_attempts.values()),
            "hard_ban_probe": ban_matrix,
            "blocked_qualification_plans": blocked_plans,
            "all_qualification_plans_not_executed": all(
                p.get("status") == "PLANNED_NOT_EXECUTED"
                and p.get("qualification_ready") is False
                and p.get("formal_qualification_status") == "BLOCKED"
                and p.get("walk_forward_plan", {}).get("formal_walk_forward_executed") is False
                and p.get("oos_reservation_plan", {}).get("oos_consumed") is False
                for p in blocked_plans
            ),
            "block_reason": BLOCK_REASON,
        }
        return self.summary()

    def summary(self) -> dict[str, Any]:
        flags = default_control_flags()
        self.flags = deepcopy(flags)
        self.qualification_status = FORMAL_STATUS_BLOCKED
        self.infrastructure_status = INFRA_STATUS_BLOCKED_READY
        triage = deepcopy(self.triage) if self.triage else None
        ingested = deepcopy(self.ingested) if self.ingested else None
        return {
            "schema": self.schema,
            "lane": self.lane,
            "qualification_status": FORMAL_STATUS_BLOCKED,
            "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
            "triage_control_status": TRIAGE_STATUS_READY,
            "status": TRIAGE_STATUS_READY,
            "created_at": self.created_at,
            "updated_at": _utc(),
            "evidence_class": EVIDENCE_CLASS,
            "allowed_triage_statuses": list(ALLOWED_TRIAGE_STATUSES),
            "forbidden_output_statuses": list(FORBIDDEN_OUTPUT_STATUSES),
            "ingest": {
                "bundle_checksum": (ingested or {}).get("bundle_checksum"),
                "ingested_candidate_count": (ingested or {}).get("ingested_candidate_count", 0),
                "qualification_ready_count": 0,
                "fixture_only": True,
                "as_of_ms": (ingested or {}).get("as_of_ms"),
                "all_candidates_connected": (ingested or {}).get("all_candidates_connected"),
                "candidate_ids": [c.get("candidate_id") for c in (ingested or {}).get("candidates", [])],
            },
            "triage": triage,
            "proofs": deepcopy(self.proofs),
            "hard_bans": list(HARD_BANS),
            "owned_paths": list(OWNED_PATHS),
            **flags,
            "selected_strategy": None,
            "promoted_strategy": None,
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
                "exchange_writes": "NOT_ATTEMPTED",
                "auto_integrate": "BANNED",
                "pr27_merge": "NOT_PERFORMED",
            },
        }


def run_candidate_triage_control(
    research_bundle: dict[str, Any] | None = None,
    *,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    ctrl = CandidateTriageControlV14H()
    return ctrl.bootstrap(research_bundle, as_of_ms=as_of_ms)


def run_two_pass_triage(
    research_bundle: dict[str, Any] | None = None,
    *,
    as_of_ms: int | None = None,
) -> dict[str, Any]:
    """PASS 1: triage evidence. PASS 2: adversarial bans + stability re-run."""
    pass1 = run_candidate_triage_control(research_bundle, as_of_ms=as_of_ms)

    ctrl = CandidateTriageControlV14H()
    ctrl.bootstrap(research_bundle, as_of_ms=as_of_ms)
    cid = (pass1.get("ingest") or {}).get("candidate_ids", ["SYN_V14H_PROBE"])[0]
    cand0 = (ctrl.ingested or {}).get("candidates", [{}])[0]

    adversarial: dict[str, Any] = {
        "force_walk_forward": ctrl.attempt_formal_walk_forward(cid),
        "force_oos": ctrl.attempt_oos(cid),
        "force_select": ctrl.attempt_select_strategy(cid),
        "force_promote": ctrl.attempt_promote_strategy(cid),
        "force_qualify": ctrl.attempt_qualify(cid),
        "force_demo_ready": ctrl.attempt_demo_ready(cid),
        "force_demo_order": ctrl.attempt_demo_order(cid),
        "force_auto_integrate": ctrl.attempt_auto_integrate(),
        "force_exchange_write": ctrl.attempt_exchange_write(),
        "inject_qualified": inject_forbidden_status_attempt(cand0, "QUALIFIED"),
        "inject_promoted": inject_forbidden_status_attempt(cand0, "PROMOTED"),
        "inject_demo_ready": inject_forbidden_status_attempt(cand0, "DEMO_READY"),
        "hard_ban_probe": hard_ban_probe_matrix(cid),
    }
    pass2_summary = ctrl.summary()
    pass2_stable = run_candidate_triage_control(research_bundle, as_of_ms=as_of_ms)

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
        "candidate_count_stable": pass1["ingest"]["ingested_candidate_count"]
        == pass2_stable["ingest"]["ingested_candidate_count"],
        "histogram_stable": pass1["triage"]["status_histogram"]
        == pass2_stable["triage"]["status_histogram"],
        "bundle_checksum_stable": pass1["ingest"]["bundle_checksum"]
        == pass2_stable["ingest"]["bundle_checksum"],
    }

    refusal_keys = (
        "force_walk_forward",
        "force_oos",
        "force_select",
        "force_promote",
        "force_qualify",
        "force_demo_ready",
        "force_demo_order",
        "force_auto_integrate",
        "force_exchange_write",
    )
    adversarial_ok = (
        all(not adversarial[k].get("allowed") for k in refusal_keys)
        and all(
            adversarial[k]["forbidden_accepted"] is False
            for k in ("inject_qualified", "inject_promoted", "inject_demo_ready")
        )
        and adversarial["hard_ban_probe"]["all_refused"] is True
        and all(stability.values())
        and pass2_summary["qualification_ready_count"] == 0
        and pass2_summary["triage"]["forbidden_output_count"] == 0
    )

    both_ok = bool(
        pass1["qualification_ready_count"] == 0
        and pass1["proofs"].get("all_selects_refused")
        and pass1["proofs"].get("all_promotes_refused")
        and pass1["proofs"].get("all_qualifies_refused")
        and pass1["proofs"].get("all_demo_ready_refused")
        and pass1["proofs"].get("forbidden_statuses_absent")
        and pass1["proofs"].get("histogram_covers_all_allowed")
        and pass1["proofs"].get("all_qualification_plans_not_executed")
        and pass1["proofs"].get("all_candidates_connected")
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
                "ingested_candidate_count": pass2_stable["ingest"]["ingested_candidate_count"],
                "status_histogram": pass2_stable["triage"]["status_histogram"],
            },
            "adversarial_ok": adversarial_ok,
        },
        "qualification_status": FORMAL_STATUS_BLOCKED,
        "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
        "triage_control_status": TRIAGE_STATUS_READY,
        "qualification_ready_count": 0,
        "both_passes_ok": both_ok,
    }


def write_immutable_artifacts(
    two_pass: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Path]:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)
    pass1 = two_pass["pass1"]

    def _dump(path: Path, doc: Any) -> None:
        path.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    paths = {
        "status": out_dir / "candidate_triage_status.json",
        "histogram": out_dir / "status_histogram.json",
        "results": out_dir / "triage_results.json",
        "connections": out_dir / "connection_surfaces.json",
        "plans": out_dir / "blocked_qualification_plans.json",
        "bans": out_dir / "hard_ban_proofs.json",
        "flags": out_dir / "control_flags.json",
        "two_pass": out_dir / "two_pass_report.json",
        "summary": out_dir / "candidate_triage_summary.json",
        "ingest": out_dir / "research_ingest.json",
    }

    _dump(
        paths["status"],
        {
            "schema": SCHEMA_ID,
            "lane": LANE,
            "qualification_status": FORMAL_STATUS_BLOCKED,
            "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
            "triage_control_status": TRIAGE_STATUS_READY,
            "qualification_ready_count": 0,
            "allowed_triage_statuses": list(ALLOWED_TRIAGE_STATUSES),
            "forbidden_output_statuses": list(FORBIDDEN_OUTPUT_STATUSES),
            **default_control_flags(),
            "prohibitions": pass1["prohibitions"],
            "created_at": pass1["created_at"],
            "updated_at": pass1["updated_at"],
        },
    )
    _dump(
        paths["histogram"],
        {
            "schema": SCHEMA_ID,
            "status_histogram": pass1["triage"]["status_histogram"],
            "covers_all_allowed": pass1["proofs"].get("histogram_covers_all_allowed"),
            "qualification_ready_count": 0,
            "forbidden_output_count": 0,
        },
    )
    _dump(paths["results"], pass1["triage"])
    _dump(
        paths["connections"],
        {
            "schema": SCHEMA_ID,
            "surfaces": pass1["proofs"].get("connection_surfaces"),
            "all_candidates_connected": pass1["proofs"].get("all_candidates_connected"),
            "connections": pass1["proofs"].get("connections"),
        },
    )
    _dump(
        paths["plans"],
        {
            "schema": SCHEMA_ID,
            "plans": pass1["proofs"].get("blocked_qualification_plans"),
            "all_plans_not_executed": pass1["proofs"].get(
                "all_qualification_plans_not_executed"
            ),
            "formal_walk_forward_executed": False,
            "oos_touched": False,
            "qualification_ready_count": 0,
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
        },
    )
    _dump(paths["summary"], pass1)
    _dump(paths["ingest"], pass1["ingest"])
    return paths

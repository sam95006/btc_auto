"""V15-G OOS Reservation and Seal Control controller (two-pass)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.nexus_oos_seal_control.audit import AccessAuditLog
from backend.nexus_oos_seal_control.bans import (
    assert_required_false_flags,
    default_control_flags,
    hard_ban_probe_matrix,
    refuse_oos_consumption,
    refuse_oos_download,
    refuse_oos_execution,
    refuse_real_oos_reservation,
)
from backend.nexus_oos_seal_control.bindings import (
    build_bindings,
    compute_code_checksum,
    synthetic_candidate,
    synthetic_dataset,
    verify_bindings_intact,
)
from backend.nexus_oos_seal_control.constants import (
    ARTIFACT_REL,
    CONTROL_STATUS_READY,
    EVIDENCE_CLASS,
    FORBIDDEN_STATUS_BASENAMES,
    FORBIDDEN_STATUS_JSON_SUFFIX,
    HARD_BANS,
    INFRA_STATUS_BLOCKED_READY,
    LANE,
    LANE_NAME,
    PLAN_STATUS_PLANNED_NOT_RESERVED,
    SCHEMA_ID,
)
from backend.nexus_oos_seal_control.founder_auth import FounderAuthorizationGate
from backend.nexus_oos_seal_control.intervals import (
    build_interval_plan,
    prove_non_consumption,
    synthetic_planning_registries,
)
from backend.nexus_oos_seal_control.seals import SealLineageStore, build_lineage_seal, reset_seal_lineage


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class OOSSealController:
    """Control plane: plan + seal + prove; never reserve/download/execute/consume."""

    def __init__(self, *, as_of_ms: int = 1_700_000_000_000, root: Path | None = None) -> None:
        self.as_of_ms = as_of_ms
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
        self.audit = AccessAuditLog()
        self.lineage = SealLineageStore()
        self.gate = FounderAuthorizationGate()
        self.created_at = _utc()

    def run_pass1(self) -> dict[str, Any]:
        reset_seal_lineage(self.lineage)
        self.audit.reset()

        candidate = synthetic_candidate()
        dataset = synthetic_dataset(as_of_ms=self.as_of_ms)
        registries = synthetic_planning_registries(as_of_ms=self.as_of_ms)
        plan = build_interval_plan(registries)
        self.audit.record(
            action="INTERVAL_PLAN_BUILD",
            actor="seal_control",
            allowed=True,
            detail={"plan_id": plan["plan_id"], "plan_status": plan["plan_status"]},
        )

        code_checksum = compute_code_checksum(Path(__file__).resolve().parent)
        bindings = build_bindings(
            candidate,
            dataset,
            code_checksum=code_checksum,
            plan_checksum=plan["plan_checksum"],
        )
        bindings_verify = verify_bindings_intact(bindings)
        self.audit.record(
            action="BINDINGS_STAMP",
            actor="seal_control",
            allowed=bindings_verify["intact"],
            detail={"bindings_checksum": bindings["bindings_checksum"]},
        )

        seal = build_lineage_seal(plan=plan, bindings=bindings, store=self.lineage)
        self.audit.record(
            action="LINEAGE_SEAL",
            actor="seal_control",
            allowed=bool(seal.get("allowed")),
            detail={"seal": seal.get("seal"), "status": seal.get("status")},
        )

        # Identical recompute must succeed (write-once idempotent).
        seal_recompute = build_lineage_seal(plan=plan, bindings=bindings, store=self.lineage)
        # Mutated plan must fail closed (anti-regeneration).
        mutated_plan = dict(plan)
        mutated_plan["plan_checksum"] = "0" * 64
        seal_regen = build_lineage_seal(plan=mutated_plan, bindings=bindings, store=self.lineage)
        # force_overwrite must fail closed.
        seal_force = build_lineage_seal(
            plan=plan, bindings=bindings, store=self.lineage, force_overwrite=True
        )

        non_consumption = prove_non_consumption(plan)
        self.audit.record(
            action="NON_CONSUMPTION_PROOF",
            actor="seal_control",
            allowed=bool(non_consumption.get("proven")),
            detail={"status": non_consumption.get("status")},
        )

        founder_auth = self.gate.evaluate()
        spoof = self.gate.attempt_spoof_authorized()
        self.audit.record(
            action="FOUNDER_AUTH_EVALUATE",
            actor="seal_control",
            allowed=True,
            detail={"authorized": False, "spoof_rejected": spoof.get("spoof_rejected")},
        )

        # Attempt real reservation — must refuse.
        reservation_attempt = refuse_real_oos_reservation(plan["plan_id"])
        download_attempt = refuse_oos_download(plan["plan_id"])
        execute_attempt = refuse_oos_execution(plan["plan_id"])
        consume_attempt = refuse_oos_consumption(plan["plan_id"])
        for attempt, action in (
            (reservation_attempt, "REAL_OOS_RESERVATION_ATTEMPT"),
            (download_attempt, "OOS_DOWNLOAD_ATTEMPT"),
            (execute_attempt, "OOS_EXECUTION_ATTEMPT"),
            (consume_attempt, "OOS_CONSUMPTION_ATTEMPT"),
        ):
            self.audit.record(
                action=action,
                actor="adversary_probe",
                allowed=False,
                detail=attempt,
            )

        flags = default_control_flags()
        flag_check = assert_required_false_flags(flags)
        hard_bans = hard_ban_probe_matrix(plan["plan_id"])

        proofs = {
            "interval_plan_built": plan.get("plan_status") == PLAN_STATUS_PLANNED_NOT_RESERVED,
            "bindings_intact": bindings_verify["intact"],
            "seal_allowed": bool(seal.get("allowed")) and seal.get("seal"),
            "seal_recompute_idempotent": bool(seal_recompute.get("allowed"))
            and seal_recompute.get("seal") == seal.get("seal"),
            "anti_regeneration_rejected": seal_regen.get("allowed") is False,
            "write_once_force_rejected": seal_force.get("allowed") is False,
            "non_consumption_proven": bool(non_consumption.get("proven")),
            "founder_auth_absent": founder_auth.get("authorized") is False,
            "founder_auth_proof_valid": bool(founder_auth.get("auth_proof")),
            "founder_spoof_rejected": bool(spoof.get("spoof_rejected")),
            "real_reservation_refused": reservation_attempt.get("allowed") is False,
            "download_refused": download_attempt.get("allowed") is False,
            "execution_refused": execute_attempt.get("allowed") is False,
            "consumption_refused": consume_attempt.get("allowed") is False,
            "required_false_flags_ok": flag_check["ok"],
            "hard_bans_all_refused": hard_bans["all_refused"],
        }

        return {
            "schema": SCHEMA_ID,
            "lane": LANE,
            "lane_name": LANE_NAME,
            "created_at": self.created_at,
            "updated_at": _utc(),
            "evidence_class": EVIDENCE_CLASS,
            "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
            "control_status": CONTROL_STATUS_READY,
            "plan": plan,
            "candidate": candidate,
            "dataset": {
                k: v for k, v in dataset.items() if k != "records"
            },
            "bindings": bindings,
            "bindings_verify": bindings_verify,
            "seal": seal,
            "seal_recompute": {
                "allowed": seal_recompute.get("allowed"),
                "seal": seal_recompute.get("seal"),
                "status": seal_recompute.get("status"),
            },
            "seal_anti_regeneration": {
                "allowed": seal_regen.get("allowed"),
                "status": seal_regen.get("status"),
                "fail_closed": seal_regen.get("fail_closed"),
            },
            "seal_write_once_force": {
                "allowed": seal_force.get("allowed"),
                "status": seal_force.get("status"),
                "fail_closed": seal_force.get("fail_closed"),
            },
            "non_consumption": non_consumption,
            "founder_authorization": founder_auth,
            "founder_spoof_check": spoof,
            "refusal_attempts": {
                "reservation": reservation_attempt,
                "download": download_attempt,
                "execution": execute_attempt,
                "consumption": consume_attempt,
            },
            "flags": flags,
            "required_false_flags": flag_check,
            "hard_ban_probe": hard_bans,
            "access_audit": self.audit.to_dict(),
            "proofs": proofs,
            "pass1_ok": all(proofs.values()),
            "oos_reserved": False,
            "oos_downloaded": False,
            "oos_executed": False,
            "oos_consumed": False,
        }

    def run_pass2(self, pass1: dict[str, Any]) -> dict[str, Any]:
        """Adversarial pass: re-run stable path + mutation attacks."""
        stable = self.run_pass1()

        # Binding mutation must fail intact check.
        mutated_bindings = dict(pass1["bindings"])
        mutated_bindings["bindings_checksum"] = "f" * 64
        binding_attack = verify_bindings_intact(mutated_bindings)

        # Spoof founder auth again.
        spoof = self.gate.attempt_spoof_authorized()

        # Attempt to claim reservation via flag injection.
        injected = dict(pass1["flags"])
        injected["oos_reserved"] = True
        injected["oos_downloaded"] = True
        injected["oos_executed"] = True
        injected["oos_consumed"] = True
        flag_attack = assert_required_false_flags(injected)

        # Force overwrite seal.
        force = build_lineage_seal(
            plan=pass1["plan"],
            bindings=pass1["bindings"],
            store=self.lineage,
            force_overwrite=True,
        )

        hard = hard_ban_probe_matrix(pass1["plan"]["plan_id"])

        stability = {
            "plan_checksum_stable": pass1["plan"]["plan_checksum"] == stable["plan"]["plan_checksum"],
            "bindings_checksum_stable": pass1["bindings"]["bindings_checksum"]
            == stable["bindings"]["bindings_checksum"],
            "seal_stable": pass1["seal"]["seal"] == stable["seal"]["seal"],
            "flags_stable_false": (
                stable["oos_reserved"] is False
                and stable["oos_downloaded"] is False
                and stable["oos_executed"] is False
                and stable["oos_consumed"] is False
            ),
            "pass1_ok_stable": pass1.get("pass1_ok") is True and stable.get("pass1_ok") is True,
        }

        adversarial = {
            "binding_mutation_rejected": binding_attack["intact"] is False,
            "founder_spoof_rejected": bool(spoof.get("spoof_rejected")),
            "flag_injection_detected": flag_attack["ok"] is False
            and set(flag_attack["violations"])
            >= {"oos_reserved", "oos_downloaded", "oos_executed", "oos_consumed"},
            "force_overwrite_refused": force.get("allowed") is False,
            "hard_bans_all_refused": hard["all_refused"],
        }

        adversarial_ok = all(adversarial.values()) and all(stability.values())
        return {
            "stable_rerun": {
                "pass1_ok": stable.get("pass1_ok"),
                "plan_checksum": stable["plan"]["plan_checksum"],
                "bindings_checksum": stable["bindings"]["bindings_checksum"],
                "seal": stable["seal"]["seal"],
                "oos_reserved": False,
                "oos_downloaded": False,
                "oos_executed": False,
                "oos_consumed": False,
            },
            "stability": stability,
            "adversarial": adversarial,
            "adversarial_ok": adversarial_ok,
            "hard_ban_probe": hard,
            "flag_attack": flag_attack,
            "binding_attack": binding_attack,
            "founder_spoof": spoof,
            "force_overwrite": {
                "allowed": force.get("allowed"),
                "status": force.get("status"),
            },
        }


def run_two_pass(*, as_of_ms: int = 1_700_000_000_000, root: Path | None = None) -> dict[str, Any]:
    ctrl = OOSSealController(as_of_ms=as_of_ms, root=root)
    pass1 = ctrl.run_pass1()
    pass2 = ctrl.run_pass2(pass1)
    both_ok = bool(pass1.get("pass1_ok") and pass2.get("adversarial_ok"))
    return {
        "schema": SCHEMA_ID,
        "lane": LANE,
        "pass1": pass1,
        "pass2": pass2,
        "both_passes_ok": both_ok,
        "infrastructure_status": INFRA_STATUS_BLOCKED_READY,
        "control_status": CONTROL_STATUS_READY,
        "oos_reserved": False,
        "oos_downloaded": False,
        "oos_executed": False,
        "oos_consumed": False,
        "hard_bans": list(HARD_BANS),
    }


def _assert_no_status_json(out_dir: Path) -> None:
    for path in out_dir.rglob("*.json"):
        name = path.name.lower()
        if name in FORBIDDEN_STATUS_BASENAMES or name.endswith(FORBIDDEN_STATUS_JSON_SUFFIX):
            raise RuntimeError(f"FORBIDDEN_STATUS_JSON:{path}")


def write_immutable_artifacts(
    two_pass: dict[str, Any],
    *,
    root: Path | None = None,
) -> dict[str, Path]:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    out_dir = base / ARTIFACT_REL
    out_dir.mkdir(parents=True, exist_ok=True)

    def _dump(path: Path, doc: Any) -> None:
        path.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    pass1 = two_pass["pass1"]
    paths = {
        "summary": out_dir / "oos_seal_control_summary.json",
        "plan": out_dir / "interval_plan.json",
        "seal": out_dir / "cryptographic_lineage_seal.json",
        "bindings": out_dir / "bindings.json",
        "non_consumption": out_dir / "non_consumption_proof.json",
        "founder_auth": out_dir / "founder_authorization_proof.json",
        "access_audit": out_dir / "access_audit.json",
        "hard_bans": out_dir / "hard_ban_proofs.json",
        "control_flags": out_dir / "control_flags.json",
        "two_pass": out_dir / "two_pass_report.json",
        "README": out_dir / "README.md",
    }

    _dump(paths["summary"], pass1)
    _dump(paths["plan"], pass1["plan"])
    _dump(paths["seal"], pass1["seal"])
    _dump(paths["bindings"], pass1["bindings"])
    _dump(paths["non_consumption"], pass1["non_consumption"])
    _dump(paths["founder_auth"], pass1["founder_authorization"])
    _dump(paths["access_audit"], pass1["access_audit"])
    _dump(
        paths["hard_bans"],
        {
            "schema": SCHEMA_ID,
            "hard_bans": list(HARD_BANS),
            "probe": pass1["hard_ban_probe"],
            "refusal_attempts": pass1["refusal_attempts"],
        },
    )
    _dump(paths["control_flags"], {"schema": SCHEMA_ID, **default_control_flags()})
    _dump(
        paths["two_pass"],
        {
            "schema": SCHEMA_ID,
            "both_passes_ok": two_pass.get("both_passes_ok"),
            "pass2_adversarial_ok": two_pass["pass2"].get("adversarial_ok"),
            "pass2_stability": two_pass["pass2"].get("stability"),
            "pass2_adversarial": two_pass["pass2"].get("adversarial"),
            "oos_reserved": False,
            "oos_downloaded": False,
            "oos_executed": False,
            "oos_consumed": False,
        },
    )
    paths["README"].write_text(
        "# V15-G OOS Reservation and Seal Control\n\n"
        "Control-plane evidence only. Real OOS reservation/download/execution/consumption "
        "are hard-banned. No `*_status.json` artifacts are emitted by this lane.\n",
        encoding="utf-8",
    )
    _assert_no_status_json(out_dir)
    return paths

"""V16-F Lesson Validation Firewall controller (three-pass)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.nexus_lesson_validation_firewall.bans import (
    assert_no_status_json_filenames,
    assert_required_false_flags,
    default_control_flags,
    hard_ban_probe_matrix,
)
from backend.nexus_lesson_validation_firewall.constants import (
    CONTROL_STATUS,
    EVIDENCE_CLASS_FIXTURE,
    HARD_BANS,
    INFRA_STATUS,
    LANE,
    LANE_NAME,
    PROMOTION_STATES,
    SCHEMA_ID,
)
from backend.nexus_lesson_validation_firewall.fixtures import (
    cherry_pick_attempt_fixture,
    fixture_catalog,
    synthetic_fixture_lesson,
    synthetic_real_lesson_blocked,
)
from backend.nexus_lesson_validation_firewall.gates import evaluate_sot_blockers
from backend.nexus_lesson_validation_firewall.record import ImmutablePromotionRecordStore
from backend.nexus_lesson_validation_firewall.states import LessonPromotionStateMachine


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


PIPELINE_UNTIL_DEMO: tuple[str, ...] = (
    "REPLAY_VALIDATED",
    "WALK_FORWARD_PENDING",
    "OOS_PENDING",
    "SHADOW_PENDING",
    "DEMO_PENDING",
)


class LessonValidationFirewall:
    """Interfaces + fixtures + safety gates. Never marks real Lesson ACTIVE."""

    def __init__(self, *, now_epoch: int = 1_700_000_000) -> None:
        self.now_epoch = now_epoch
        self.created_at = _utc()
        self.record_store = ImmutablePromotionRecordStore()

    def run_pass1_interfaces_fixtures(self) -> dict[str, Any]:
        """Pass 1: interfaces, fixtures, legal pipeline mechanics, ACTIVE block."""
        catalog = fixture_catalog()
        fixture = synthetic_fixture_lesson()
        real = synthetic_real_lesson_blocked()
        sm = LessonPromotionStateMachine(
            fixture, record_store=self.record_store, now_epoch=self.now_epoch
        )

        advances: list[dict[str, Any]] = []
        for target in PIPELINE_UNTIL_DEMO:
            advances.append(sm.attempt_transition(target, actor="founder_operator"))

        active_block = sm.attempt_transition("ACTIVE", actor="founder_operator", force=True)
        skip = sm.attempt_transition("ACTIVE", actor="founder_operator")  # from DEMO_PENDING still blocked
        # Illegal skip from CANDIDATE-like: use a fresh SM
        sm_skip = LessonPromotionStateMachine(
            synthetic_fixture_lesson(lesson_id="FIX_V16F_SKIP"),
            record_store=ImmutablePromotionRecordStore(),
            now_epoch=self.now_epoch,
        )
        illegal_skip = sm_skip.attempt_transition("OOS_PENDING", actor="founder_operator")

        real_sm = LessonPromotionStateMachine(
            real, record_store=ImmutablePromotionRecordStore(), now_epoch=self.now_epoch
        )
        for target in PIPELINE_UNTIL_DEMO:
            real_sm.attempt_transition(target, actor="founder_operator")
        real_active = real_sm.attempt_transition("ACTIVE", actor="founder_operator", force=True)

        flags = default_control_flags()
        flag_check = assert_required_false_flags(flags)
        sot = evaluate_sot_blockers()

        proofs = {
            "pipeline_order_defined": list(PROMOTION_STATES)
            == [
                "CANDIDATE",
                "REPLAY_VALIDATED",
                "WALK_FORWARD_PENDING",
                "OOS_PENDING",
                "SHADOW_PENDING",
                "DEMO_PENDING",
                "ACTIVE",
                "DEGRADED",
                "RETIRED",
            ],
            "fixture_advanced_to_demo_pending": sm.state == "DEMO_PENDING"
            and all(a.get("allowed") for a in advances),
            "fixture_active_blocked": active_block.get("allowed") is False
            and active_block.get("real_lesson_active") is False,
            "real_active_blocked": real_active.get("allowed") is False
            and real_active.get("real_lesson_active") is False,
            "illegal_skip_blocked": illegal_skip.get("allowed") is False,
            "force_active_ignored": active_block.get("force_ignored") is True,
            "required_false_flags_ok": flag_check["ok"],
            "sot_active_blocked": sot.get("active_blocked") is True,
            "no_real_lesson_active_flag": flags.get("real_lesson_active") is False,
            "immutable_records_present": self.record_store.verify_chain().get("ok") is True,
        }
        return {
            "pass": 1,
            "name": "interfaces_fixtures_safety_baseline",
            "schema": SCHEMA_ID,
            "lane": LANE,
            "lane_name": LANE_NAME,
            "created_at": self.created_at,
            "updated_at": _utc(),
            "evidence_class": EVIDENCE_CLASS_FIXTURE,
            "infrastructure_status": INFRA_STATUS,
            "control_status": CONTROL_STATUS,
            "promotion_states": list(PROMOTION_STATES),
            "fixture_catalog_keys": sorted(catalog.keys()),
            "fixture_state": sm.state,
            "real_state": real_sm.state,
            "advances": advances,
            "active_block": {
                "allowed": active_block.get("allowed"),
                "reason": active_block.get("reason"),
                "real_lesson_active": False,
            },
            "real_active_block": {
                "allowed": real_active.get("allowed"),
                "reason": real_active.get("reason"),
                "real_lesson_active": False,
            },
            "illegal_skip": {
                "allowed": illegal_skip.get("allowed"),
                "from_state": illegal_skip.get("from_state"),
                "to_state": illegal_skip.get("to_state"),
            },
            "skip_repeat": {"allowed": skip.get("allowed")},
            "sot_blockers": sot,
            "flags": flags,
            "flag_check": flag_check,
            "hard_bans": list(HARD_BANS),
            "proofs": proofs,
            "pass_ok": all(proofs.values()),
        }

    def run_pass2_adversarial_gates(self) -> dict[str, Any]:
        """Pass 2: adversarial probes — AI self-promote, cherry-pick, mutation, bans."""
        probes = hard_ban_probe_matrix()
        sm = LessonPromotionStateMachine(
            synthetic_fixture_lesson(lesson_id="FIX_V16F_ADV"),
            record_store=ImmutablePromotionRecordStore(),
            now_epoch=self.now_epoch,
        )
        ai_promote = sm.attempt_transition("REPLAY_VALIDATED", actor="ai_agent")
        cherry_sm = LessonPromotionStateMachine(
            cherry_pick_attempt_fixture(),
            record_store=ImmutablePromotionRecordStore(),
            now_epoch=self.now_epoch,
        )
        cherry = cherry_sm.attempt_transition("REPLAY_VALIDATED", actor="founder_operator")
        mut_sm = LessonPromotionStateMachine(
            synthetic_fixture_lesson(lesson_id="FIX_V16F_MUT"),
            record_store=ImmutablePromotionRecordStore(),
            now_epoch=self.now_epoch,
        )
        mutation = mut_sm.attempt_transition(
            "REPLAY_VALIDATED",
            actor="founder_operator",
            mutation={"target": "leverage", "value": 10},
        )

        # Status JSON / report ban probe (in-memory paths only — never write).
        status_paths = [
            "artifacts/readiness/immutable/v16_lesson_validation_firewall/v16_f_status.json",
            "artifacts/readiness/immutable/v16_lesson_validation_firewall/report.json",
        ]
        status_ban_ok = False
        try:
            assert_no_status_json_filenames(status_paths)
        except Exception:
            status_ban_ok = True

        proofs = {
            "hard_bans_all_refused": probes.get("all_refused") is True,
            "ai_self_promote_blocked": ai_promote.get("allowed") is False,
            "cherry_pick_blocked": cherry.get("allowed") is False,
            "production_mutation_blocked": mutation.get("allowed") is False,
            "status_json_paths_banned": status_ban_ok,
            "real_lesson_active_still_false": default_control_flags().get("real_lesson_active")
            is False,
        }
        return {
            "pass": 2,
            "name": "adversarial_safety_gates",
            "updated_at": _utc(),
            "hard_ban_probes": probes,
            "ai_promote": {
                "allowed": ai_promote.get("allowed"),
                "actor_rejected": True,
            },
            "cherry_pick": {"allowed": cherry.get("allowed")},
            "mutation": {"allowed": mutation.get("allowed")},
            "status_json_ban_enforced": status_ban_ok,
            "proofs": proofs,
            "pass_ok": all(proofs.values()),
        }

    def run_pass3_regression_immutability(self) -> dict[str, Any]:
        """Pass 3: regression protection, forgetting guard, immutable record, false-pass harden."""
        store = ImmutablePromotionRecordStore()
        lesson = synthetic_fixture_lesson(lesson_id="FIX_V16F_P3")
        sm = LessonPromotionStateMachine(lesson, record_store=store, now_epoch=self.now_epoch)
        ok_advances = []
        for target in PIPELINE_UNTIL_DEMO:
            ok_advances.append(sm.attempt_transition(target, actor="founder_operator"))

        # Regression fixture: worsen error_rate
        reg_lesson = synthetic_fixture_lesson(lesson_id="FIX_V16F_REG")
        reg_lesson["patched_metrics"] = {
            "error_rate": 0.40,
            "repeat_error_rate": 0.35,
            "coverage": 0.20,
        }
        reg_sm = LessonPromotionStateMachine(
            reg_lesson, record_store=ImmutablePromotionRecordStore(), now_epoch=self.now_epoch
        )
        reg_block = reg_sm.attempt_transition("REPLAY_VALIDATED", actor="founder_operator")

        # Forgetting attack
        forget_lesson = synthetic_fixture_lesson(lesson_id="FIX_V16F_FORGET")
        forget_lesson["drop_prior_ids"] = ["FIX_V16F_PRIOR_A"]
        forget_sm = LessonPromotionStateMachine(
            forget_lesson, record_store=ImmutablePromotionRecordStore(), now_epoch=self.now_epoch
        )
        forget_block = forget_sm.attempt_transition("REPLAY_VALIDATED", actor="founder_operator")

        # Expiry
        expired = synthetic_fixture_lesson(lesson_id="FIX_V16F_EXP")
        expired["expires_at_epoch"] = self.now_epoch - 1
        exp_sm = LessonPromotionStateMachine(
            expired, record_store=ImmutablePromotionRecordStore(), now_epoch=self.now_epoch
        )
        exp_block = exp_sm.attempt_transition("REPLAY_VALIDATED", actor="founder_operator")

        # Contradictory ignore
        contra = synthetic_fixture_lesson(lesson_id="FIX_V16F_CONTRA")
        contra["ignore_contradictory_evidence"] = True
        contra_sm = LessonPromotionStateMachine(
            contra, record_store=ImmutablePromotionRecordStore(), now_epoch=self.now_epoch
        )
        # First step to REPLAY is allowed only if cherry-pick ok; contradiction ignore fails later holds.
        # Force ignore path: after reaching REPLAY, try advance while ignore flag set.
        contra_sm.attempt_transition("REPLAY_VALIDATED", actor="founder_operator")
        contra_hold = contra_sm.attempt_transition("WALK_FORWARD_PENDING", actor="founder_operator")

        # Immutable rewrite attempt
        first_id = f"rec_{lesson['lesson_id']}_CANDIDATE_REPLAY_VALIDATED"
        rewrite = store.attempt_rewrite(first_id, {"outcome": "TAMPERED_ACTIVE"})
        chain = store.verify_chain()

        # Retire path still allowed
        retire_sm = LessonPromotionStateMachine(
            synthetic_fixture_lesson(lesson_id="FIX_V16F_RETIRE"),
            record_store=ImmutablePromotionRecordStore(),
            now_epoch=self.now_epoch,
        )
        retire = retire_sm.attempt_transition("RETIRED", actor="founder_operator")

        # Final ACTIVE force on good path still blocked
        final_active = sm.attempt_transition("ACTIVE", actor="founder_operator", force=True)

        proofs = {
            "pipeline_to_demo_ok": sm.state == "DEMO_PENDING" and all(a.get("allowed") for a in ok_advances),
            "regression_blocked": reg_block.get("allowed") is False,
            "forgetting_blocked": forget_block.get("allowed") is False,
            "expiry_blocked": exp_block.get("allowed") is False,
            "contradiction_ignore_blocked": contra_hold.get("allowed") is False,
            "immutable_rewrite_rejected": rewrite.get("allowed") is False
            and rewrite.get("unchanged") is True,
            "chain_ok": chain.get("ok") is True,
            "retire_allowed": retire.get("allowed") is True and retire_sm.state == "RETIRED",
            "final_active_still_blocked": final_active.get("allowed") is False
            and final_active.get("real_lesson_active") is False,
            "no_real_active": sm.real_lesson_active is False,
        }
        return {
            "pass": 3,
            "name": "regression_immutability_false_pass_harden",
            "updated_at": _utc(),
            "fixture_final_state": sm.state,
            "regression_block": {"allowed": reg_block.get("allowed")},
            "forgetting_block": {"allowed": forget_block.get("allowed")},
            "expiry_block": {"allowed": exp_block.get("allowed")},
            "contradiction_hold": {"allowed": contra_hold.get("allowed")},
            "rewrite": {
                "allowed": rewrite.get("allowed"),
                "unchanged": rewrite.get("unchanged"),
            },
            "chain": chain,
            "retire": {"allowed": retire.get("allowed"), "state": retire_sm.state},
            "final_active": {
                "allowed": final_active.get("allowed"),
                "real_lesson_active": False,
            },
            "proofs": proofs,
            "pass_ok": all(proofs.values()),
        }


def run_three_pass() -> dict[str, Any]:
    fw = LessonValidationFirewall()
    p1 = fw.run_pass1_interfaces_fixtures()
    p2 = fw.run_pass2_adversarial_gates()
    p3 = fw.run_pass3_regression_immutability()
    all_ok = bool(p1.get("pass_ok") and p2.get("pass_ok") and p3.get("pass_ok"))
    return {
        "schema": SCHEMA_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "infrastructure_status": INFRA_STATUS,
        "control_status": CONTROL_STATUS,
        "three_pass": True,
        "pass1": p1,
        "pass2": p2,
        "pass3": p3,
        "all_passes_ok": all_ok,
        "real_lesson_active": False,
        "blockers": evaluate_sot_blockers().get("block_reasons"),
        "hard_bans": list(HARD_BANS),
        "updated_at": _utc(),
        # Explicit non-writing of status/report artifacts.
        "status_json_written": False,
        "report_written": False,
    }


def summarize_for_return(result: dict[str, Any]) -> dict[str, Any]:
    """Compact return payload: status, tests-oriented flags, blockers (no status file)."""
    return {
        "status": "PASS" if result.get("all_passes_ok") else "FAIL",
        "lane": LANE,
        "real_lesson_active": False,
        "passes": {
            "pass1": bool(result.get("pass1", {}).get("pass_ok")),
            "pass2": bool(result.get("pass2", {}).get("pass_ok")),
            "pass3": bool(result.get("pass3", {}).get("pass_ok")),
        },
        "blockers": list(result.get("blockers") or []),
        "hard_ban_count": len(result.get("hard_bans") or []),
        "status_json_written": False,
        "report_written": False,
    }

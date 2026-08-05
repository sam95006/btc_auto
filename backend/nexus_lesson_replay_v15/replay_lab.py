"""V15-I Lesson Replay Lab — classify historical sims + labeled fixtures."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from backend.nexus_lesson_replay_v15.classification import (
    classify_from_evidence,
    error_signature,
)
from backend.nexus_lesson_replay_v15.constants import (
    CONTROL_FIXTURE_LABEL,
    REPLAY_LAB_LABEL,
    SCHEMA_REPLAY,
)
from backend.nexus_lesson_replay_v15.fixtures import (
    fixture_controls_manifest,
    labeled_fixture_controls,
    prohibited_effect_probe,
)
from backend.nexus_lesson_replay_v15.gate import reject_forbidden_effect
from backend.nexus_lesson_replay_v15.simulated_trades import (
    historical_simulated_completed_trades,
    simulated_trades_manifest,
)


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def classify_matrix(packets: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [classify_from_evidence(p) for p in packets]
    by_class: dict[str, int] = {}
    for r in rows:
        cls = r["process_classification"]
        by_class[cls] = by_class.get(cls, 0) + 1
    loss_not_auto_bad = all(
        not (
            r["is_loss"]
            and r["deterministic_process_status"] == "PROCESS_COMPLIANT"
            and r["is_bad_process"]
        )
        for r in rows
    )
    return {
        "packet_count": len(packets),
        "class_counts": by_class,
        "rows": [
            {
                "trade_id": r.get("trade_id"),
                "process_classification": r["process_classification"],
                "source_kind": r.get("source_kind"),
                "pnl": r["pnl"],
                "is_fixture": bool(
                    next(
                        (p.get("is_fixture") for p in packets if p.get("trade_id") == r.get("trade_id")),
                        False,
                    )
                ),
            }
            for r in rows
        ],
        "loss_is_not_automatic_bad_process": loss_not_auto_bad,
        "required_classes_present": {
            "GOOD_PROCESS_WIN": by_class.get("GOOD_PROCESS_WIN", 0) >= 1,
            "GOOD_PROCESS_LOSS": by_class.get("GOOD_PROCESS_LOSS", 0) >= 1,
            "BAD_PROCESS_WIN": by_class.get("BAD_PROCESS_WIN", 0) >= 1,
            "BAD_PROCESS_LOSS": by_class.get("BAD_PROCESS_LOSS", 0) >= 1,
            "UNDETERMINED": by_class.get("UNDETERMINED", 0) >= 1,
        },
    }


def _good_process_loss_non_suppression(packets: list[dict[str, Any]]) -> dict[str, Any]:
    gpl = [
        p
        for p in packets
        if classify_from_evidence(p)["process_classification"] == "GOOD_PROCESS_LOSS"
    ]
    if not gpl:
        return {
            "good_process_loss_non_suppression_status": "FAIL",
            "reason": "missing_good_process_loss",
            "auto_block_all_similar_valid_trades": False,
            "block_created": False,
        }
    source = gpl[0]
    suppressed = False
    for p in packets:
        c = classify_from_evidence(p)
        if (
            p is not source
            and c["is_good_process"]
            and p.get("symbol") == source.get("symbol")
            and bool(p.get("_suppressed_by_good_process_loss"))
        ):
            suppressed = True
    return {
        "source_trade_id": source.get("trade_id"),
        "good_process_loss_count": len(gpl),
        "auto_block_all_similar_valid_trades": False,
        "block_created": False,
        "good_process_loss_non_suppression_status": "FAIL" if suppressed else "PASS",
    }


def run_replay_lab() -> dict[str, Any]:
    """Replay historical simulated trades + labeled fixtures; detect all five classes.

    Does NOT execute Real Lesson Prevention. Observation / classification only.
    """
    sims = historical_simulated_completed_trades()
    fixtures = labeled_fixture_controls()
    combined = list(sims) + list(fixtures)

    sim_matrix = classify_matrix(sims)
    fix_matrix = classify_matrix(fixtures)
    combined_matrix = classify_matrix(combined)

    # Fixtures must remain clearly labelled and never count as real policy-effect.
    fixture_labels_ok = all(
        p.get("is_fixture") and p.get("fixture_label") == CONTROL_FIXTURE_LABEL for p in fixtures
    )
    sims_not_fixtures = all(not p.get("is_fixture") for p in sims)
    sims_labelled = all(p.get("historical_sim_label") for p in sims)

    # Observation of repeatable error signature across historical sims (no policy lesson emit).
    bad_sims = [p for p in sims if classify_from_evidence(p)["is_bad_process"]]
    signatures = {error_signature(p): p.get("trade_id") for p in bad_sims}
    repeat_obs = []
    seen: dict[str, str] = {}
    for p in bad_sims:
        sig = error_signature(p)
        if sig in seen:
            repeat_obs.append(
                {
                    "signature": sig,
                    "first_trade_id": seen[sig],
                    "later_trade_id": p.get("trade_id"),
                    "policy_effect_emitted": False,
                }
            )
        else:
            seen[sig] = str(p.get("trade_id"))

    probe = prohibited_effect_probe()
    reject = reject_forbidden_effect(probe["requested_effect"])
    hard_risk_override_path_test_status = (
        "PASS"
        if (
            probe["ai_or_lesson_requested_prohibited_action"]
            and reject["deterministic_rejected"]
            and not probe["order_or_policy_mutation"]
        )
        else "FAIL"
    )

    gpl = _good_process_loss_non_suppression(combined)

    classes_ok = all(combined_matrix["required_classes_present"].values()) and all(
        sim_matrix["required_classes_present"].values()
    ) and all(fix_matrix["required_classes_present"].values())

    lab_pass = (
        classes_ok
        and combined_matrix["loss_is_not_automatic_bad_process"]
        and fixture_labels_ok
        and sims_not_fixtures
        and sims_labelled
        and hard_risk_override_path_test_status == "PASS"
        and gpl["good_process_loss_non_suppression_status"] == "PASS"
        and len(bad_sims) >= 1
    )

    return {
        "schema": SCHEMA_REPLAY,
        "label": REPLAY_LAB_LABEL,
        "control_fixture_label": CONTROL_FIXTURE_LABEL,
        "replay_lab_status": "PASS" if lab_pass else "FAIL",
        "misrepresented_as_real_learning": False,
        "fixture_as_real_policy_effect_proof": False,
        "new_policy_effect_lesson_count": 0,
        "REAL_LESSON_PREVENTION_STATUS": "NOT_THIS_PROOF_REMAINS_BLOCKED",
        "historical_simulated_trade_count": len(sims),
        "labeled_fixture_count": len(fixtures),
        "combined_packet_count": len(combined),
        "classification_matrix": {
            "combined": {
                "class_counts": combined_matrix["class_counts"],
                "loss_is_not_automatic_bad_process": combined_matrix[
                    "loss_is_not_automatic_bad_process"
                ],
                "required_classes_present": combined_matrix["required_classes_present"],
            },
            "historical_simulated": {
                "class_counts": sim_matrix["class_counts"],
                "required_classes_present": sim_matrix["required_classes_present"],
                "rows": sim_matrix["rows"],
            },
            "labeled_fixtures": {
                "class_counts": fix_matrix["class_counts"],
                "required_classes_present": fix_matrix["required_classes_present"],
                "rows": fix_matrix["rows"],
                "clearly_labelled": fixture_labels_ok,
            },
        },
        "repeat_error_observations": repeat_obs,
        "bad_process_sim_count": len(bad_sims),
        "unique_bad_signatures": list(signatures.keys()),
        "hard_risk_override_path_test_status": hard_risk_override_path_test_status,
        "hard_risk_override_attempt": {**probe, **reject, "deterministic_risk_final": True},
        "good_process_loss_non_suppression": gpl,
        "simulated_trades_manifest": {
            k: v for k, v in simulated_trades_manifest().items() if k != "trades"
        },
        "fixture_controls_manifest": {
            k: v for k, v in fixture_controls_manifest().items() if k != "packets"
        },
        "exchange_write_attempt_count": 0,
        "demo_order_count": 0,
        "mainnet": False,
        "real_money": False,
        "proof_digest": _sha(
            {
                "sim_counts": sim_matrix["class_counts"],
                "fix_counts": fix_matrix["class_counts"],
                "lab_pass": lab_pass,
                "repeat_obs": len(repeat_obs),
            }
        ),
    }

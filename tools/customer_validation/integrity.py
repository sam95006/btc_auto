"""Integrity counters and THREE-PASS proof for PUB2-G Concierge app."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.customer_validation.hard_bans import HARD_BANS, assert_hard_bans
from tools.customer_validation.store import COLLECTIONS, ensure_workspace, load_collection
from tools.customer_validation.workflow_spine import (
    REQUIRED_ZERO_UNTIL_REAL,
    WORKFLOW_STEPS,
    compute_workflow_counters,
    workflow_spine_status,
)

# Backward-compatible alias used by PUB-I tests / imports
REQUIRED_ZERO_COUNTERS = (
    "real_participant_count",
    "completed_interview_count",
    "paid_pilot_count",
)


def compute_counters(workspace=None) -> dict[str, int]:
    """Full workflow counters (zeros until real participation)."""
    return compute_workflow_counters(workspace)


def build_integrity_snapshot(workspace=None) -> dict[str, Any]:
    root = ensure_workspace(workspace)
    counters = compute_counters(root)
    collection_lens = {name: len(load_collection(name, root)) for name in COLLECTIONS}
    bans = assert_hard_bans()
    spine = workflow_spine_status(root)
    body = {
        "schema": "NEXUS_CUSTOMER_VALIDATION_INTEGRITY_V2",
        "lane": "PUB2-G",
        "workspace": str(root),
        "production_customer_database": False,
        "counters": counters,
        "collection_lengths": collection_lens,
        "required_zero_counters": list(REQUIRED_ZERO_COUNTERS),
        "required_zero_until_real": list(REQUIRED_ZERO_UNTIL_REAL),
        "required_zeros_ok": all(counters[k] == 0 for k in REQUIRED_ZERO_UNTIL_REAL),
        "hard_bans": list(HARD_BANS),
        "hard_bans_honored": bans["hard_bans_honored"],
        "workflow_steps": list(WORKFLOW_STEPS),
        "tools": [
            "registry",
            "consent",
            "interview",
            "problem_ranking",
            "workflow",
            "watchlist_onboarding",
            "decision_object_concierge",
            "weekly_review",
            "retention_evidence",
            "wtp_evidence",
            "objection_taxonomy",
            "conversion_evidence",
            "workflow_spine",
            "concierge_app",
        ],
        "target_cohort": {"min": 10, "max": 20},
        "status_json_emitted": False,
        "spine_all_required_zeros": spine["all_required_zeros"],
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["digest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return body


def run_two_pass_integrity(workspace=None) -> dict[str, Any]:
    """Compatibility wrapper: first two digests of the three-pass runner."""
    three = run_three_pass_integrity(workspace)
    return {
        "schema": "NEXUS_CUSTOMER_VALIDATION_TWO_PASS_V1",
        "pass_count": 2,
        "pass1_digest": three["pass1_digest"],
        "pass2_digest": three["pass2_digest"],
        "digests_match": three["pass1_digest"] == three["pass2_digest"],
        "required_zeros_ok": three["required_zeros_ok"],
        "counters": three["counters"],
        "hard_bans_honored": three["hard_bans_honored"],
        "ok": three["pass1_digest"] == three["pass2_digest"]
        and three["required_zeros_ok"]
        and three["hard_bans_honored"],
        "status_json_emitted": False,
        "pass1": three["pass1"],
        "pass2": three["pass2"],
        "note": "No *_status.json emitted by design.",
    }


def run_three_pass_integrity(workspace=None) -> dict[str, Any]:
    """THREE PASSES: recompute integrity thrice and require identical digests."""
    pass1 = build_integrity_snapshot(workspace)
    pass2 = build_integrity_snapshot(workspace)
    pass3 = build_integrity_snapshot(workspace)
    digests = [
        pass1["digest_sha256"],
        pass2["digest_sha256"],
        pass3["digest_sha256"],
    ]
    matched = len(set(digests)) == 1
    zeros_ok = (
        pass1["required_zeros_ok"]
        and pass2["required_zeros_ok"]
        and pass3["required_zeros_ok"]
    )
    return {
        "schema": "NEXUS_PUB2_G_CONCIERGE_THREE_PASS_V1",
        "lane": "PUB2-G",
        "pass_count": 3,
        "pass1_digest": digests[0],
        "pass2_digest": digests[1],
        "pass3_digest": digests[2],
        "digests_match": matched,
        "required_zeros_ok": zeros_ok,
        "counters": pass1["counters"],
        "hard_bans_honored": pass1["hard_bans_honored"],
        "ok": matched and zeros_ok and pass1["hard_bans_honored"],
        "status_json_emitted": False,
        "pass1": pass1,
        "pass2": pass2,
        "pass3": pass3,
        "note": "No *_status.json emitted by design. Counters stay 0 until real people participate.",
    }


def write_two_pass_proof(out_dir: Path | str, workspace=None) -> Path:
    """Write two-pass proof JSON (never named *_status.json)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    proof = run_two_pass_integrity(workspace)
    path = out / "customer_validation_two_pass_proof.json"
    if path.name.endswith("_status.json"):
        raise RuntimeError("refusing to write *_status.json")
    path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_three_pass_proof(out_dir: Path | str, workspace=None) -> Path:
    """Write three-pass proof JSON (never named *_status.json)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    proof = run_three_pass_integrity(workspace)
    path = out / "customer_validation_concierge_three_pass_proof.json"
    if path.name.endswith("_status.json"):
        raise RuntimeError("refusing to write *_status.json")
    path.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

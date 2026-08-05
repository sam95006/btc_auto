"""Integrity counters and two-pass proof for PUB-I."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from tools.customer_validation.evidence import paid_pilot_count
from tools.customer_validation.hard_bans import HARD_BANS, assert_hard_bans
from tools.customer_validation.interview import completed_interview_count
from tools.customer_validation.registry import real_participant_count
from tools.customer_validation.store import COLLECTIONS, ensure_workspace, load_collection

REQUIRED_ZERO_COUNTERS = (
    "real_participant_count",
    "completed_interview_count",
    "paid_pilot_count",
)


def compute_counters(workspace=None) -> dict[str, int]:
    return {
        "real_participant_count": real_participant_count(workspace),
        "completed_interview_count": completed_interview_count(workspace),
        "paid_pilot_count": paid_pilot_count(workspace),
        "fabricated_result_count": _fabricated_flag_count(workspace),
    }


def _fabricated_flag_count(workspace=None) -> int:
    total = 0
    for name in COLLECTIONS:
        for row in load_collection(name, workspace):
            if row.get("fabricated") is True:
                total += 1
    return total


def build_integrity_snapshot(workspace=None) -> dict[str, Any]:
    root = ensure_workspace(workspace)
    counters = compute_counters(root)
    collection_lens = {name: len(load_collection(name, root)) for name in COLLECTIONS}
    bans = assert_hard_bans()
    body = {
        "schema": "NEXUS_CUSTOMER_VALIDATION_INTEGRITY_V1",
        "workspace": str(root),
        "production_customer_database": False,
        "counters": counters,
        "collection_lengths": collection_lens,
        "required_zero_counters": list(REQUIRED_ZERO_COUNTERS),
        "required_zeros_ok": all(counters[k] == 0 for k in REQUIRED_ZERO_COUNTERS),
        "hard_bans": list(HARD_BANS),
        "hard_bans_honored": bans["hard_bans_honored"],
        "tools": [
            "registry",
            "consent",
            "interview",
            "problem_ranking",
            "workflow",
            "decision_object_concierge",
            "weekly_review",
            "retention_evidence",
            "wtp_evidence",
            "objection_taxonomy",
            "conversion_evidence",
        ],
        "target_cohort": {"min": 10, "max": 20},
        "status_json_emitted": False,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["digest_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return body


def run_two_pass_integrity(workspace=None) -> dict[str, Any]:
    """TWO PASSES: recompute integrity and require identical digests."""
    pass1 = build_integrity_snapshot(workspace)
    pass2 = build_integrity_snapshot(workspace)
    matched = pass1["digest_sha256"] == pass2["digest_sha256"]
    zeros_ok = pass1["required_zeros_ok"] and pass2["required_zeros_ok"]
    return {
        "schema": "NEXUS_CUSTOMER_VALIDATION_TWO_PASS_V1",
        "pass_count": 2,
        "pass1_digest": pass1["digest_sha256"],
        "pass2_digest": pass2["digest_sha256"],
        "digests_match": matched,
        "required_zeros_ok": zeros_ok,
        "counters": pass1["counters"],
        "hard_bans_honored": pass1["hard_bans_honored"],
        "ok": matched and zeros_ok and pass1["hard_bans_honored"],
        "status_json_emitted": False,
        "pass1": pass1,
        "pass2": pass2,
        "note": "No *_status.json emitted by design.",
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

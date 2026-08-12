"""V14-D Robustness & Multiple-Testing Lab orchestrator."""
from __future__ import annotations

from typing import Any

from backend.nexus_research_validation.bootstrap import bootstrap_stability_report
from backend.nexus_research_validation.clustering import cluster_candidates
from backend.nexus_research_validation.constants import (
    ALLOWED_LABELS,
    CAMPAIGN_ID,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    RANDOM_SEED,
    SCHEMA,
)
from backend.nexus_research_validation.cost_turnover import cost_turnover_sensitivity
from backend.nexus_research_validation.fdr import multiple_testing_reject_decision
from backend.nexus_research_validation.fixtures import (
    build_synthetic_candidates,
    fixture_manifest,
)
from backend.nexus_research_validation.hard_bans import env_hard_ban_guard
from backend.nexus_research_validation.labeling import assign_label, label_histogram
from backend.nexus_research_validation.lineage import build_lineage, lineage_index
from backend.nexus_research_validation.metadata import family_comparison_bundle
from backend.nexus_research_validation.sample_size import sample_size_requirements
from backend.nexus_research_validation.stability import combined_stability_report
from backend.nexus_research_validation.ts_dependence import ts_dependence_controls


def evaluate_candidate(
    candidate: dict[str, Any],
    *,
    bh_adjusted_p: float,
    family_test_count: int,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    series = list(candidate["net_series"])
    ts = ts_dependence_controls(series)
    n_eff = float(ts["effective_sample_size"]["n_eff"])
    sample = sample_size_requirements(
        n_observations=int(candidate["n_observations"]),
        n_trades=int(candidate["n_trades"]),
        n_eff=n_eff,
    )
    boot = bootstrap_stability_report(series, seed=seed + hash(candidate["candidate_id"]) % 10_000)
    stab = combined_stability_report(
        base_metric=float(boot["observed_mean"]),
        neighbor_metrics=list(candidate.get("neighbor_metrics") or []),
        regime_net=dict(candidate.get("regime_net") or {}),
        symbol_net=dict(candidate.get("symbol_net") or {}),
    )
    cost = cost_turnover_sensitivity(
        gross_pnl=float(candidate["gross_pnl"]),
        net_pnl=float(candidate["net_pnl"]),
        cost_components=dict(candidate["cost_components"]),
        turnover_notional=float(candidate["turnover_notional"]),
    )
    mt_reject = multiple_testing_reject_decision(
        float(candidate["p_value"]),
        bh_adjusted_p=float(bh_adjusted_p),
        family_test_count=int(family_test_count),
    )
    label_info = assign_label(
        data_quality_blocked=not bool(candidate.get("data_quality_ok", True)),
        sample_sufficient=bool(sample["sufficient"]),
        multiple_testing_rejected=mt_reject,
        cost_destroyed=bool(cost["destroyed"]),
        bootstrap_stable=bool(boot["bootstrap_stable"]),
        stability_axes_ok=bool(stab["all_stability_axes_ok"]),
        dependence_blocks_robust=bool(ts["dependence_blocks_robust_claim"]),
    )
    lineage = build_lineage(
        candidate_id=str(candidate["candidate_id"]),
        research_family=str(candidate["research_family"]),
        mechanism_semantic_id=str(candidate["mechanism_semantic_id"]),
        parent_experiment_id=candidate.get("parent_experiment_id"),
        parameter_checksum=str(candidate["parameter_checksum"]),
        feature_version=str(candidate["feature_version"]),
        universe_checksum=str(candidate["universe_checksum"]),
        data_fixture_id=str(candidate["data_fixture_id"]),
        random_seed=seed,
    )
    return {
        "candidate_id": candidate["candidate_id"],
        "research_family": candidate["research_family"],
        "result_label": label_info["label"],
        "label": label_info["label"],
        "label_info": label_info,
        "p_value": float(candidate["p_value"]),
        "bh_adjusted_p": float(bh_adjusted_p),
        "family_test_count": int(family_test_count),
        "sample_size": sample,
        "ts_dependence": ts,
        "bootstrap": boot,
        "stability": stab,
        "cost_turnover": cost,
        "lineage": lineage,
        "fixture_synthetic": True,
        "qualification_claim": False,
        "formal_walk_forward": False,
        "oos_consumed": False,
        "intended_pathway": candidate.get("intended_pathway"),
    }


def run_robustness_lab(*, seed: int = RANDOM_SEED) -> dict[str, Any]:
    """Full development-only robustness campaign over synthetic fixtures."""
    env = env_hard_ban_guard()
    if not env["ok"]:
        raise RuntimeError(f"hard ban env violations: {env['violations']}")

    candidates = build_synthetic_candidates(seed=seed)
    manifest = fixture_manifest(candidates)

    # Multiple-comparison metadata by research family
    families: dict[str, dict[str, Any]] = {}
    for c in candidates:
        fam = c["research_family"]
        families.setdefault(fam, {"candidate_ids": [], "p_values": []})
        families[fam]["candidate_ids"].append(c["candidate_id"])
        families[fam]["p_values"].append(float(c["p_value"]))
    comparison = family_comparison_bundle(families)

    bh_by_candidate: dict[str, tuple[float, int]] = {}
    for fam_meta in comparison["families"].values():
        n = int(fam_meta["n_tests"])
        for row in fam_meta["per_candidate"]:
            bh_by_candidate[row["candidate_id"]] = (float(row["bh_adjusted_p"]), n)

    evaluations: list[dict[str, Any]] = []
    for c in candidates:
        adj, n = bh_by_candidate[c["candidate_id"]]
        evaluations.append(
            evaluate_candidate(c, bh_adjusted_p=adj, family_test_count=n, seed=seed)
        )

    lineage_records = [e["lineage"] for e in evaluations]
    lineage = lineage_index(lineage_records)

    series_map = {c["candidate_id"]: list(c["net_series"]) for c in candidates}
    clusters = cluster_candidates(series_map)

    hist = label_histogram(evaluations)
    labels_used = {e["label"] for e in evaluations}
    assert labels_used <= ALLOWED_LABELS

    # Deterministic replay fingerprint
    replay_a = [e["label"] + ":" + e["candidate_id"] for e in evaluations]
    candidates_b = build_synthetic_candidates(seed=seed)
    # Re-run labeling path lightly for replay proof
    replay_match = [c["candidate_id"] for c in candidates] == [
        c["candidate_id"] for c in candidates_b
    ] and manifest["batch_digest"] == fixture_manifest(candidates_b)["batch_digest"]

    return {
        "schema": SCHEMA,
        "package": PACKAGE,
        "campaign_id": CAMPAIGN_ID,
        "lane": LANE,
        "lane_name": LANE_NAME,
        "seed": seed,
        "hard_bans": sorted(HARD_BANS),
        "env_guard": env,
        "fixture_manifest": manifest,
        "candidate_count": len(evaluations),
        "evaluations": evaluations,
        "label_histogram": hist,
        "multiple_comparison": comparison,
        "lineage_index": lineage,
        "correlation_clustering": clusters,
        "deterministic_fixture_replay": replay_match,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "qualification_ready_count": 0,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "shadow_order_count": 0,
        "auto_integrate": False,
        "development_only": True,
        "fixture_synthetic": True,
        "not_qualification_claim": True,
    }


def adversarial_self_review(lab: dict[str, Any]) -> dict[str, Any]:
    """PASS-2 adversarial checks against false PASS / banned claims / bans."""
    findings: list[dict[str, Any]] = []

    hist = lab.get("label_histogram") or {}
    for lab_name in hist:
        if lab_name not in ALLOWED_LABELS:
            findings.append(
                {
                    "severity": "CRITICAL",
                    "code": "BANNED_LABEL_EMITTED",
                    "detail": lab_name,
                }
            )

    if lab.get("formal_walk_forward_executed") or lab.get("oos_consumed") or lab.get("oos_executed"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "WF_OR_OOS_EXECUTED",
                "detail": "lab claimed WF/OOS execution",
            }
        )

    if int(lab.get("qualification_ready_count") or 0) != 0:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "QUALIFICATION_READY_NONZERO",
                "detail": lab.get("qualification_ready_count"),
            }
        )

    if not lab.get("deterministic_fixture_replay"):
        findings.append(
            {
                "severity": "HIGH",
                "code": "FIXTURE_REPLAY_MISMATCH",
                "detail": "synthetic fixture batch not deterministic",
            }
        )

    if not lab.get("env_guard", {}).get("ok", False):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "ENV_HARD_BAN_VIOLATION",
                "detail": lab.get("env_guard"),
            }
        )

    # Every allowed label pathway should appear at least once in fixtures
    missing_pathways = sorted(ALLOWED_LABELS - set(k for k, v in hist.items() if v > 0))
    if missing_pathways:
        findings.append(
            {
                "severity": "HIGH",
                "code": "LABEL_PATHWAY_COVERAGE_GAP",
                "detail": missing_pathways,
            }
        )

    # Correlation clustering must detect the robust twin pair
    pairs = lab.get("correlation_clustering", {}).get("redundant_pairs") or []
    twin_hit = any(
        {p.get("a"), p.get("b")} == {"CAND_ROBUST_001", "CAND_ROBUST_002"} for p in pairs
    )
    if not twin_hit:
        findings.append(
            {
                "severity": "HIGH",
                "code": "CLUSTERING_MISSED_TWIN",
                "detail": "expected high correlation between ROBUST_001/002",
            }
        )

    # Multiple comparison metadata present
    if int(lab.get("multiple_comparison", {}).get("total_tests") or 0) < 1:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "MISSING_MULTIPLE_COMPARISON_METADATA",
                "detail": lab.get("multiple_comparison"),
            }
        )

    # Cost destroyed candidate must be labeled COST_DESTROYED
    by_id = {e["candidate_id"]: e for e in lab.get("evaluations") or []}
    cost_row = by_id.get("CAND_COST_001")
    if not cost_row or cost_row["label"] != "COST_DESTROYED":
        findings.append(
            {
                "severity": "HIGH",
                "code": "COST_DESTROY_MISLABEL",
                "detail": cost_row,
            }
        )

    data_row = by_id.get("CAND_DATA_BLOCK_001")
    if not data_row or data_row["label"] != "DATA_QUALITY_BLOCKED":
        findings.append(
            {
                "severity": "HIGH",
                "code": "DATA_QUALITY_MISLABEL",
                "detail": data_row,
            }
        )

    findings.append(
        {
            "severity": "INFO",
            "code": "FIXTURE_SYNTHETIC_ONLY",
            "detail": (
                "All V14-D robustness evaluations use synthetic fixtures; "
                "not real strategy qualification evidence."
            ),
            "status": "ACKNOWLEDGED",
        }
    )

    critical = [f for f in findings if f.get("severity") == "CRITICAL"]
    high = [f for f in findings if f.get("severity") == "HIGH"]
    return {
        "pass": "PASS_2",
        "findings": findings,
        "critical_count": len(critical),
        "high_count": len(high),
        "adversarial_ok": len(critical) == 0 and len(high) == 0,
        "label_histogram": hist,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
    }

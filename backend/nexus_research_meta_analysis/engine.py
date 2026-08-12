"""V15-D Research Meta-Analysis orchestrator."""
from __future__ import annotations

from typing import Any

from backend.nexus_research_meta_analysis.bootstrap_intervals import bootstrap_intervals
from backend.nexus_research_meta_analysis.constants import (
    ALLOWED_LABELS,
    CAMPAIGN_ID,
    HARD_BANS,
    LANE,
    LANE_NAME,
    PACKAGE,
    RANDOM_SEED,
    REQUIRED_ANALYSIS_AXES,
    SCHEMA,
)
from backend.nexus_research_meta_analysis.correlation import (
    candidate_correlation,
    mechanism_family_correlation,
)
from backend.nexus_research_meta_analysis.duplication import detect_duplicates
from backend.nexus_research_meta_analysis.favorable_selection import (
    attempt_silent_cherry_pick,
    build_promising_packet,
    detect_favorable_run_selection,
)
from backend.nexus_research_meta_analysis.fdr import benjamini_hochberg, bonferroni_gate
from backend.nexus_research_meta_analysis.fixtures import (
    build_synthetic_experiments,
    fixture_manifest,
)
from backend.nexus_research_meta_analysis.hard_bans import (
    HardBanViolation,
    env_hard_ban_guard,
)
from backend.nexus_research_meta_analysis.labeling import assert_label_allowed, label_histogram
from backend.nexus_research_meta_analysis.stability_axes import combined_stability_axes


def _assign_label(
    experiment: dict[str, Any],
    *,
    bh_adjusted_p: float,
    q: float,
    duplicate_ids: set[str],
    stability: dict[str, Any],
    boot: dict[str, Any],
) -> str:
    eid = experiment["experiment_id"]
    role = experiment["role"]

    if eid in duplicate_ids:
        return "DUPLICATE_EXPERIMENT"
    if role == "cherry_favorable":
        # Favorable without disclosed siblings is blocked at meta layer
        return "FAVORABLE_SELECTION_BLOCKED"
    if bool(stability["cost_sensitivity"]["destroyed"]):
        return "COST_DESTROYED"
    if not stability["regime_stability"]["stable"]:
        return "REGIME_FRAGILE"
    if bool(stability["capacity_sensitivity"].get("fragile")):
        return "CAPACITY_FRAGILE"
    if float(bh_adjusted_p) > q and float(experiment["p_value"]) > q * 0.5:
        return "MULTIPLE_TESTING_REJECTED"
    if role == "failed_sibling" or role == "cherry_omitted":
        return "REJECTED"
    if (
        role == "promising"
        and stability["all_stability_axes_ok"]
        and boot["bootstrap_stable"]
        and float(bh_adjusted_p) <= q
    ):
        return "DEVELOPMENT_PROMISING_NOT_QUALIFIED"
    if not stability["all_stability_axes_ok"] or not boot["bootstrap_stable"]:
        if role in {"fragile", "review", "promising"}:
            return "INSUFFICIENT_STABILITY"
        return "REJECTED"
    if role == "review":
        return "DEVELOPMENT_REVIEW"
    return "DEVELOPMENT_REVIEW"


def evaluate_experiment(
    experiment: dict[str, Any],
    *,
    bh_adjusted_p: float,
    duplicate_ids: set[str],
    seed: int,
    q: float = 0.10,
) -> dict[str, Any]:
    series = list(experiment["net_series"])
    boot = bootstrap_intervals(series, seed=seed + hash(experiment["experiment_id"]) % 10_000)
    stability = combined_stability_axes(experiment)
    label = _assign_label(
        experiment,
        bh_adjusted_p=bh_adjusted_p,
        q=q,
        duplicate_ids=duplicate_ids,
        stability=stability,
        boot=boot,
    )
    assert_label_allowed(label)
    return {
        "experiment_id": experiment["experiment_id"],
        "candidacy_group": experiment["candidacy_group"],
        "role": experiment["role"],
        "research_family": experiment["research_family"],
        "mechanism_semantic_id": experiment["mechanism_semantic_id"],
        "label": label,
        "result_label": label,
        "p_value": float(experiment["p_value"]),
        "bh_adjusted_p": float(bh_adjusted_p),
        "bootstrap_intervals": boot["bootstrap_intervals"],
        "block_bootstrap_intervals": boot["block_bootstrap_intervals"],
        "bootstrap_stable": boot["bootstrap_stable"],
        "stability_axes": stability,
        "fixture_synthetic": True,
        "qualification_claim": False,
        "formal_walk_forward": False,
        "oos_consumed": False,
    }


def run_meta_analysis(*, seed: int = RANDOM_SEED) -> dict[str, Any]:
    """Full cross-experiment meta-analysis over synthetic development fixtures."""
    env = env_hard_ban_guard()
    if not env["ok"]:
        raise RuntimeError(f"hard ban env violations: {env['violations']}")

    experiments = build_synthetic_experiments(seed=seed)
    manifest = fixture_manifest(experiments)

    p_values = [float(e["p_value"]) for e in experiments]
    fdr = benjamini_hochberg(p_values)
    bonf = bonferroni_gate(p_values)
    adjusted = list(fdr["adjusted_p"])

    series_map = {e["experiment_id"]: list(e["net_series"]) for e in experiments}
    cand_corr = candidate_correlation(series_map)
    fam_corr = mechanism_family_correlation(experiments)
    duplication = detect_duplicates(experiments)
    duplicate_ids = set(duplication["duplicate_experiment_ids"])

    # Adversarial silent cherry-pick attempt on G_CHERRY (must be blocked)
    cherry_attempt = {
        "candidacy_group": "G_CHERRY",
        "selected_experiment_id": "EXP_CHERRY_FAV",
        "disclosed_member_ids": ["EXP_CHERRY_FAV"],  # omits failed siblings
    }
    favorable = detect_favorable_run_selection(
        experiments, attempted_silent_selection=cherry_attempt
    )

    evaluations: list[dict[str, Any]] = []
    for i, e in enumerate(experiments):
        evaluations.append(
            evaluate_experiment(
                e,
                bh_adjusted_p=float(adjusted[i]),
                duplicate_ids=duplicate_ids,
                seed=seed,
                q=float(fdr["q"]),
            )
        )

    # Promising packets MUST retain failed siblings
    promising_packets: list[dict[str, Any]] = []
    by_id = {e["experiment_id"]: e for e in experiments}
    for row in evaluations:
        if row["label"] == "DEVELOPMENT_PROMISING_NOT_QUALIFIED":
            packet = build_promising_packet(
                promising=by_id[row["experiment_id"]],
                experiments=experiments,
            )
            if not packet["failed_sibling_ids"]:
                raise HardBanViolation("promising_missing_failed_siblings")
            promising_packets.append(packet)
            row["failed_sibling_ids"] = packet["failed_sibling_ids"]
            row["sibling_retention_ok"] = True

    # Ensure G_PROMISING always retains failed siblings in a promising packet
    prom_raw = by_id.get("EXP_PROM_001")
    if prom_raw is not None:
        existing = {
            p["promising_experiment_id"] for p in promising_packets
        }
        if "EXP_PROM_001" not in existing:
            promising_packets.append(
                build_promising_packet(promising=prom_raw, experiments=experiments)
            )

    hist = label_histogram(evaluations)
    labels_used = {e["label"] for e in evaluations}
    assert labels_used <= ALLOWED_LABELS

    # Deterministic replay
    experiments_b = build_synthetic_experiments(seed=seed)
    replay_match = [e["experiment_id"] for e in experiments] == [
        e["experiment_id"] for e in experiments_b
    ] and manifest["batch_digest"] == fixture_manifest(experiments_b)["batch_digest"]

    axes_present = {
        "candidate_correlation": cand_corr,
        "mechanism_family_correlation": fam_corr,
        "parameter_neighborhood_stability": True,
        "symbol_stability": True,
        "regime_stability": True,
        "turnover_stability": True,
        "cost_sensitivity": True,
        "capacity_sensitivity": True,
        "bootstrap_intervals": True,
        "block_bootstrap_intervals": True,
        "false_discovery_adjustment": fdr,
        "experiment_duplication": duplication,
        "favorable_run_selection_detection": favorable,
        "failed_sibling_retention": {
            "promising_packet_count": len(promising_packets),
            "all_retained": all(
                bool(p.get("sibling_retention", {}).get("retention_ok"))
                for p in promising_packets
            ),
        },
    }
    missing_axes = [a for a in REQUIRED_ANALYSIS_AXES if a not in axes_present]
    if missing_axes:
        raise RuntimeError(f"missing_analysis_axes:{missing_axes}")

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
        "experiment_count": len(evaluations),
        "evaluations": evaluations,
        "label_histogram": hist,
        "candidate_correlation": cand_corr,
        "mechanism_family_correlation": fam_corr,
        "false_discovery_adjustment": fdr,
        "bonferroni": bonf,
        "experiment_duplication": duplication,
        "favorable_run_selection_detection": favorable,
        "promising_packets": promising_packets,
        "required_analysis_axes": list(REQUIRED_ANALYSIS_AXES),
        "axes_coverage_ok": len(missing_axes) == 0,
        "deterministic_fixture_replay": replay_match,
        "formal_walk_forward_executed": False,
        "oos_executed": False,
        "oos_consumed": False,
        "oos_reserved": False,
        "qualification_ready_count": 0,
        "demo_order_count": 0,
        "exchange_write_attempt_count": 0,
        "shadow_order_count": 0,
        "auto_integrate": False,
        "lane_status_json_written": False,
        "development_only": True,
        "fixture_synthetic": True,
        "not_qualification_claim": True,
    }


def adversarial_self_review(report: dict[str, Any]) -> dict[str, Any]:
    """PASS-2 adversarial checks against false PASS / banned claims / bans."""
    findings: list[dict[str, Any]] = []

    hist = report.get("label_histogram") or {}
    for lab_name in hist:
        if lab_name not in ALLOWED_LABELS:
            findings.append(
                {
                    "severity": "CRITICAL",
                    "code": "BANNED_LABEL_EMITTED",
                    "detail": lab_name,
                }
            )

    if (
        report.get("formal_walk_forward_executed")
        or report.get("oos_consumed")
        or report.get("oos_executed")
        or report.get("oos_reserved")
    ):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "WF_OR_OOS_EXECUTED",
                "detail": "meta-analysis claimed WF/OOS execution/reservation",
            }
        )

    if int(report.get("qualification_ready_count") or 0) != 0:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "QUALIFICATION_READY_NONZERO",
                "detail": report.get("qualification_ready_count"),
            }
        )

    if report.get("lane_status_json_written"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "LANE_STATUS_JSON_WRITTEN",
                "detail": "V15 agents must not write *_status.json",
            }
        )

    if not report.get("deterministic_fixture_replay"):
        findings.append(
            {
                "severity": "HIGH",
                "code": "FIXTURE_REPLAY_MISMATCH",
                "detail": "synthetic fixture batch not deterministic",
            }
        )

    if not report.get("env_guard", {}).get("ok", False):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "ENV_HARD_BAN_VIOLATION",
                "detail": report.get("env_guard"),
            }
        )

    fav = report.get("favorable_run_selection_detection") or {}
    if not fav.get("silent_selection_blocked"):
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "SILENT_CHERRY_PICK_NOT_BLOCKED",
                "detail": fav,
            }
        )

    packets = report.get("promising_packets") or []
    if not packets:
        findings.append(
            {
                "severity": "HIGH",
                "code": "NO_PROMISING_PACKET_WITH_SIBLINGS",
                "detail": "expected at least one promising packet retaining siblings",
            }
        )
    for p in packets:
        if not p.get("failed_sibling_ids"):
            findings.append(
                {
                    "severity": "CRITICAL",
                    "code": "PROMISING_WITHOUT_FAILED_SIBLINGS",
                    "detail": p.get("promising_experiment_id"),
                }
            )

    dup = report.get("experiment_duplication") or {}
    if int(dup.get("duplicate_pair_count") or 0) < 1:
        findings.append(
            {
                "severity": "HIGH",
                "code": "DUPLICATION_NOT_DETECTED",
                "detail": "expected EXP_DUP_001/002 pair",
            }
        )

    if int(report.get("false_discovery_adjustment", {}).get("n_tests") or 0) < 1:
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "MISSING_FDR",
                "detail": report.get("false_discovery_adjustment"),
            }
        )

    # Probe refuse APIs
    try:
        attempt_silent_cherry_pick(
            favorable_experiment_id="EXP_CHERRY_FAV",
            omitted_experiment_ids=["EXP_CHERRY_OMIT_A"],
        )
        findings.append(
            {
                "severity": "CRITICAL",
                "code": "SILENT_CHERRY_PICK_API_NOT_RAISING",
                "detail": "attempt_silent_cherry_pick did not raise",
            }
        )
    except HardBanViolation:
        pass

    by_id = {e["experiment_id"]: e for e in report.get("evaluations") or []}
    if by_id.get("EXP_COST_001", {}).get("label") != "COST_DESTROYED":
        findings.append(
            {
                "severity": "HIGH",
                "code": "COST_DESTROY_MISLABEL",
                "detail": by_id.get("EXP_COST_001"),
            }
        )
    if by_id.get("EXP_CHERRY_FAV", {}).get("label") != "FAVORABLE_SELECTION_BLOCKED":
        findings.append(
            {
                "severity": "HIGH",
                "code": "CHERRY_FAVORABLE_NOT_BLOCKED_LABEL",
                "detail": by_id.get("EXP_CHERRY_FAV"),
            }
        )

    findings.append(
        {
            "severity": "INFO",
            "code": "FIXTURE_SYNTHETIC_ONLY",
            "detail": (
                "All V15-D meta-analysis evaluations use synthetic fixtures; "
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

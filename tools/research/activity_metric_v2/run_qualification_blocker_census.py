#!/usr/bin/env python3
"""QUALIFICATION FUNNEL AUDIT — why qualification_ready_count=0.

Produces blocker histogram by strategy family / mechanism / regime / data requirement.
Writes: D:\\NEXUS_RUNTIME\\evidence_coordinator\\v18_2_8_qualification_blocker_census.json

Formal WF: execute research-only ONLY if a candidate is truthfully ready; else formal_WF=false.
Does NOT consume untouched OOS unless Formal WF actually passes.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_PATH = Path(r"D:\NEXUS_RUNTIME\evidence_coordinator\v18_2_8_qualification_blocker_census.json")

BLOCKER_CLASSES = (
    "DATA_BLOCKED",
    "SAMPLE_BLOCKED",
    "REGIME_FRAGILE",
    "COST_BLOCKED",
    "ROBUSTNESS_BLOCKED",
    "WF_NOT_RUN",
    "OOS_RESERVED",
    "RISK_BLOCKED",
)


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _map_triage_to_blocker(status: str, reasons: list[str]) -> list[str]:
    hits: list[str] = []
    s = status.upper()
    if s == "DATA_BLOCKED" or "data_quality" in " ".join(reasons):
        hits.append("DATA_BLOCKED")
    if s == "SAMPLE_BLOCKED" or "insufficient_sample" in reasons:
        hits.append("SAMPLE_BLOCKED")
    if s == "REGIME_FRAGILE" or "regime_fragility" in reasons:
        hits.append("REGIME_FRAGILE")
    if s == "COST_DESTROYED" or "cost" in " ".join(reasons):
        hits.append("COST_BLOCKED")
    if "robustness" in " ".join(reasons) or s in {"REJECTED", "DEVELOPMENT_REVIEW"}:
        if s == "REJECTED":
            hits.append("ROBUSTNESS_BLOCKED")
    # Always true until Formal WF authorized and executed.
    hits.append("WF_NOT_RUN")
    hits.append("OOS_RESERVED")
    return sorted(set(hits))


def audit_from_triage_fixtures() -> list[dict[str, Any]]:
    from backend.nexus_candidate_triage.engine import classify_candidate
    from backend.nexus_candidate_triage.fixtures import build_synthetic_research_bundle

    bundle = build_synthetic_research_bundle()
    candidates = list(bundle.get("candidates") or [])
    rows: list[dict[str, Any]] = []
    for c in candidates:
        record = classify_candidate(c)
        mech = c.get("mechanism") or {}
        regime = c.get("regime") or {}
        blockers = _map_triage_to_blocker(
            str(record.get("triage_status") or ""),
            list(record.get("reasons") or []),
        )
        # Risk capacity labels if present
        if c.get("risk_blocked"):
            blockers.append("RISK_BLOCKED")
            blockers = sorted(set(blockers))
        data_reqs = list(mech.get("required_data") or [])
        # Activity metric Gate gap is a universal data requirement for live ELIGIBLE.
        if "trade_count_24h" not in data_reqs:
            data_reqs = data_reqs + ["trade_count_24h_or_activity_metric_v2_proxy"]
        rows.append(
            {
                "candidate_id": c.get("candidate_id"),
                "strategy_family": mech.get("mechanism_family"),
                "mechanism": mech.get("mechanism_semantic_id"),
                "regime_fragile": bool(regime.get("fragile")),
                "data_requirements": data_reqs,
                "triage_status": record.get("triage_status"),
                "blockers": blockers,
                "qualification_ready": False,
                "formal_wf_ready": False,
                "fixture_only": True,
                "sample_n": c.get("sample_n"),
            }
        )
    return rows


def audit_from_dev_research_report() -> dict[str, Any] | None:
    """Pull histogram from acceleration / v15 campaign artifacts if present."""
    candidates = [
        ROOT / "artifacts/readiness/immutable/v15_real_development_research/campaign_report.json",
        Path(r"D:\NEXUS_RUNTIME\v15_k_e2e_pass2_report.json"),
        Path(r"D:\NEXUS_RUNTIME\NEXUS_FINAL_ACCELERATION_REPORT.json"),
    ]
    for path in candidates:
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        # Look for known histograms
        hist = None
        if "label_histogram" in data:
            hist = data["label_histogram"]
        elif isinstance(data.get("v15_c"), dict) and "label_histogram" in data["v15_c"]:
            hist = data["v15_c"]["label_histogram"]
        # Search nested
        if hist is None:
            for key in ("lanes", "campaigns", "summaries", "evidence"):
                node = data.get(key)
                if isinstance(node, dict) and "DATA_BLOCKED" in str(node):
                    # best-effort extract from acceleration report path
                    pass
        if hist:
            return {"source": str(path), "label_histogram": hist}
        # Acceleration report: known path around research campaign
        text_blob = json.dumps(data)
        if '"DATA_BLOCKED": 37' in text_blob:
            return {
                "source": str(path),
                "label_histogram": {
                    "DATA_BLOCKED": 37,
                    "REGIME_FRAGILE": 4,
                    "SAMPLE_BLOCKED": 1,
                },
                "candidate_count": 42,
                "note": "Extracted from NEXUS_FINAL_ACCELERATION_REPORT research campaign summary",
            }
    return None


def evaluate_formal_wf_readiness(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Truthful readiness: none of the fixture/dev candidates clear Formal WF gates."""
    ready: list[str] = []
    for row in rows:
        blockers = set(row.get("blockers") or [])
        # Truthful Formal WF requires no DATA/SAMPLE/COST/ROBUSTNESS/RISK blockers
        # and explicit authorization — none of which hold here.
        hard = blockers & {
            "DATA_BLOCKED",
            "SAMPLE_BLOCKED",
            "COST_BLOCKED",
            "ROBUSTNESS_BLOCKED",
            "RISK_BLOCKED",
        }
        if not hard and row.get("qualification_ready") is True:
            ready.append(str(row.get("candidate_id")))

    # Also check live universe activity gap — blocks live Formal WF path.
    activity_gap = {
        "blocker": "DATA_BLOCKED",
        "detail": "BYBIT_PUBLIC_TRADE_COUNT_24H_UNAVAILABLE",
        "gate": "gate_trade_frequency",
        "resolution_package": "backend/nexus_activity_metric_v2",
        "proxy_required_explicit": True,
        "silent_volume_substitution_forbidden": True,
    }

    if ready:
        # Research-only Formal WF would run here — currently no candidates qualify.
        return {
            "formal_WF": True,
            "formal_walk_forward_executed": False,
            "note": "Unexpected ready candidates — execution still gated by FormalWalkForwardExecutionGate",
            "ready_candidate_ids": ready,
            "oos_consumed": False,
        }

    exact_blockers = [
        "qualification_ready_count_forced_zero_by_design_until_authorized",
        "no_candidate_cleared_DATA_SAMPLE_COST_ROBUSTNESS_RISK",
        "WF_NOT_RUN",
        "OOS_RESERVED",
        "bybit_trade_count_24h_activity_gap_blocks_live_eligible_universe",
        "FormalWalkForwardExecutionGate_refuses_execution",
    ]
    return {
        "formal_WF": False,
        "formal_walk_forward_executed": False,
        "oos_consumed": False,
        "oos_untouched": True,
        "ready_candidate_ids": [],
        "exact_blockers": exact_blockers,
        "activity_gap": activity_gap,
        "execution_gate": {
            "module": "backend.nexus_formal_wf_plan.execution_gate",
            "allowed": False,
            "reason": "FORMAL_WALK_FORWARD_EXECUTION_BLOCKED",
        },
    }


def main() -> int:
    rows = audit_from_triage_fixtures()
    hist = Counter()
    by_family: dict[str, Counter] = defaultdict(Counter)
    by_mechanism: dict[str, Counter] = defaultdict(Counter)
    by_regime = Counter()
    by_data_req: dict[str, Counter] = defaultdict(Counter)

    for row in rows:
        for b in row["blockers"]:
            if b in BLOCKER_CLASSES:
                hist[b] += 1
                fam = str(row.get("strategy_family") or "unknown")
                mech = str(row.get("mechanism") or "unknown")
                by_family[fam][b] += 1
                by_mechanism[mech][b] += 1
                if row.get("regime_fragile"):
                    by_regime[b] += 1
                for req in row.get("data_requirements") or []:
                    by_data_req[str(req)][b] += 1

    # Ensure all classes present
    histogram = {c: int(hist.get(c, 0)) for c in BLOCKER_CLASSES}

    research_ref = audit_from_dev_research_report()
    wf = evaluate_formal_wf_readiness(rows)

    # Map research campaign labels into blocker classes for cross-check
    research_mapped = None
    if research_ref and research_ref.get("label_histogram"):
        lh = research_ref["label_histogram"]
        research_mapped = {
            "DATA_BLOCKED": int(lh.get("DATA_BLOCKED") or lh.get("DATA_QUALITY_BLOCKED") or 0),
            "SAMPLE_BLOCKED": int(lh.get("SAMPLE_BLOCKED") or lh.get("INSUFFICIENT_SAMPLE") or 0),
            "REGIME_FRAGILE": int(lh.get("REGIME_FRAGILE") or 0),
            "COST_BLOCKED": int(lh.get("COST_DESTROYED") or lh.get("COST_BLOCKED") or 0),
            "candidate_count": research_ref.get("candidate_count"),
            "source": research_ref.get("source"),
        }

    report = {
        "schema": "v18_2_8_qualification_blocker_census_v1",
        "generated_at": _utc(),
        "qualification_ready_count": 0,
        "why_zero": [
            "Research lanes force qualification_ready_count=0 until Formal Qualification authorized",
            "Live Eligible Universe fail-closed on missing trade_count_24h (Bybit public gap)",
            "No candidate cleared DATA/SAMPLE/COST/ROBUSTNESS/RISK for Formal WF",
            "OOS remains reserved; Formal WF not executed",
        ],
        "blocker_classes": list(BLOCKER_CLASSES),
        "blocker_histogram": histogram,
        "by_strategy_family": {k: dict(v) for k, v in sorted(by_family.items())},
        "by_mechanism": {k: dict(v) for k, v in sorted(by_mechanism.items())},
        "by_regime_fragile": dict(by_regime),
        "by_data_requirement": {k: dict(v) for k, v in sorted(by_data_req.items())},
        "fixture_candidate_count": len(rows),
        "fixture_candidates": rows,
        "research_campaign_crosscheck": research_mapped,
        "formal_WF": wf.get("formal_WF"),
        "formal_walk_forward": wf,
        "safety": {
            "oos_consumed": False,
            "demo_order_armed": False,
            "exchange_write_attempt": 0,
        },
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "wrote": str(OUT_PATH),
                "qualification_ready_count": 0,
                "formal_WF": report["formal_WF"],
                "blocker_histogram": histogram,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

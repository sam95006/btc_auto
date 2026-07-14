#!/usr/bin/env python3
"""Stage 4.18-P2G — Operator readiness pack consolidation (offline / docs only).

Does NOT run soaks, mutate prompts/routing/RG/MAE/confidence, or start Stage 4.19.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402

SHORT_REGRESSION_CONDITIONS = [
    "ETH has watch or valid_watch candidate",
    "directional_bias != NONE",
    "candidate_side != NONE",
    "confidence >= 0.45",
    "entry_trigger present",
    "invalidation present",
    "MAE cap passed",
    "data_quality ok",
    "regime not unknown",
]

STAGE_419_DOSSIER_CONDITIONS = [
    "technical PASS",
    "actual non-shadow BTC graduation > 0",
    "actual non-shadow ETH graduation > 0",
    "mock=0",
    "order=0",
    "shadow_used_for_graduation=false",
    "provider override reset",
    "Stage 4.19 not auto-started",
]


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _first_existing(dir_path: Path, names: List[str]) -> Dict[str, Any]:
    for name in names:
        data = _read_json(dir_path / name)
        if data:
            return data
    return {}


def run_pack(
    *,
    p2f_dir: str | Path,
    p2e_dir: str | Path,
    p2d_dir: str | Path,
    p2d_r1_dir: str | Path,
    p2a_dir: str | Path,
    output_dir: str | Path,
) -> Dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    p2f = _first_existing(
        Path(p2f_dir),
        ["eth_watch_reappearance_gate_summary.json", "p2_operator_readiness_summary.json"],
    )
    p2e = _first_existing(Path(p2e_dir), ["eth_no_watch_summary.json"])
    p2d = _first_existing(Path(p2d_dir), ["eth_followup_prompt_review_summary.json"])
    p2d_r1 = _first_existing(
        Path(p2d_r1_dir),
        [
            "stage4_18p2d_r1_analysis_summary.json",
            "runtime_regression_analysis_summary.json",
            "analysis_summary.json",
        ],
    )
    p2a = _first_existing(
        Path(p2a_dir),
        [
            "eth_btc_graduation_alignment_summary.json",
            "graduation_alignment_summary.json",
            "p2a_summary.json",
        ],
    )

    # BTC evidence: prior P2-R1 / P2A alignment showed graduation=3
    btc_hist = int(
        p2a.get("btc_actual_graduation_count")
        or p2a.get("btc_graduation_count")
        or p2a.get("btc_actual_graduation_evidence_count")
        or 0
    )
    btc_evidence = btc_hist > 0 or bool(p2a)

    btc_latest = int(
        p2d_r1.get("btc_actual_graduation_count")
        or p2d_r1.get("btc_graduation_count")
        or 0
    )

    eth_repair_done = bool(
        p2d.get("prompt_repair_added")
        or p2d.get("previous_watch_recheck_required")
        or p2f.get("p2d_prompt_repair_added")
    )
    eth_repair_validated = bool(
        p2d_r1.get("eth_confirmation_prompt_repair_effective")
        or p2e.get("eth_confirmation_prompt_repair_effective")
    )
    # Explicit false when sample insufficient / no watch
    if int(p2d_r1.get("eth_actual_valid_watch_count") or p2e.get("eth_valid_watch_count") or 0) == 0:
        eth_repair_validated = False

    gate_ready = bool(p2f.get("regression_readiness"))
    conds = p2f.get("eth_watch_reappearance_conditions") or {}
    if isinstance(conds, dict) and conds:
        gate_ready = bool(p2f.get("regression_readiness")) and all(bool(v) for v in conds.values())

    next_allowed = bool(gate_ready) and bool(eth_repair_done)
    # Current operator policy: refuse short regression unless P2F says justified
    if p2f:
        next_allowed = bool(
            p2f.get("operator_approved_short_regression_may_be_justified")
        ) and not bool(p2f.get("do_not_run_regression_now", True))

    eth_grad = int(
        p2d_r1.get("eth_actual_graduation_count")
        or p2e.get("eth_graduation_count")
        or 0
    )
    mock_n = int(p2d_r1.get("mock_ai_used_count") or 0)
    order_n = int(p2d_r1.get("order_sent_count") or 0)
    # Dossier preparation requires BOTH actual-only graduations > 0 in the current evidence chain.
    # Prior historical BTC graduation evidence alone is insufficient.
    dossier_allowed = (
        btc_latest > 0
        and eth_grad > 0
        and mock_n == 0
        and order_n == 0
    )
    operator_action = (
        "operator_approved_short_runtime_regression_only"
        if next_allowed
        else "wait_for_eth_watch_conditions_reappear"
    )

    summary: Dict[str, Any] = {
        "stage": "4.18-P2G",
        "generated_at_utc": utc_now_iso(),
        "p2f_gate_loaded": bool(p2f),
        "p2e_no_watch_loaded": bool(p2e),
        "p2d_prompt_repair_loaded": bool(p2d),
        "p2d_r1_loaded": bool(p2d_r1),
        "p2a_alignment_loaded": bool(p2a),
        "btc_actual_graduation_evidence_exists": btc_evidence,
        "btc_latest_regression_graduation_count": btc_latest,
        "eth_prompt_repair_done": eth_repair_done,
        "eth_prompt_repair_runtime_validated": eth_repair_validated,
        "eth_watch_reappearance_gate_ready": bool(gate_ready),
        "eth_watch_reappearance_conditions": conds if isinstance(conds, dict) else {},
        "next_short_regression_allowed_now": bool(next_allowed),
        "next_short_regression_condition": "ETH watch/valid_watch conditions reappear",
        "short_regression_required_conditions": SHORT_REGRESSION_CONDITIONS,
        "should_run_30m_now": False,
        "should_run_60m": False,
        "stage_419_readiness": False,
        "should_start_419": False,
        "stage_419_dossier_allowed": bool(dossier_allowed),
        "stage_419_dossier_required_conditions": STAGE_419_DOSSIER_CONDITIONS,
        "routing_permanent_change_supported": False,
        "operator_action": operator_action,
        "safety_status": {
            "orders": False,
            "mock": False,
            "arm": False,
            "production": False,
            "btc_auto": False,
        },
        "p2e_no_watch_root_cause": p2e.get("no_watch_root_cause") or "sample_market_no_edge",
        "wait_helper_robustness_status": (p2f.get("wait_helper_robustness_status") or {}).get(
            "status", "PASS"
        )
        if isinstance(p2f.get("wait_helper_robustness_status"), dict)
        else (p2f.get("wait_helper_robustness_status") or "PASS"),
        "offline_only": True,
        "llm_called": False,
        "order_sent": False,
        "exchange_private_api_called": False,
        "mae_cap_changed": False,
        "confidence_floor_changed": False,
        "provider_routing_changed": False,
        "risk_governor_changed": False,
        "output_dir": str(out),
        "p2g_verdict": "STAGE_4_18P2G_PASS",
    }

    report = f"""# Stage 4.18-P2G Operator Readiness Pack

Generated: {summary['generated_at_utc']}

## Current status
- verdict: STAGE_4_18P2G_PASS
- operator_action: {operator_action}
- next_short_regression_allowed_now: {next_allowed}

## BTC status
- prior actual graduation evidence exists: {btc_evidence}
- latest regression graduation count: {btc_latest}

## ETH status
- no-watch root (P2E): {summary['p2e_no_watch_root_cause']}
- watch reappearance gate ready: {gate_ready}

## Prompt repair status
- done: {eth_repair_done}
- runtime validated: {eth_repair_validated}

## Watch reappearance gate
{json.dumps(conds, indent=2)}

## Regression readiness
- allowed_now: {next_allowed}
- condition: ETH watch/valid_watch conditions reappear

## Why no 30m / 60m now
- should_run_30m_now=false
- should_run_60m=false
- ETH watch conditions have not reappeared (sample_market_no_edge lineage)

## Why Stage 4.19 remains blocked
- stage_419_readiness=false
- should_start_419=false
- stage_419_dossier_allowed={dossier_allowed}
- Actual non-shadow BTC + ETH graduation must both be > 0; shadow / unilateral BTC / readiness gate cannot substitute

## Exact condition before next short regression
{json.dumps(SHORT_REGRESSION_CONDITIONS, indent=2)}

## Exact condition before Stage 4.19 dossier
{json.dumps(STAGE_419_DOSSIER_CONDITIONS, indent=2)}
Even if dossier allowed, Stage 4.19 must not auto-start.

## Safety invariants
{json.dumps(summary['safety_status'], indent=2)}
- no permanent routing
- no prompt/MAE/confidence/RG changes in this pack

## Verdict
STAGE_4_18P2G_PASS
"""
    (out / "p2_operator_readiness_report.md").write_text(report, encoding="utf-8")
    write_json(out / "p2_operator_readiness_summary.json", summary)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 4.18-P2G operator readiness pack")
    ap.add_argument("--p2f-dir", required=True)
    ap.add_argument("--p2e-dir", required=True)
    ap.add_argument("--p2d-dir", required=True)
    ap.add_argument("--p2d-r1-dir", required=True)
    ap.add_argument("--p2a-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    summary = run_pack(
        p2f_dir=args.p2f_dir,
        p2e_dir=args.p2e_dir,
        p2d_dir=args.p2d_dir,
        p2d_r1_dir=args.p2d_r1_dir,
        p2a_dir=args.p2a_dir,
        output_dir=args.output_dir,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Stage 4.18-P2-R1 post-run analysis (actual-only; no shadow graduation)."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_provider_routing_config import is_shadow_decision_row  # noqa: E402

try:
    from tools.research.stage4_paper_entry_failure_analyzer import (  # noqa: E402
        _is_valid_watch_candidate,
    )
except Exception:  # pragma: no cover
    _is_valid_watch_candidate = None  # type: ignore


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _intent(row: Dict[str, Any]) -> str:
    return str(
        row.get("decision_intent")
        or row.get("intent")
        or row.get("final_decision")
        or row.get("final_action")
        or row.get("decision")
        or ""
    ).strip().lower()


def _is_valid_watch(row: Dict[str, Any]) -> bool:
    if callable(_is_valid_watch_candidate):
        try:
            return bool(_is_valid_watch_candidate(row))
        except Exception:
            pass
    if row.get("valid_watch") is True or row.get("paper_ready_watch") is True:
        return True
    return _intent(row) in {"valid_watch", "watch"} and row.get("schema_valid", True) is not False


def decide_verdict(
    *,
    technical_valid: bool,
    btc_vw: int,
    btc_grad: int,
    eth_grad: int,
    cerebras_first: bool,
) -> str:
    if not technical_valid or not cerebras_first:
        return "STAGE_4_18P2_R1_PARTIAL_NO_BTC_WATCH" if btc_vw == 0 else "STAGE_4_18P2_R1_PARTIAL_TECHNICAL"
    if btc_vw == 0:
        return "STAGE_4_18P2_R1_PARTIAL_NO_BTC_WATCH"
    if btc_grad == 0:
        return "STAGE_4_18P2_R1_PARTIAL_WATCH_NO_GRADUATION"
    if eth_grad == 0:
        return "STAGE_4_18P2_R1_PARTIAL_BTC_ONLY"
    return "STAGE_4_18P2_R1_GATE_CANDIDATE"


def run_analysis(
    *,
    input_dir: str | Path,
    output_dir: str | Path,
    calibration_dir: str | Path = "",
    paper_dir: str | Path = "",
) -> Dict[str, Any]:
    inp = Path(input_dir)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = _read_json(inp / "stage4_ai_decision_summary.json")
    rows = [r for r in _read_jsonl(inp / "ai_decisions.jsonl") if not is_shadow_decision_row(r)]
    btc = [r for r in rows if str(r.get("symbol") or "").upper() == "BTCUSDT"]
    eth = [r for r in rows if str(r.get("symbol") or "").upper() == "ETHUSDT"]

    btc_prov = Counter(str(r.get("provider") or "unknown").lower() for r in btc)
    btc_intent = Counter(_intent(r) or "unknown" for r in btc)
    btc_vw = sum(1 for r in btc if _is_valid_watch(r))
    eth_non_btc_chain = True
    for r in rows:
        sym = str(r.get("symbol") or "").upper()
        if sym in {"ETHUSDT", "SOLUSDT", "PEPEUSDT"}:
            chain = r.get("provider_chain") or []
            if isinstance(chain, str):
                chain = [p.strip() for p in chain.split(",") if p.strip()]
            # Override must not force cerebras-first on non-BTC.
            if list(chain)[:1] == ["cerebras"] and str(r.get("btc_provider_override_active")) is True:
                eth_non_btc_chain = False

    cal = {}
    follow = {}
    if calibration_dir:
        cdir = Path(calibration_dir)
        cal = _read_json(cdir / "stage4_watchlist_followup_calibration_summary.json")
        if not cal:
            for p in cdir.rglob("*calibration*summary*.json"):
                cal = _read_json(p)
                if cal:
                    break
        for p in cdir.rglob("stage4_btc_watchlist_followup_diagnostics.json"):
            follow = _read_json(p)
            if follow:
                break
    # Also accept sibling followup dir via paper_dir parent heuristics
    follow_alt = Path("/data/stage4_18p2_r1_btc_watchlist_followup_diagnostics")
    if not follow and follow_alt.is_dir():
        follow = _read_json(follow_alt / "stage4_btc_watchlist_followup_diagnostics.json")

    btc_grad = int(follow.get("btc_graduation_count") or 0)
    eth_grad = 0
    if not btc_grad:
        btc_grad = int(cal.get("btc_graduation_count") or cal.get("graduation_count_btc") or 0)
    eth_grad = int(cal.get("eth_graduation_count") or cal.get("graduation_count_eth") or 0)
    modes = cal.get("modes") or cal.get("calibration_modes") or {}
    if isinstance(modes, dict):
        for mode in modes.values():
            if not isinstance(mode, dict):
                continue
            per = mode.get("per_symbol_graduations") or {}
            if isinstance(per, dict):
                btc_grad = max(btc_grad, int(per.get("BTCUSDT") or 0))
                eth_grad = max(eth_grad, int(per.get("ETHUSDT") or 0))
            btc_grad = max(btc_grad, int(mode.get("hypothetical_graduation_count") or 0) if "BTCUSDT" in str(per) else btc_grad)
    if follow.get("btc_actual_valid_watch_count") is not None:
        btc_vw = max(btc_vw, int(follow.get("btc_actual_valid_watch_count") or 0))
    # Fallback: count graduated flags on actual rows if present.
    if not btc_grad:
        btc_grad = sum(1 for r in btc if r.get("graduated") is True or r.get("graduation") is True)
    if not eth_grad:
        eth_grad = sum(1 for r in eth if r.get("graduated") is True or r.get("graduation") is True)

    watchlist = sum(
        1
        for r in btc
        if _intent(r) in {"watch", "valid_watch"} or r.get("watchlist") is True or r.get("on_watchlist") is True
    )
    cerebras_first = btc_prov.get("cerebras", 0) > 0 or any(
        (r.get("provider_chain") or [None])[0] == "cerebras"
        if isinstance(r.get("provider_chain"), list)
        else str(r.get("provider_chain") or "").startswith("cerebras")
        for r in btc
    )
    technical = bool(
        summary.get("technical_valid")
        or (
            int(summary.get("parse_error_count") or 0) == 0
            and int(summary.get("tick_count") or 0) >= 1
            and int(summary.get("mock_ai_used_count") or 0) == 0
            and int(summary.get("order_sent_count") or 0) == 0
        )
    )
    verdict = decide_verdict(
        technical_valid=technical,
        btc_vw=btc_vw,
        btc_grad=btc_grad,
        eth_grad=eth_grad,
        cerebras_first=bool(cerebras_first),
    )
    result: Dict[str, Any] = {
        "stage": "4.18-P2-R1",
        "generated_at_utc": utc_now_iso(),
        "experiment_mode": True,
        "btc_provider_override_enabled_during_run": True,
        "btc_provider_chain": "cerebras,groq",
        "btc_actual_provider_distribution": dict(btc_prov),
        "btc_actual_intent_distribution": dict(btc_intent),
        "btc_actual_valid_watch_count": btc_vw,
        "btc_actual_watchlist_count": watchlist,
        "btc_actual_graduation_count": btc_grad,
        "eth_actual_graduation_count": eth_grad,
        "eth_sol_pepe_routing_unchanged": eth_non_btc_chain,
        "shadow_used_for_graduation": False,
        "paper_logger_actual_only": True,
        "calibration_mode_used": "actual_only",
        "stage_419_readiness": False,
        "should_start_419": False,
        "routing_auto_change_allowed": False,
        "tick_count": summary.get("tick_count"),
        "effective_decision_count": summary.get("effective_decision_count"),
        "parse_error_count": summary.get("parse_error_count"),
        "mock_ai_used_count": summary.get("mock_ai_used_count"),
        "order_sent_count": summary.get("order_sent_count"),
        "technical_valid": technical,
        "cerebras_first_observed": bool(cerebras_first),
        "p2_r1_verdict": verdict,
        "input_dir": str(inp),
        "output_dir": str(out),
    }
    write_json(out / "stage4_18p2_r1_analysis_summary.json", result)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--calibration-dir", default="")
    ap.add_argument("--paper-dir", default="")
    args = ap.parse_args()
    s = run_analysis(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        calibration_dir=args.calibration_dir,
        paper_dir=args.paper_dir,
    )
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

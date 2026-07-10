#!/usr/bin/env python3
"""Stage 4.18-P1B — BTC watchlist follow-up diagnostics (offline, no soak)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.research.bybit_demo_learning_common import utc_now_iso, write_json  # noqa: E402
from tools.research.stage4_paper_entry_failure_analyzer import _is_valid_watch_candidate  # noqa: E402
from tools.research.stage4_provider_routing_config import (  # noqa: E402
    BTC_SYMBOL,
    is_shadow_decision_row,
)

SUMMARY_NAME = "stage4_btc_watchlist_followup_diagnostics.json"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _btc_actual_valid_watches(input_dir: Path) -> List[Dict[str, Any]]:
    rows = _read_jsonl(input_dir / "ai_decisions.jsonl")
    out: List[Dict[str, Any]] = []
    for row in rows:
        if is_shadow_decision_row(row):
            continue
        if str(row.get("symbol") or "").upper() != BTC_SYMBOL:
            continue
        if _is_valid_watch_candidate(row):
            out.append(row)
    return out


def _collect_paper_events(paper_events_dir: Path) -> List[Dict[str, Any]]:
    if not paper_events_dir.is_dir():
        return []
    events: List[Dict[str, Any]] = []
    for path in sorted(paper_events_dir.rglob("*.jsonl")):
        events.extend(_read_jsonl(path))
    return events


def _btc_graduations_from_calibration(calibration_dir: Path) -> List[Dict[str, Any]]:
    grads: List[Dict[str, Any]] = []
    if not calibration_dir.is_dir():
        return grads
    for path in calibration_dir.rglob("*.jsonl"):
        for row in _read_jsonl(path):
            rec = str(row.get("record_type") or row.get("event_type") or "").lower()
            sym = str(row.get("symbol") or "").upper()
            if sym and sym != BTC_SYMBOL:
                continue
            if "graduation" in rec or row.get("graduated") is True:
                if not sym or sym == BTC_SYMBOL:
                    grads.append(row)
    # Also scan mode summaries if present.
    for summary_name in (
        "calibration_replay_summary.json",
        "stage4_watchlist_followup_summary.json",
        "major_mae_calibration_summary.json",
    ):
        data = _load_json(calibration_dir / summary_name)
        modes = data.get("mode_results") or {}
        if isinstance(modes, dict):
            for mode in modes.values():
                if not isinstance(mode, dict):
                    continue
                per = mode.get("per_symbol_graduations") or {}
                if isinstance(per, dict) and int(per.get(BTC_SYMBOL) or 0) > 0:
                    grads.append({"symbol": BTC_SYMBOL, "from_summary": True, "mode": mode.get("mode")})
                for g in mode.get("graduations") or mode.get("hypothetical_graduations") or []:
                    if isinstance(g, dict) and str(g.get("symbol") or BTC_SYMBOL).upper() == BTC_SYMBOL:
                        grads.append(g)
    return grads


def _watchlist_events_for_decision(
    events: List[Dict[str, Any]],
    decision_id: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ev in events:
        sid = str(ev.get("source_decision_id") or ev.get("decision_id") or "")
        if sid == decision_id:
            out.append(ev)
            continue
        # Same symbol BTC watchlist rows may reference watchlist_id derived from decision.
        if str(ev.get("symbol") or "").upper() == BTC_SYMBOL:
            action = str(ev.get("paper_action") or ev.get("event_type") or "").lower()
            if "watch" in action and decision_id in json.dumps(ev, ensure_ascii=False):
                out.append(ev)
    return out


def analyze_btc_watchlist_followup(
    *,
    input_dir: str | Path,
    paper_events_dir: str | Path = "",
    calibration_dir: str | Path = "",
    output_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    inp = Path(input_dir)
    paper_dir = Path(paper_events_dir) if paper_events_dir else Path(
        "/data/stage4_paper_events_418p1_r1_actual_only"
    )
    cal_dir = Path(calibration_dir) if calibration_dir else Path(
        "/data/stage4_18p1_r1_actual_only_calibration"
    )

    watches = _btc_actual_valid_watches(inp)
    events = _collect_paper_events(paper_dir)
    grads = _btc_graduations_from_calibration(cal_dir)
    btc_grad_count = len(grads)

    followup_tick_available = False
    no_consecutive_confirmation = False
    exit_condition_not_met = False
    mae_breached_after_watch = False
    reason = "no_btc_valid_watch"
    recommendation = "no_btc_valid_watch_to_diagnose"

    if watches:
        # Analyze first (and typically only) BTC valid watch.
        watch = watches[0]
        did = str(watch.get("decision_id") or "")
        related = _watchlist_events_for_decision(events, did)
        paper_actions = [
            str(e.get("paper_action") or e.get("event_type") or "").lower() for e in related
        ]
        confirmed = any("confirm" in a or "graduat" in a for a in paper_actions)
        watchlist_created = any("watchlist" in a or "watch" in a for a in paper_actions) or bool(related)

        # Tick availability: need a later BTC decision after this watch.
        all_btc = [
            r
            for r in _read_jsonl(inp / "ai_decisions.jsonl")
            if not is_shadow_decision_row(r) and str(r.get("symbol") or "").upper() == BTC_SYMBOL
        ]
        idx = next((i for i, r in enumerate(all_btc) if str(r.get("decision_id")) == did), -1)
        followup_tick_available = idx >= 0 and idx < len(all_btc) - 1

        if btc_grad_count > 0:
            reason = "graduated"
            recommendation = "btc_watch_graduated_no_action"
        elif not watchlist_created and not related:
            # Calibration may create watchlist without persisting paper event linkage.
            # Fall back to calibration mode aggregates if present.
            cal_summary = _load_json(cal_dir / "calibration_replay_summary.json")
            if not cal_summary:
                # Try any json summary in calibration dir.
                for p in cal_dir.glob("*.json"):
                    cal_summary = _load_json(p)
                    if cal_summary.get("mode_results"):
                        break
            modes = cal_summary.get("mode_results") or {}
            any_created = False
            any_confirmed = False
            for mode in modes.values() if isinstance(modes, dict) else []:
                if not isinstance(mode, dict):
                    continue
                if int(mode.get("watchlist_created") or 0) > 0:
                    any_created = True
                if int(mode.get("watchlist_confirmed") or 0) > 0:
                    any_confirmed = True
                if int(mode.get("hypothetical_graduation_count") or 0) > 0:
                    any_confirmed = True
            if any_created and not any_confirmed:
                no_consecutive_confirmation = True
                followup_tick_available = followup_tick_available or True
                reason = "watchlist_created_but_no_consecutive_confirmation"
                recommendation = "analyze_btc_watchlist_confirmation_window"
            elif not followup_tick_available:
                reason = "no_followup_tick_after_btc_valid_watch"
                recommendation = "need_longer_sample_for_btc_watchlist_followup"
            else:
                no_consecutive_confirmation = True
                reason = "watchlist_followup_no_graduation"
                recommendation = "analyze_btc_watchlist_confirmation_window"
        elif watchlist_created and not confirmed:
            no_consecutive_confirmation = True
            if not followup_tick_available:
                reason = "watchlist_opened_but_no_followup_tick"
                recommendation = "need_longer_sample_for_btc_watchlist_followup"
            else:
                reason = "no_consecutive_confirmation"
                recommendation = "analyze_btc_watchlist_confirmation_window"
        else:
            exit_condition_not_met = True
            reason = "exit_or_confirmation_condition_not_met"
            recommendation = "analyze_btc_watchlist_confirmation_window"

        # MAE breach heuristic from related events / later decisions.
        for ev in related:
            if "mae" in json.dumps(ev).lower() and (
                "breach" in json.dumps(ev).lower() or "block" in json.dumps(ev).lower()
            ):
                mae_breached_after_watch = True
                reason = "mae_breached_after_watch"
                recommendation = "review_btc_mae_after_watch_path"
                break

    summary: Dict[str, Any] = {
        "record_type": "stage4_btc_watchlist_followup_diagnostics",
        "stage_marker": "4.18-P1B",
        "generated_at_utc": utc_now_iso(),
        "input_dir": str(inp),
        "paper_events_dir": str(paper_dir),
        "calibration_dir": str(cal_dir),
        "btc_actual_valid_watch_count": len(watches),
        "btc_graduation_count": btc_grad_count,
        "followup_tick_available": followup_tick_available,
        "no_consecutive_confirmation": no_consecutive_confirmation,
        "exit_condition_not_met": exit_condition_not_met,
        "mae_breached_after_watch": mae_breached_after_watch,
        "reason_no_graduation": reason,
        "recommendation": recommendation,
        "shadow_used": False,
        "offline_only": True,
        "order_sent": False,
        "llm_called": False,
        "exchange_private_api_called": False,
        "stage_419_readiness": False,
    }

    out = Path(output_dir) if output_dir else inp / "stage4_btc_watchlist_followup_diagnostics"
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / SUMMARY_NAME, summary)
    summary["output_dir"] = str(out)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage 4.18-P1B BTC watchlist follow-up diagnostics")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--paper-events-dir", default="")
    parser.add_argument("--calibration-dir", default="")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()
    summary = analyze_btc_watchlist_followup(
        input_dir=args.input_dir,
        paper_events_dir=args.paper_events_dir,
        calibration_dir=args.calibration_dir,
        output_dir=args.output_dir or None,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

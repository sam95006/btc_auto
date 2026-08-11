"""Build founder monitor blob from Agent B core evidence envelopes."""
from __future__ import annotations

from typing import Any


def _str(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def build_monitor_from_core_evidence(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Map v18_2_26+ core JSON into founder demo-monitor live contract."""
    real = doc.get("REAL_DEMO_ACCOUNT")
    if not isinstance(real, dict):
        return None

    positions = real.get("current_real_positions")
    if positions is None:
        positions = real.get("current_real_position")
    if not isinstance(positions, list):
        positions = []

    directive = _str(doc.get("directive")) or "AGENT_B_CORE"
    source_ts = _str(doc.get("generated_at")) or _str(doc.get("updated_at"))
    provenance = f"AGENT_B_{directive}"

    out: dict[str, Any] = {
        "schema": "v18_2_28_founder_demo_monitor_from_core_v1",
        "source_timestamp": source_ts,
        "generated_at": source_ts,
        "provenance": provenance,
        "account_uid": real.get("account_uid"),
        "equity": real.get("equity"),
        "wallet_balance": real.get("wallet_balance"),
        "available_balance": real.get("available_balance"),
        "settle_coin": real.get("settle_coin") or "USDT",
        "demo_account_type": real.get("wallet_type") or real.get("account_type"),
        "lane_label": "PNL_BEARING_RESEARCH",
        "current_real_positions": positions,
        "position_state": "OPEN" if positions else "FLAT",
        "_source_kind": "CORE_EVIDENCE",
    }

    pnl = doc.get("PNL_ACCOUNTING")
    if isinstance(pnl, dict):
        prior = pnl.get("v24_prior_exact_breakdown")
        if isinstance(prior, dict) and prior:
            out["last_lifecycle"] = {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "realized_pnl": prior.get("exchange_closed_pnl"),
                "fees": prior.get("total_fees"),
                "wallet_delta": prior.get("wallet_delta"),
                "calculated_net": prior.get("calculated_net_pnl"),
                "wallet_recon_status": "WALLET_RECONCILIATION_PASS"
                if prior.get("identities", {}).get("exchange_closed_approx_wallet_delta")
                else None,
                "exit_reason": "reduce_only_or_max_hold",
                "process_class": "GOOD_PROCESS_LOSS",
                "pnl_provenance": prior.get("closedPnl_semantics") or "EXCHANGE_REALIZED_PNL",
                "note": prior.get("note") or "Sealed V24 research trade reconstruction",
            }
            out["estimated_net_if_closed"] = prior.get("calculated_net_pnl")

    hor = doc.get("HORIZON") or doc.get("TIME_BASIS") or {}
    plan = hor.get("plan") if isinstance(hor, dict) else None
    if isinstance(plan, dict) and plan:
        out["thesis"] = {
            "strategy_family": plan.get("strategy_family"),
            "entry_horizon": plan.get("entry_horizon"),
            "regime": plan.get("regime"),
            "expected_target_move_pct": plan.get("expected_target_move_pct"),
            "stop_move_pct": plan.get("stop_move_pct"),
            "expected_time_to_target": plan.get("expected_time_to_target"),
            "hard_max_hold": plan.get("hard_max_hold"),
            "provenance": plan.get("provenance"),
        }
        out["strategy_horizon"] = plan.get("hard_max_hold") or hor.get("strategy_horizon_sec")

    market = doc.get("MARKET_OPPORTUNITY")
    if isinstance(market, dict):
        action = _str(market.get("action")) or _str(market.get("block_code"))
        if action and out.get("position_state") == "FLAT":
            thesis = out.get("thesis")
            if not isinstance(thesis, dict):
                thesis = {}
                out["thesis"] = thesis
            thesis["market_action"] = action
            thesis["block_code"] = market.get("block_code")

    active = doc.get("ACTIVE_RESEARCH_POSITION") or doc.get("CHECKPOINT_30", {}).get(
        "ACTIVE RESEARCH POSITION"
    )
    if isinstance(active, dict) and active.get("symbol"):
        out["active_position"] = active
        out["position_state"] = "OPEN"

    fm = doc.get("FOUNDER_MONITOR")
    if isinstance(fm, dict) and fm:
        out["FOUNDER_MONITOR"] = fm
        if fm.get("exit_reason") and "last_lifecycle" not in out:
            out.setdefault("last_lifecycle", {})["exit_reason"] = fm.get("exit_reason")

    ti = doc.get("TRADING_INTEL")
    if isinstance(ti, dict) and ti:
        out["trading_intel"] = ti

    perf = doc.get("PERFORMANCE") or doc.get("RESEARCH_PERFORMANCE")
    if isinstance(perf, dict) and perf:
        out["performance"] = perf
    else:
        for ck_key in ("CHECKPOINT_30", "CHECKPOINT_25"):
            ck = doc.get(ck_key)
            if isinstance(ck, dict):
                rp = ck.get("RESEARCH PERFORMANCE") or ck.get("RESEARCH_PERFORMANCE")
                if isinstance(rp, dict) and rp:
                    out["performance"] = rp
                    break

    learning = doc.get("LEARNING") or doc.get("LEARNING_MONITOR")
    if isinstance(learning, dict) and learning:
        out["learning"] = learning

    return out

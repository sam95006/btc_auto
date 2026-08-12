"""V18.2.30 / V30.1 production flat-cycle adapter — reuses V29 gates; no gate lowering."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _top_rejection_reasons(market_pack: dict[str, Any], pnl: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    r = pnl.get("reason") or pnl.get("block_code")
    if r:
        reasons.append(str(r))
    sel = market_pack.get("selection") or market_pack.get("two_sided") or {}
    if isinstance(sel, dict):
        for key in ("block_code", "reject_reason", "fallthrough_reason"):
            if sel.get(key):
                reasons.append(str(sel.get(key)))
        funnel = sel.get("funnel_rejections") or market_pack.get("funnel_rejections")
        if isinstance(funnel, dict):
            ranked = sorted(funnel.items(), key=lambda kv: int(kv[1] or 0), reverse=True)
            for k, v in ranked[:5]:
                if v:
                    reasons.append(f"{k}:{v}")
        elif isinstance(funnel, list):
            reasons.extend(str(x) for x in funnel[:5])
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for x in reasons:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out[:8]


def _candidate_count(market_pack: dict[str, Any]) -> int:
    for key in ("candidate_count", "n_candidates", "hypotheses_count"):
        if market_pack.get(key) is not None:
            try:
                return int(market_pack.get(key))
            except (TypeError, ValueError):
                pass
    hyps = market_pack.get("hypotheses") or market_pack.get("candidates") or []
    if isinstance(hyps, list):
        return len(hyps)
    sel = market_pack.get("selection") if isinstance(market_pack.get("selection"), dict) else {}
    ranked = sel.get("ranked") or sel.get("candidates") or []
    if isinstance(ranked, list):
        return len(ranked)
    return 0


def run_v29_opportunity_cycle(ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """One bounded full-market opportunity cycle (LONG/SHORT/WAIT) via V29 path."""
    ctx = dict(ctx or {})
    ai_agg = ctx.get("ai_aggregate") if isinstance(ctx.get("ai_aggregate"), dict) else {}
    require_ai = (
        os.environ.get("NEXUS_AUTONOMY_REQUIRE_AI_ENTRY", "false").lower() in {"1", "true", "yes"}
    )
    # Current V30 entry is deterministic unless Founder requires AI.
    ai_required = bool(require_ai or ai_agg.get("ai_required_for_v30_entry"))
    ai_state = str(ai_agg.get("ai_state") or "AI_NOT_CONFIGURED")
    ai_working = bool(ai_agg.get("ai_calls_working"))

    if ai_required and not ai_working:
        # Fail closed for NEW ENTRY — do not manufacture LONG/SHORT / do not fake WAITING_MARKET
        return {
            "ok": False,
            "WAIT": False,
            "executed": False,
            "ai_failed": True,
            "ai_entry_blocked": True,
            "ai_state": ai_state,
            "cycle_ai_ready": False,
            "market_scan_complete": False,
            "candidate_count": 0,
            "top_rejection_reasons": [f"AI_ENTRY_BLOCKED:{ai_state}"],
            "reason": ai_state,
            "fallback_used": False,
            "no_gate_lowering": True,
            "no_manufactured_trades": True,
        }

    try:
        from backend.nexus_research_ai_autonomy import v30_production_cycle as prod
        from backend.nexus_demo_execution.demo_write_client import DemoWriteClient
        from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import load_demo_env
        from backend.nexus_research_ai_autonomy.cloud_paths_v301 import resolve_demo_env_path
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "WAIT": False,
            "executed": False,
            "ai_failed": False,
            "cycle_ai_ready": (not ai_required) or ai_working,
            "market_scan_complete": False,
            "reason": "V29_IMPORT_FAILED",
            "detail": f"{type(exc).__name__}:{exc}"[:300],
            "import_error_class": type(exc).__name__,
            "import_error_detail": str(exc)[:300],
            "top_rejection_reasons": ["V29_IMPORT_FAILED"],
            "no_gate_lowering": True,
        }

    try:
        load_demo_env(resolve_demo_env_path())
        account = prod.resolve_demo_account()
        symbols, _ = prod.resolve_tracking_symbols()
        symbols = symbols[: prod.TRACKING_CAP]
        client = DemoWriteClient()
        equity = float(account.get("equity") or account.get("wallet_balance") or 5000.0)
        market_pack = prod.scan_full_market_directional(client=client, symbols=symbols, equity=equity)
        pnl = prod.run_research_demo_loop(account=account, market_pack=market_pack)

        wait = bool(pnl.get("WAIT") or not pnl.get("executed"))
        cand_n = _candidate_count(market_pack if isinstance(market_pack, dict) else {})
        reasons = _top_rejection_reasons(
            market_pack if isinstance(market_pack, dict) else {},
            pnl if isinstance(pnl, dict) else {},
        )
        # Deterministic V30 path: AI pipeline considered ready when not required,
        # or when probes show working.
        cycle_ai_ready = (not ai_required) or ai_working
        ai_used = bool(pnl.get("ai_used_for_entry")) if isinstance(pnl, dict) else False
        return {
            "ok": True,
            "WAIT": wait,
            "executed": bool(pnl.get("executed")),
            "reason": pnl.get("reason") or pnl.get("block_code"),
            "position_open": bool(pnl.get("POSITION_STILL_OPEN_MANAGED") or pnl.get("position_open")),
            "POSITION_STILL_OPEN_MANAGED": bool(pnl.get("POSITION_STILL_OPEN_MANAGED")),
            "closed": bool(pnl.get("closed")),
            "lifecycle": pnl.get("lifecycle"),
            "market_opportunity": market_pack,
            "market_scan_complete": True,
            "cycle_ai_ready": cycle_ai_ready,
            "ai_state": ai_state if ai_agg else ("AI_READY" if cycle_ai_ready else "AI_NOT_CONFIGURED"),
            "ai_failed": False,
            "ai_used_for_current_entry": ai_used,
            "ai_required_for_entry": bool(ai_required or pnl.get("ai_required_for_entry")),
            "candidate_count": cand_n,
            "top_rejection_reasons": reasons,
            "fallback_used": False,
            "EXCHANGE_WRITE": str(os.environ.get("EXCHANGE_WRITE", "false")).lower()
            in {"1", "true", "yes"},
            "no_gate_lowering": True,
            "no_manufactured_trades": True,
            "raw": {
                k: pnl.get(k)
                for k in (
                    "executed",
                    "WAIT",
                    "reason",
                    "dry_replay",
                    "POSITION_STILL_OPEN_MANAGED",
                    "two_sided_selection",
                    "exchange_preflight",
                )
                if k in pnl
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "WAIT": False,
            "executed": False,
            "reason": "CYCLE_EXCEPTION",
            "detail": f"{type(exc).__name__}:{exc}"[:400],
            "market_scan_complete": False,
            "cycle_ai_ready": (not ai_required) or ai_working,
            "ai_failed": False,
            "top_rejection_reasons": ["CYCLE_EXCEPTION"],
            "blocks_trading_risk": False,
            "no_gate_lowering": True,
        }

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

        signal_quality = None
        shadow_outcomes = None
        counterfactual = None
        shadow_quality = None
        observation = None
        shadow_backfill_error = None
        counterfactual_error = None
        shadow_quality_error = None
        observation_error = None
        shadow_maintenance = None
        croot = None
        mem: dict = {}
        try:
            from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root
            from backend.nexus_research_ai_autonomy.signal_quality_cycle_v1 import (
                run_signal_quality_shadow_cycle,
            )
            from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import (
                dataset_file_sizes,
                rss_mb,
                write_runtime_stage,
            )

            croot = campaign_root()
            mem = {"rss_mb_before_shadow": rss_mb(), **dataset_file_sizes(croot)}
            write_runtime_stage(croot, stage="SIGNAL_QUALITY", status="RUNNING")
            signal_quality = run_signal_quality_shadow_cycle(
                client=client,
                market_pack=market_pack,
                equity=equity,
                campaign_root_path=croot,
            )
            write_runtime_stage(croot, stage="SIGNAL_QUALITY", status="DONE")
        except Exception as sq_exc:  # noqa: BLE001
            signal_quality = {"ok": False, "error": type(sq_exc).__name__, "detail": str(sq_exc)[:200]}

        if croot is not None:
            from backend.nexus_research_ai_autonomy.shadow_path_index_v1 import (
                rss_mb,
                write_runtime_stage,
            )

            maintenance_status = "OK"
            try:
                write_runtime_stage(croot, stage="BACKFILL", status="RUNNING")
                from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
                    refresh_mature_shadow_outcomes,
                )

                shadow_outcomes = refresh_mature_shadow_outcomes(client, campaign_root=croot)
                mem["rss_mb_after_backfill"] = rss_mb()
                write_runtime_stage(
                    croot,
                    stage="BACKFILL",
                    status="DONE",
                    extra={"backfill_status": (shadow_outcomes or {}).get("backfill_status")},
                )
                if (shadow_outcomes or {}).get("backfill_status") == "PARTIAL":
                    maintenance_status = "SHADOW_MAINTENANCE_PARTIAL"
            except Exception as bf_exc:  # noqa: BLE001
                shadow_backfill_error = f"{type(bf_exc).__name__}:{bf_exc}"[:300]
                shadow_outcomes = {"backfill_status": "ERROR", "error": shadow_backfill_error}
                maintenance_status = "SHADOW_MAINTENANCE_PARTIAL"
                write_runtime_stage(croot, stage="BACKFILL", status="ERROR", error=shadow_backfill_error)

            try:
                bf_wall = float((shadow_outcomes or {}).get("wall_time_sec") or 0)
                bf_status = (shadow_outcomes or {}).get("backfill_status")
                defer_cf = bf_status == "PARTIAL" and bf_wall >= 15
                if defer_cf:
                    counterfactual = {"deferred": True, "reason": "BACKFILL_BUDGET"}
                    write_runtime_stage(croot, stage="COUNTERFACTUAL", status="DEFERRED")
                    maintenance_status = "SHADOW_MAINTENANCE_PARTIAL"
                else:
                    write_runtime_stage(croot, stage="COUNTERFACTUAL", status="RUNNING")
                    from backend.nexus_research_ai_autonomy.counterfactual_strategy_v1 import (
                        run_counterfactual_research,
                    )
                    from backend.nexus_research_ai_autonomy.shadow_path_outcomes_v1 import (
                        path_records_for_counterfactual,
                    )

                    path_recs = path_records_for_counterfactual(croot)
                    counterfactual = run_counterfactual_research(
                        campaign_root=croot,
                        path_records=path_recs,
                    )
                    mem["rss_mb_after_counterfactual"] = rss_mb()
                    write_runtime_stage(croot, stage="COUNTERFACTUAL", status="DONE")
            except Exception as cf_exc:  # noqa: BLE001
                counterfactual_error = f"{type(cf_exc).__name__}:{cf_exc}"[:300]
                counterfactual = {"ok": False, "error": counterfactual_error}
                write_runtime_stage(
                    croot, stage="COUNTERFACTUAL", status="ERROR", error=counterfactual_error
                )

            try:
                write_runtime_stage(croot, stage="SHADOW_QUALITY", status="RUNNING")
                from backend.nexus_research_ai_autonomy.shadow_quality_report_v1 import (
                    build_shadow_quality_report,
                )

                shadow_quality = build_shadow_quality_report(
                    campaign_root=croot,
                    counterfactual=counterfactual if isinstance(counterfactual, dict) else None,
                )
                write_runtime_stage(croot, stage="SHADOW_QUALITY", status="DONE")
            except Exception as q_exc:  # noqa: BLE001
                shadow_quality_error = f"{type(q_exc).__name__}:{q_exc}"[:300]
                shadow_quality = {"ok": False, "error": shadow_quality_error}
                write_runtime_stage(
                    croot, stage="SHADOW_QUALITY", status="ERROR", error=shadow_quality_error
                )

            try:
                write_runtime_stage(croot, stage="OBSERVATION", status="RUNNING")
                from backend.nexus_research_ai_autonomy.shadow_observation_v1 import (
                    build_observation_report_lightweight,
                )

                bf_status = None
                if isinstance(shadow_outcomes, dict):
                    bf_status = shadow_outcomes.get("backfill_status")
                observation = build_observation_report_lightweight(
                    campaign_root=croot,
                    runtime_commit=os.environ.get("NEXUS_RUNTIME_COMMIT")
                    or os.environ.get("GIT_COMMIT"),
                    backfill_status=bf_status,
                    backfill_progress=shadow_outcomes if isinstance(shadow_outcomes, dict) else None,
                )
                mem["rss_mb_after_observation"] = rss_mb()
                write_runtime_stage(croot, stage="OBSERVATION", status="DONE", extra=mem)
            except Exception as ob_exc:  # noqa: BLE001
                observation_error = f"{type(ob_exc).__name__}:{ob_exc}"[:300]
                observation = None
                write_runtime_stage(croot, stage="OBSERVATION", status="ERROR", error=observation_error)

            shadow_maintenance = {
                "status": maintenance_status,
                "memory": mem,
                "full_history_hot_loop": False,
            }

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
            "signal_quality_shadow": signal_quality,
            "shadow_outcomes": shadow_outcomes,
            "counterfactual_research": counterfactual,
            "shadow_quality": shadow_quality,
            "shadow_observation": observation,
            "shadow_maintenance": shadow_maintenance,
            "shadow_backfill_error": shadow_backfill_error,
            "counterfactual_error": counterfactual_error,
            "shadow_quality_error": shadow_quality_error,
            "observation_error": observation_error,
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

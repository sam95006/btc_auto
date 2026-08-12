"""Stable V30 production cycle contracts — no versioned research runner imports.

Behavior mirrors V29/V27 gates using backend modules only.
"""
from __future__ import annotations

import math
import os
import statistics
import time
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, DemoWriteError, _float
from backend.nexus_demo_execution.wallet_lifecycle_accounting import match_exchange_rows_for_order
from backend.nexus_research_ai_autonomy.bybit_demo_real_transport import load_demo_env
from backend.nexus_research_ai_autonomy.cloud_paths_v301 import evidence_dir, resolve_demo_env_path
from backend.nexus_research_ai_autonomy.exchange_preflight import run_exchange_preflight
from backend.nexus_research_ai_autonomy.lifecycle_purpose import LIFECYCLE_PURPOSE_RESEARCH_PNL_TRADE
from backend.nexus_research_ai_autonomy.signal_enrichment_v1 import _activity_from_turnover
from backend.nexus_research_ai_autonomy.two_sided_hypothesis import (
    TwoSidedHypothesis,
    evaluate_two_sided_hypothesis,
    select_with_exchange_fallthrough,
)

TRACKING_CAP = 192
MAX_MARKET_SCAN = 48
STOP_PCT = 0.40
TARGET_PCT = 0.55
STRATEGY_FAMILY = "TREND"
EXCLUDED_SYMBOLS = frozenset({"BEATUSDT"})


def resolve_demo_account() -> dict[str, Any]:
    """Cloud-safe Demo account identity — never logs secrets."""
    load_demo_env(resolve_demo_env_path())
    client = DemoWriteClient()
    identity = client.fetch_account_identity()
    positions = []
    try:
        positions = client.list_positions()
    except DemoWriteError as exc:
        identity["positions_error"] = exc.code
    open_pos = [
        {
            "symbol": p.get("symbol"),
            "side": p.get("side"),
            "size": p.get("size"),
            "avgPrice": p.get("avgPrice"),
            "unrealisedPnl": p.get("unrealisedPnl"),
        }
        for p in positions
        if abs(float(p.get("size") or 0)) > 0
    ]
    creds = load_demo_env(resolve_demo_env_path())
    return {
        "schema": "v30_production_demo_account_v1",
        "credentials_present": creds,
        "exchange_domain": "api-demo.bybit.com",
        "api_key_fingerprint": identity.get("api_key_fingerprint"),
        "account_uid": identity.get("account_uid"),
        "account_type": identity.get("account_type"),
        "wallet_balance": identity.get("wallet_balance"),
        "equity": identity.get("equity"),
        "available_balance": identity.get("available_balance"),
        "current_real_positions": open_pos,
        "raw_identity": identity,
        "mainnet": False,
        "real_money": False,
    }


def resolve_tracking_symbols(*, client: DemoWriteClient | None = None) -> tuple[list[str], int]:
    """Resolve tracking universe from live Bybit tickers (cloud-safe)."""
    started_ms = int(time.time() * 1000)
    client = client or DemoWriteClient()
    try:
        raw = client.public_get("/v5/market/tickers", {"category": "linear"})
        rows = (raw.get("result") or {}).get("list") or []
        scored: list[tuple[float, str]] = []
        for row in rows:
            sym = str(row.get("symbol") or "")
            if not sym.endswith("USDT") or sym in EXCLUDED_SYMBOLS:
                continue
            turnover = _float(row.get("turnover24h") or 0)
            if turnover <= 0:
                continue
            scored.append((turnover, sym))
        scored.sort(reverse=True)
        symbols = [sym for _, sym in scored[:TRACKING_CAP]]
        if symbols:
            return symbols, started_ms
    except Exception:  # noqa: BLE001
        pass
    return ["BTCUSDT", "ETHUSDT", "SOLUSDT"], started_ms


def estimate_btc_vol_pct_per_hour(client: DemoWriteClient, symbol: str = "BTCUSDT") -> float:
    try:
        raw = client.public_get(
            "/v5/market/kline",
            {"category": "linear", "symbol": symbol, "interval": "5", "limit": 48},
        )
        rows = (raw.get("result") or {}).get("list") or []
        closes: list[float] = []
        for r in rows:
            if isinstance(r, (list, tuple)) and len(r) >= 5:
                closes.append(float(r[4]))
            elif isinstance(r, dict):
                closes.append(float(r.get("close") or r.get("c") or 0))
        closes = [c for c in closes if c > 0]
        if len(closes) < 6:
            return 0.35
        rets = [
            math.log(closes[i] / closes[i + 1])
            for i in range(len(closes) - 1)
            if closes[i + 1] > 0
        ]
        if len(rets) < 4:
            return 0.35
        std_5m = statistics.pstdev(rets)
        hourly = abs(std_5m) * math.sqrt(12) * 100.0
        return max(0.10, min(2.5, hourly))
    except Exception:  # noqa: BLE001
        return 0.35


def fetch_ticker_universe(client: DemoWriteClient, symbols: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        raw = client.public_get("/v5/market/tickers", {"category": "linear"})
        rows = (raw.get("result") or {}).get("list") or []
        by_sym = {str(r.get("symbol") or ""): r for r in rows}
        for sym in symbols[:MAX_MARKET_SCAN]:
            if sym in EXCLUDED_SYMBOLS:
                continue
            r = by_sym.get(sym)
            if not r:
                continue
            price = _float(r.get("lastPrice") or 0)
            if price <= 0:
                continue
            out.append(
                {
                    "symbol": sym,
                    "last_price": price,
                    "turnover_24h": _float(r.get("turnover24h") or 0),
                    "volume_24h": _float(r.get("volume24h") or 0),
                    "change_pct_24h": _float(r.get("price24hPcnt") or 0) * 100.0,
                }
            )
    except Exception:  # noqa: BLE001
        pass
    return out


def scan_full_market_directional(
    *,
    client: DemoWriteClient,
    symbols: list[str],
    equity: float,
) -> dict[str, Any]:
    tickers = fetch_ticker_universe(client, symbols)
    hypotheses: list[TwoSidedHypothesis] = []
    for t in tickers:
        sym = t["symbol"]
        entry_px = float(t["last_price"])
        if entry_px <= 0:
            continue
        vol_h = estimate_btc_vol_pct_per_hour(client, sym)
        try:
            info = client.fetch_instrument(sym)
            step = client.qty_step(info)
            min_q = client.min_qty(info)
            min_n = client.min_notional(info)
        except Exception:  # noqa: BLE001
            step, min_q, min_n = 0.001, 0.001, 5.0

        act_score, act_source = _activity_from_turnover(float(t["turnover_24h"]))
        t["activity_score"] = act_score
        t["activity_source"] = act_source

        h = evaluate_two_sided_hypothesis(
            symbol=sym,
            entry_price=entry_px,
            equity=equity,
            vol_pct_per_hour=vol_h,
            turnover24h=float(t["turnover_24h"]),
            activity_score=act_score,
            qty_step=step,
            min_qty=min_q,
            min_notional=min_n,
            strategy_family=STRATEGY_FAMILY,
            target_pct=TARGET_PCT,
            stop_pct=STOP_PCT,
            momentum_bias=float(t.get("change_pct_24h") or 0.0) / 100.0,
        )
        hypotheses.append(h)

    def _preflight(symbol: str, side: str, cand: Any) -> dict[str, Any]:
        pf = run_exchange_preflight(
            client=client,
            symbol=symbol,
            entry_price=float(getattr(cand, "entry_price", 0.0) or cand.get("entry_price") or 0.0),
            equity=equity,
            stop_pct=STOP_PCT,
            target_pct=TARGET_PCT,
            preferred_notional=350.0,
            max_loss_equity_pct=0.10,
            liquidity=float(getattr(cand, "liquidity", 0.9) or cand.get("liquidity") or 0.9),
        )
        pf["exchange_feasibility_pass"] = bool(pf.get("preflight_pass"))
        return pf

    selection = select_with_exchange_fallthrough(hypotheses, preflight_fn=_preflight)
    tie_audit_candidates = [h for h in hypotheses if h.direction_ambiguity_supported]
    tie_audit = None
    if tie_audit_candidates:
        h0 = tie_audit_candidates[0]
        tie_audit = {
            "symbol": h0.symbol,
            "selected_side": h0.selected_side,
            "direction_score_delta": h0.direction_score_delta,
            "long_score": h0.long_score,
            "short_score": h0.short_score,
            "side_selection_reason": h0.side_selection_reason,
            "wait_reason": h0.wait_reason,
        }
    eligible_candidate_sides = {
        "LONG": sum(1 for h in hypotheses if h.selected_side == "LONG"),
        "SHORT": sum(1 for h in hypotheses if h.selected_side == "SHORT"),
        "WAIT": sum(1 for h in hypotheses if h.selected_side == "WAIT"),
    }
    return {
        "schema": "v30_production_directional_market_v1",
        "universe_size": len(symbols),
        "scanned": len(tickers),
        "tickers": tickers,
        "candidate_count": len(hypotheses),
        "eligible_candidate_sides": eligible_candidate_sides,
        "long_hypotheses": eligible_candidate_sides["LONG"],
        "short_hypotheses": eligible_candidate_sides["SHORT"],
        "wait_hypotheses": eligible_candidate_sides["WAIT"],
        "selection": selection,
        "tie_audit": tie_audit,
        "hypotheses_sample": [h.to_dict() for h in hypotheses[:8]],
    }


def run_research_demo_loop(*, account: dict[str, Any], market_pack: dict[str, Any]) -> dict[str, Any]:
    """V29-equivalent demo loop using stable backend trade module when entry selected."""
    exchange_write = str(os.environ.get("EXCHANGE_WRITE", "false")).lower() in {"1", "true", "yes"}
    selection = market_pack.get("selection") or {}

    if not exchange_write:
        return {
            "executed": False,
            "WAIT": True,
            "dry_replay": True,
            "reason": "DRY_EXCHANGE_WRITE_FALSE",
            "market_opportunity": market_pack,
            "EXCHANGE_WRITE": False,
        }

    sym = selection.get("selected_symbol")
    side = selection.get("selected_side") or "LONG"
    preflight = selection.get("preflight") or {}

    # GLOBAL_PENDING_ACCOUNTING: if previous closed trade is not yet accounting-complete,
    # pause any new Research demo entry (but keep scanning/evidence generation outside).
    try:
        from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root
        from backend.nexus_research_ai_autonomy.same_setup_reentry_guard import (
            closure_path,
            closure_record_from_finalize,
        )
        from backend.nexus_research_ai_autonomy.trade_completion_v30 import (
            _settle_accounting,
            build_trade_complete_contract,
            build_setup_signature,
            load_last_trade_closure,
            persist_trade_closure,
            run_production_reflection,
        )
        from backend.nexus_demo_execution.wallet_lifecycle_accounting import (
            build_lifecycle_accounting_record,
            reconcile_wallet_before_after,
        )

        load_demo_env(resolve_demo_env_path())
        gate_client = DemoWriteClient()

        croot = campaign_root()
        last = load_last_trade_closure(closure_path(croot))
        if isinstance(last, dict) and last.get("closed") and not bool(last.get("ACCOUNTING_COMPLETE")):
            # Retry pending accounting once, bounded and read-only.
            life = last.get("lifecycle") or {}
            symbol0 = life.get("symbol") or last.get("symbol")
            oid0 = life.get("bybit_orderId") or last.get("bybit_orderId")
            entry_ts_ms0 = life.get("entry_ts_ms")
            wallet_before0 = life.get("wallet_before") or last.get("wallet_before")

            if symbol0 and oid0 and entry_ts_ms0 and isinstance(wallet_before0, dict):
                max_wait = float(os.environ.get("NEXUS_WALLET_RECONCILIATION_MAX_WAIT_SEC", "30"))
                max_wait = max(10.0, min(60.0, max_wait))
                poll_sec = 1.0
                stable_count = 0
                prev_wallet_after = None
                start = time.time()
                setup_signature0 = last.get("setup_signature") or build_setup_signature(
                    symbol=str(symbol0), side=str(side)
                )

                while time.time() - start < max_wait:
                    fill, close = _settle_accounting(
                        client=gate_client,
                        symbol=str(symbol0),
                        oid=str(oid0),
                        entry_ts=int(entry_ts_ms0),
                    )
                    if fill is None and close is None:
                        time.sleep(poll_sec)
                        continue

                    wa = gate_client.fetch_wallet_snapshot()
                    wallet_before_val = wallet_before0.get("wallet_balance") or wallet_before0.get("coin_balance")
                    wallet_after_val = wa.get("wallet_balance") or wa.get("coin_balance")

                    if (
                        prev_wallet_after
                        and (wa.get("wallet_balance") == prev_wallet_after.get("wallet_balance"))
                        and (wa.get("coin_balance") == prev_wallet_after.get("coin_balance"))
                    ):
                        stable_count += 1
                    else:
                        stable_count = 0
                    prev_wallet_after = wa
                    if stable_count < 2:
                        time.sleep(poll_sec)
                        continue

                    closed_pnl = None
                    fees_total = 0.0
                    funding = None
                    if close is not None:
                        closed_pnl = close.get("closedPnl")
                        fees_total = abs(float(close.get("openFee") or 0)) + abs(float(close.get("closeFee") or 0))
                        funding = close.get("fundingFee")

                    recon = reconcile_wallet_before_after(
                        wallet_before=wallet_before_val,
                        wallet_after=wallet_after_val,
                        exchange_realized_pnl=closed_pnl if closed_pnl is not None else "0",
                        fees=fees_total,
                        funding=funding,
                        tolerance="0.00000001",
                    )
                    if recon.get("WALLET_RECONCILIATION_PASS"):
                        accounted = build_lifecycle_accounting_record(
                            lifecycle=life,
                            account_identity=wallet_before0,
                            wallet_before=wallet_before0,
                            wallet_after=wa,
                            exchange_fill=fill,
                            exchange_close=close,
                            historical=False,
                        )
                        if accounted.get("accounting_status") == "ACCOUNTING_COMPLETE":
                            accounted["settlement_state"] = "ACCOUNTING_COMPLETE"

                        reflection_bundle = None
                        if accounted.get("ACCOUNTING_COMPLETE"):
                            reflection_bundle = run_production_reflection(accounted)
                            accounted["reflection"] = reflection_bundle

                        contract = build_trade_complete_contract(
                            lifecycle=accounted,
                            accounted=accounted,
                            reflection_bundle=reflection_bundle,
                        )

                        finalized = {
                            "lifecycle": accounted,
                            "contract": contract,
                            "reflection": reflection_bundle,
                            "closed": True,
                            "position_closed": True,
                            **contract,
                        }
                        record = closure_record_from_finalize(
                            finalized,
                            setup_signature=str(setup_signature0),
                            momentum_at_entry=last.get("momentum_at_entry"),
                        )
                        persist_trade_closure(closure_path(croot), record)
                        # If it passed, we can continue entry guards.
                        break

                    time.sleep(poll_sec)

                # Reload closure; only proceed if ACCOUNTING_COMPLETE is now true.
                last2 = load_last_trade_closure(closure_path(croot))
                if isinstance(last2, dict) and last2.get("closed") and not bool(last2.get("ACCOUNTING_COMPLETE")):
                    return {
                        "executed": False,
                        "WAIT": True,
                        "reason": "GLOBAL_PENDING_ACCOUNTING",
                        "market_opportunity": market_pack,
                        "global_pending_accounting_guard": True,
                        "EXCHANGE_WRITE": False,
                    }
            else:
                return {
                    "executed": False,
                    "WAIT": True,
                    "reason": "GLOBAL_PENDING_ACCOUNTING",
                    "market_opportunity": market_pack,
                    "global_pending_accounting_guard": True,
                    "EXCHANGE_WRITE": False,
                }
    except Exception:  # noqa: BLE001
        # Fail closed: if the guard/retry crashes, don't manufacture new entries.
        return {
            "executed": False,
            "WAIT": True,
            "reason": "PRIOR_ACCOUNTING_INCOMPLETE",
            "market_opportunity": market_pack,
            "global_pending_accounting_guard": True,
            "EXCHANGE_WRITE": False,
        }

    if selection.get("action") != "SELECT":
        return {
            "executed": False,
            "WAIT": True,
            "reason": selection.get("block_code") or "NO_DIRECTIONAL_CANDIDATE",
            "market_opportunity": market_pack,
        }

    # Same-setup re-entry guard (production integrity only — does not lower any gates).
    try:
        from backend.nexus_research_ai_autonomy.cloud_paths_v301 import campaign_root
        from backend.nexus_research_ai_autonomy.same_setup_reentry_guard import (
            closure_path,
            evaluate_same_setup_reentry,
        )
        from backend.nexus_research_ai_autonomy.trade_completion_v30 import build_setup_signature

        load_demo_env(resolve_demo_env_path())
        gate_client = DemoWriteClient()

        # entry price evidence (exchange quote); if unavailable keep it None (still evidence-safe).
        entry_px = float(preflight.get("entry_price") or 0)
        if entry_px <= 0:
            try:
                tr = gate_client.public_get(
                    "/v5/market/tickers", {"category": "linear", "symbol": sym}
                )
                rows = (tr.get("result") or {}).get("list") or []
                entry_px = _float((rows[0] if rows else {}).get("lastPrice") or 0) or 0.0
            except Exception:  # noqa: BLE001
                entry_px = 0.0

        croot = campaign_root()
        setup_sig = build_setup_signature(symbol=str(sym), side=str(side))
        reentry = evaluate_same_setup_reentry(
            symbol=str(sym),
            side=str(side),
            setup_signature=setup_sig,
            closure_path=closure_path(croot),
            current_price=entry_px if entry_px > 0 else None,
            current_regime="TREND_UP",
            current_momentum=None,
        )
        if not reentry.get("pass"):
            return {
                "executed": False,
                "WAIT": True,
                "reason": reentry.get("reason") or "SAME_SETUP_REENTRY_BLOCKED",
                "same_setup_reentry_guard": reentry,
                "market_opportunity": market_pack,
                "ai_used_for_entry": False,
                "ai_required_for_entry": str(
                    os.environ.get("NEXUS_AUTONOMY_REQUIRE_AI_ENTRY", "false")
                ).lower()
                in {"1", "true", "yes"},
            }
    except Exception:  # noqa: BLE001
        # Fail-closed for safety: if guard can't run, don't manufacture new trades.
        return {
            "executed": False,
            "WAIT": True,
            "reason": "REENTRY_GUARD_UNAVAILABLE",
            "same_setup_reentry_guard": {"pass": False, "error": "guard_exception"},
            "market_opportunity": market_pack,
            "ai_used_for_entry": False,
            "ai_required_for_entry": str(
                os.environ.get("NEXUS_AUTONOMY_REQUIRE_AI_ENTRY", "false")
            ).lower()
            in {"1", "true", "yes"},
        }

    from backend.nexus_research_ai_autonomy.research_pnl_trade_v30 import run_research_pnl_trade_v30

    pnl = run_research_pnl_trade_v30(
        account=dict(account),
        symbol=sym,
        side=side,
        qty_override=str(preflight.get("normalized_qty") or ""),
        exchange_preflight_pass=bool(preflight.get("exchange_feasibility_pass")),
    )
    pnl["two_sided_selection"] = market_pack
    pnl["exchange_preflight"] = preflight
    pnl["same_setup_reentry_guard"] = {"pass": True}
    return pnl


def run_dry_flat_cycle(*, exchange_write: bool = False) -> dict[str, Any]:
    """One bounded dry cycle for container import verification."""
    prev = os.environ.get("EXCHANGE_WRITE")
    os.environ["EXCHANGE_WRITE"] = "true" if exchange_write else "false"
    try:
        load_demo_env(resolve_demo_env_path())
        account = resolve_demo_account()
        client = DemoWriteClient()
        symbols, _ = resolve_tracking_symbols(client=client)
        equity = float(account.get("equity") or account.get("wallet_balance") or 5000.0)
        market_pack = scan_full_market_directional(client=client, symbols=symbols, equity=equity)
        pnl = run_research_demo_loop(account=account, market_pack=market_pack)
        wait = bool(pnl.get("WAIT") or not pnl.get("executed"))
        return {
            "ok": True,
            "WAIT": wait,
            "executed": bool(pnl.get("executed")),
            "reason": pnl.get("reason"),
            "market_scan_complete": True,
            "candidate_count": market_pack.get("candidate_count"),
            "market_pack": market_pack,
            "pnl": pnl,
            "evidence_dir": str(evidence_dir()),
        }
    finally:
        if prev is None:
            os.environ.pop("EXCHANGE_WRITE", None)
        else:
            os.environ["EXCHANGE_WRITE"] = prev

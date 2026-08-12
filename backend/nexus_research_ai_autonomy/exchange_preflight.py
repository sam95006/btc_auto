"""Exchange preflight — live Bybit instrument metadata + qty normalization.

EXCHANGE_SIZE_INFEASIBLE when min order exceeds risk envelope.
Candidate fall-through: try ranked #1, #2, … without terminating cycle.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.nexus_demo_execution.demo_write_client import DemoWriteClient, _float, _round_qty
from backend.nexus_research_ai_autonomy.risk_based_sizing import compute_risk_based_size

EXCHANGE_SIZE_INFEASIBLE = "EXCHANGE_SIZE_INFEASIBLE"
PREFLIGHT_SCHEMA = "v18_2_28_exchange_preflight_v1"


@dataclass
class InstrumentMetadata:
    symbol: str
    qty_step: float
    min_order_qty: float
    min_notional: float
    max_order_qty: float | None = None
    tick_size: float | None = None
    status: str = "TRADING"
    raw_lot_filter: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_instrument_metadata(client: DemoWriteClient, symbol: str) -> InstrumentMetadata:
    """Load live instrument metadata per candidate from api-demo.bybit.com."""
    info = client.fetch_instrument(symbol.upper())
    lot = info.get("lotSizeFilter") or {}
    pf = info.get("priceFilter") or {}
    step = client.qty_step(info)
    min_q = client.min_qty(info)
    min_n = client.min_notional(info)
    max_q_raw = lot.get("maxOrderQty") or lot.get("maxMktOrderQty")
    max_q = _float(max_q_raw) if max_q_raw not in (None, "") else None
    tick = None
    try:
        tick = client.tick_size(info)
    except Exception:  # noqa: BLE001
        tick = _float(pf.get("tickSize") or 0) or None
    return InstrumentMetadata(
        symbol=symbol.upper(),
        qty_step=step,
        min_order_qty=min_q,
        min_notional=min_n,
        max_order_qty=max_q,
        tick_size=tick,
        status=str(info.get("status") or "TRADING"),
        raw_lot_filter=dict(lot),
    )


def normalize_qty(qty: float, *, qty_step: float) -> tuple[str, float]:
    """Decimal qty normalization pipeline — floor to exchange step."""
    if qty_step <= 0:
        qty_str = f"{qty:.8f}".rstrip("0").rstrip(".")
        return qty_str, _float(qty_str)
    qty_str = _round_qty(qty, qty_step)
    return qty_str, _float(qty_str)


def run_exchange_preflight(
    *,
    client: DemoWriteClient,
    symbol: str,
    entry_price: float,
    equity: float,
    stop_pct: float = 0.40,
    target_pct: float = 0.55,
    preferred_notional: float = 350.0,
    max_loss_equity_pct: float = 0.10,
    liquidity: float = 0.9,
) -> dict[str, Any]:
    """Preflight one candidate — return pass or EXCHANGE_SIZE_INFEASIBLE."""
    try:
        meta = load_instrument_metadata(client, symbol)
    except Exception as exc:  # noqa: BLE001
        return {
            "schema": PREFLIGHT_SCHEMA,
            "symbol": symbol,
            "preflight_pass": False,
            "block_code": "INSTRUMENT_METADATA_UNAVAILABLE",
            "detail": type(exc).__name__,
        }

    sizing = compute_risk_based_size(
        equity=equity,
        entry_price=entry_price,
        stop_distance_pct=stop_pct,
        target_distance_pct=target_pct,
        fee_rate_roundtrip=0.0011,
        slippage_pct=0.02,
        liquidity=liquidity,
        confidence=0.75,
        qty_step=meta.qty_step,
        min_qty=meta.min_order_qty,
        min_notional=meta.min_notional,
        preferred_notional=preferred_notional,
        max_loss_equity_pct=max_loss_equity_pct,
    )

    if sizing.action != "SIZE" or not sizing.qty_str:
        min_risk_notional = meta.min_order_qty * entry_price if entry_price > 0 else meta.min_notional
        wallet_risk_cap = equity * (max_loss_equity_pct / 100.0)
        block = EXCHANGE_SIZE_INFEASIBLE if (
            meta.min_order_qty > 0 and min_risk_notional > wallet_risk_cap * 5
        ) else (sizing.block_code or "RISK_SIZING_WAIT")
        return {
            "schema": PREFLIGHT_SCHEMA,
            "symbol": symbol,
            "preflight_pass": False,
            "block_code": block,
            "instrument": meta.to_dict(),
            "sizing": sizing.to_dict(),
            "min_order_exceeds_risk": block == EXCHANGE_SIZE_INFEASIBLE,
        }

    qty_str, qty_f = normalize_qty(_float(sizing.qty_str), qty_step=meta.qty_step)
    notional = qty_f * entry_price

    if meta.min_order_qty > 0 and qty_f + 1e-15 < meta.min_order_qty:
        return {
            "schema": PREFLIGHT_SCHEMA,
            "symbol": symbol,
            "preflight_pass": False,
            "block_code": EXCHANGE_SIZE_INFEASIBLE,
            "instrument": meta.to_dict(),
            "detail": f"normalized_qty={qty_f}<minOrderQty={meta.min_order_qty}",
            "min_order_exceeds_risk": True,
        }
    if meta.min_notional > 0 and notional + 1e-9 < meta.min_notional:
        return {
            "schema": PREFLIGHT_SCHEMA,
            "symbol": symbol,
            "preflight_pass": False,
            "block_code": EXCHANGE_SIZE_INFEASIBLE,
            "instrument": meta.to_dict(),
            "detail": f"notional={notional}<minNotional={meta.min_notional}",
            "min_order_exceeds_risk": True,
        }
    if meta.max_order_qty and qty_f > meta.max_order_qty:
        qty_str, qty_f = normalize_qty(meta.max_order_qty, qty_step=meta.qty_step)
        notional = qty_f * entry_price

    wallet_risk_usdt = notional * (stop_pct / 100.0)
    wallet_risk_pct = (wallet_risk_usdt / equity * 100.0) if equity > 0 else 999.0
    if wallet_risk_pct > max_loss_equity_pct + 1e-9:
        return {
            "schema": PREFLIGHT_SCHEMA,
            "symbol": symbol,
            "preflight_pass": False,
            "block_code": EXCHANGE_SIZE_INFEASIBLE,
            "instrument": meta.to_dict(),
            "detail": f"wallet_risk_pct={wallet_risk_pct:.4f}>{max_loss_equity_pct}",
            "min_order_exceeds_risk": True,
        }

    return {
        "schema": PREFLIGHT_SCHEMA,
        "symbol": symbol,
        "preflight_pass": True,
        "block_code": None,
        "instrument": meta.to_dict(),
        "normalized_qty": qty_str,
        "normalized_qty_float": qty_f,
        "notional_usdt": notional,
        "wallet_risk_pct": wallet_risk_pct,
        "sizing": sizing.to_dict(),
    }


def preflight_ranked_candidates(
    candidates: list[Any],
    *,
    client: DemoWriteClient,
    equity: float,
    stop_pct: float = 0.40,
    target_pct: float = 0.55,
    max_loss_equity_pct: float = 0.10,
) -> dict[str, Any]:
    """Try candidates in rank order; fall through on preflight failure."""
    attempts: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    selected_preflight: dict[str, Any] | None = None

    ranked = sorted(
        candidates,
        key=lambda c: float(getattr(c, "rank_score", None) or (c.get("rank_score") if isinstance(c, dict) else 0) or 0),
        reverse=True,
    )

    for i, cand in enumerate(ranked):
        if isinstance(cand, dict):
            sym = str(cand.get("symbol") or "")
            entry = float(cand.get("entry_price") or 0)
            liq = float(cand.get("liquidity") or cand.get("liquidity_score") or 0.9)
            gates_ok = (
                cand.get("economic_edge_pass")
                and cand.get("horizon_feasibility_pass")
                and cand.get("risk_pass", True)
                and cand.get("horizon_config_valid", True)
            )
        else:
            sym = str(getattr(cand, "symbol", "") or "")
            entry = float(getattr(cand, "entry_price", 0) or 0)
            liq = float(getattr(cand, "liquidity", 0) or 0.9)
            gates_ok = (
                cand.economic_edge_pass
                and cand.horizon_feasibility_pass
                and cand.risk_pass
                and cand.horizon_config_valid
            )

        if not sym or entry <= 0 or not gates_ok:
            continue

        pf = run_exchange_preflight(
            client=client,
            symbol=sym,
            entry_price=entry,
            equity=equity,
            stop_pct=stop_pct,
            target_pct=target_pct,
            max_loss_equity_pct=max_loss_equity_pct,
            liquidity=liq,
        )
        pf["candidate_rank"] = i + 1
        attempts.append(pf)

        if pf.get("preflight_pass"):
            selected = cand if isinstance(cand, dict) else cand.to_dict()
            selected_preflight = pf
            break

    return {
        "schema": "v18_2_28_preflight_fallthrough_v1",
        "attempts": attempts,
        "attempts_n": len(attempts),
        "selected": selected,
        "selected_preflight": selected_preflight,
        "action": "SELECT" if selected else "WAIT",
        "block_code": None if selected else (attempts[-1].get("block_code") if attempts else "NO_ELIGIBLE_CANDIDATE"),
        "fallthrough_enabled": True,
        "cycle_terminated_on_first_failure": False,
    }

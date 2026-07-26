"""Autonomous Demo orchestrator — scan → select → size → (optional) send."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from backend.nexus_research.demo_autonomous.leverage_policy import ConfidenceLeveragePolicy
from backend.nexus_research.demo_autonomous.session_authorization import (
    AuthorizationValidator,
    get_authorization_validator,
)
from backend.nexus_research.demo_autonomous.universe import (
    DynamicContractUniverse,
    FIXTURE_INSTRUMENTS,
    LiquidityTier,
    MarketQualitySnapshot,
    TradableContract,
    fixture_quality,
)
from backend.nexus_research.demo_autonomous.write_adapter import (
    AutonomousDemoOrderAdapter,
    make_order_link_id,
)
from backend.nexus_research.demo_autonomous.write_trace import DemoWriteStageTrace
from backend.nexus_research.demo_execution.intent import DemoOrderIntent
from backend.nexus_research.demo_execution.preflight import DemoOrderPreflight
from backend.nexus_research.demo_execution.state_machine import DemoOrderState, DemoOrderStateMachine
from backend.nexus_research.demo_autonomous.multi_strategy import pick_best_strategy
from backend.nexus_research.demo_autonomous.risk_budget import AutonomousDemoRiskBudget
from backend.nexus_research.demo_strategy.capital_allocator import DemoCapitalAllocator
from backend.nexus_research.demo_strategy.market_features import extract_features
from backend.nexus_research.demo_strategy.risk_tiers import RiskTierName
from backend.nexus_research.demo_strategy.strategy_evaluator import evaluate


ENTRY_PRICE_HINT = {
    "BTCUSDT": 105_000.0,
    "ETHUSDT": 3_500.0,
    "SOLUSDT": 180.0,
    "PEPEUSDT": 0.000012,
}


@dataclass
class AutonomousCandidate:
    symbol: str
    tier: str
    side: str
    strategy: str
    regime: str
    confidence: float
    leverage: int
    qty: float
    notional: float
    margin: float
    risk_pct: float
    risk_amount: float
    stop_price: float
    take_profit_price: float | None
    liquidation_buffer: float
    expected_r: float | None
    allow_trade: bool
    block_reasons: list[str] = field(default_factory=list)
    why_selected: str = ""
    rejected_others: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "tier": self.tier,
            "side": self.side,
            "strategy": self.strategy,
            "regime": self.regime,
            "confidence": self.confidence,
            "leverage": self.leverage,
            "qty": self.qty,
            "notional": self.notional,
            "margin": self.margin,
            "riskPct": self.risk_pct,
            "riskAmount": self.risk_amount,
            "stopPrice": self.stop_price,
            "takeProfitPrice": self.take_profit_price,
            "liquidationBuffer": self.liquidation_buffer,
            "expectedR": self.expected_r,
            "allowTrade": self.allow_trade,
            "blockReasons": list(self.block_reasons),
            "whySelected": self.why_selected,
            "rejectedOthers": list(self.rejected_others),
        }


@dataclass
class OrchestratorResult:
    universe_summary: dict[str, Any]
    candidates: list[AutonomousCandidate]
    top: AutonomousCandidate | None
    order_sent: bool
    write_result: dict[str, Any] | None
    state: str
    session_active: bool
    dry_run: bool
    blocker: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe": self.universe_summary,
            "candidates": [c.to_dict() for c in self.candidates],
            "top": self.top.to_dict() if self.top else None,
            "orderSent": self.order_sent,
            "writeResult": self.write_result,
            "state": self.state,
            "sessionActive": self.session_active,
            "dryRun": self.dry_run,
            "blocker": self.blocker,
            "secretSafe": True,
            "mainnetUsed": False,
            "realMoneyUsed": False,
        }


class AutonomousDemoOrchestrator:
    """End-to-end Demo autonomous cycle (send only when enabled + authorized)."""

    def __init__(
        self,
        *,
        auth: AuthorizationValidator | None = None,
        write_adapter: AutonomousDemoOrderAdapter | None = None,
        dry_run: bool = True,
    ) -> None:
        self.auth = auth or get_authorization_validator()
        self.write_adapter = write_adapter
        self.dry_run = dry_run
        self.universe = DynamicContractUniverse()
        self.lev_policy = ConfidenceLeveragePolicy()
        self.allocator = DemoCapitalAllocator()
        self.risk_budget: AutonomousDemoRiskBudget | None = None

    def run_cycle(
        self,
        *,
        equity: float,
        instruments: list[dict[str, Any]] | None = None,
        quality: dict[str, MarketQualitySnapshot] | None = None,
        feature_rows: dict[str, dict[str, Any]] | None = None,
        open_positions: int = 0,
        open_orders: int = 0,
        send: bool = False,
        stop_distance_pct: float = 1.5,
    ) -> OrchestratorResult:
        instruments = instruments or FIXTURE_INSTRUMENTS
        quality = quality or fixture_quality()
        contracts = self.universe.build(instruments, quality)
        summary = self.universe.summary(contracts)

        if self.risk_budget is None or abs(self.risk_budget.equity - equity) > 1e-6:
            self.risk_budget = AutonomousDemoRiskBudget(equity=equity)

        session_active = False
        try:
            session_active = self.auth.session is not None and self.auth.session.is_active()
        except Exception:
            session_active = False

        risk_ok, risk_reason = self.risk_budget.allow_new_order()
        if not risk_ok:
            return OrchestratorResult(
                summary, [], None, False, None, "RISK_BUDGET_PAUSED",
                session_active, self.dry_run, blocker=risk_reason,
            )

        if open_positions > 0 or open_orders > 0:
            return OrchestratorResult(
                summary, [], None, False, None, "BLOCKED_EXISTING_EXPOSURE",
                session_active, self.dry_run,
                blocker="existing_position_or_order",
            )

        candidates: list[AutonomousCandidate] = []
        for c in contracts:
            if not c.allow_trade:
                continue
            for side in ("LONG", "SHORT"):
                cand = self._evaluate_one(
                    c, side=side, equity=equity,
                    feature_rows=feature_rows,
                    stop_distance_pct=stop_distance_pct,
                )
                if cand is not None:
                    candidates.append(cand)

        candidates.sort(key=lambda x: (x.allow_trade, x.confidence), reverse=True)
        top = next((c for c in candidates if c.allow_trade), None)
        if top:
            rejected = [
                f"{c.symbol}:{c.side}:{c.confidence:.1f}:{','.join(c.block_reasons[:2]) or 'ok_but_lower'}"
                for c in candidates if c is not top
            ][:12]
            top.rejected_others = rejected
            top.why_selected = (
                f"highest_confidence_eligible tier={top.tier} conf={top.confidence:.1f} "
                f"lev={top.leverage} risk={top.risk_pct}%"
            )

        if top is None:
            return OrchestratorResult(
                summary, candidates, None, False, None, "NO_ELIGIBLE_CANDIDATE",
                session_active, self.dry_run, blocker="no_eligible_candidate",
            )

        if not send:
            return OrchestratorResult(
                summary, candidates, top, False, None, "READY_HOLD_NO_SEND",
                session_active, self.dry_run,
            )

        if not session_active:
            return OrchestratorResult(
                summary, candidates, top, False, None, "SESSION_INACTIVE",
                False, self.dry_run, blocker="session_inactive",
            )

        if self.write_adapter is None:
            return OrchestratorResult(
                summary, candidates, top, False, None, "ADAPTER_MISSING",
                session_active, self.dry_run, blocker="write_adapter_missing",
            )

        return self._send_top(top, summary, candidates, session_active)

    def _evaluate_one(
        self,
        contract: TradableContract,
        *,
        side: str,
        equity: float,
        feature_rows: dict[str, dict[str, Any]] | None,
        stop_distance_pct: float,
    ) -> AutonomousCandidate | None:
        symbol = contract.meta.symbol
        q = contract.quality
        row = (feature_rows or {}).get(symbol) or {
            "symbol": symbol,
            "trendScore": 45.0 if side == "LONG" else -45.0,
            "momentumScore": 32.0 if side == "LONG" else -32.0,
            "rsi14": 58.0 if side == "LONG" else 42.0,
            "atrPct": q.atr_pct or 2.0,
            "fundingRate8hPct": 0.01,
            "openInterestUsd": q.open_interest,
            "volume24hUsd": q.volume_24h,
            "spreadBps": q.spread_bps,
            "freshnessMs": q.freshness_ms,
        }
        feat = extract_features(row, source="autonomous_scan")
        ev = evaluate(feat, side)
        conf = float(ev.composite_score)
        blocks = list(ev.block_reasons)
        strategy, regime, _strat_score = pick_best_strategy(feat, side)
        if regime in {"LOW_LIQUIDITY", "EVENT_RISK"}:
            blocks.append(f"regime_block:{regime}")

        lev = self.lev_policy.select(
            tier=contract.tier,
            confidence=conf,
            stop_distance_pct=stop_distance_pct,
            instrument_max_leverage=contract.meta.max_leverage,
            atr_pct=q.atr_pct,
            spread_bps=q.spread_bps,
        )
        if not lev.allow:
            blocks.extend(lev.block_reasons)

        entry = float(q.last_price or ENTRY_PRICE_HINT.get(symbol, 100.0))
        if entry <= 0:
            entry = float(ENTRY_PRICE_HINT.get(symbol, 100.0))
        alloc = self.allocator.allocate(
            symbol=symbol,
            direction=side,
            entry_price=entry,
            stop_distance_pct=stop_distance_pct,
            equity=equity,
            tier=RiskTierName.VALIDATION,
            is_first_order=True,
            requested_leverage=lev.selected or 1,
            current_open_positions=0,
            source="autonomous",
            allow_dynamic_leverage=True,
        )
        if not alloc.allow_trade:
            blocks.extend(alloc.block_reasons)

        allow = (
            ev.allow_trade and lev.allow and alloc.allow_trade and conf >= 65
            and regime not in {"LOW_LIQUIDITY", "EVENT_RISK"}
        )
        stop = entry * (1 - stop_distance_pct / 100.0) if side == "LONG" else entry * (1 + stop_distance_pct / 100.0)
        tp = entry * (1 + 1.5 * stop_distance_pct / 100.0) if side == "LONG" else entry * (1 - 1.5 * stop_distance_pct / 100.0)

        return AutonomousCandidate(
            symbol=symbol,
            tier=contract.tier.value,
            side="Buy" if side == "LONG" else "Sell",
            strategy=strategy,
            regime=regime,
            confidence=conf,
            leverage=int(alloc.leverage if allow else (lev.selected or 0)),
            qty=float(alloc.qty if allow else 0.0),
            notional=float(alloc.notional if allow else 0.0),
            margin=float(alloc.margin_required if allow else 0.0),
            risk_pct=float(alloc.risk_pct),
            risk_amount=float(alloc.risk_amount_usd),
            stop_price=float(stop),
            take_profit_price=float(tp),
            liquidation_buffer=float(lev.stop_to_liq_buffer_pct),
            expected_r=1.5,
            allow_trade=allow,
            block_reasons=blocks,
        )

    def _send_top(
        self,
        top: AutonomousCandidate,
        summary: dict[str, Any],
        candidates: list[AutonomousCandidate],
        session_active: bool,
    ) -> OrchestratorResult:
        entry_px = float(top.notional / top.qty) if top.qty else ENTRY_PRICE_HINT.get(top.symbol, 100.0)
        intent = DemoOrderIntent(
            intent_id=f"auto-{int(time.time())}",
            symbol=top.symbol,
            side=top.side,
            qty=top.qty,
            leverage=top.leverage,
            entry_price=entry_px,
            stop_loss_price=top.stop_price,
            take_profit_price=top.take_profit_price,
            risk_tier="VALIDATION",
            client_order_id=make_order_link_id(top.symbol, top.side, top.qty, top.leverage),
            source="autonomous_orchestrator",
        )
        # Dynamic universe: allow the selected symbol; majors may go to 50x when policy permits.
        pre = DemoOrderPreflight(
            max_open_positions=1,
            current_open_positions=0,
            ambiguous_orders_exist=False,
            allowed_symbols={top.symbol},
            max_leverage=50,
            min_leverage=1,
        ).check(intent)
        sm = DemoOrderStateMachine()
        if not pre.all_passed:
            sm.transition(DemoOrderState.PREFLIGHT_BLOCKED, reason="preflight")
            return OrchestratorResult(
                summary, candidates, top, False, {"preflight": pre.to_dict()},
                sm.state.value, session_active, self.dry_run, blocker="preflight_blocked",
            )

        sm.transition(DemoOrderState.READY_FOR_AUTHORIZATION, reason="preflight_ok")
        # Session already authorized — treat as AUTHORIZED
        sm.transition(DemoOrderState.AUTHORIZED, reason="session_grant")
        sm.transition(DemoOrderState.SEND_STARTED, reason="send")

        assert self.write_adapter is not None
        self.write_adapter.last_trace = DemoWriteStageTrace()
        account = self.write_adapter.refresh_account_truth()

        # Instrument truth for qty rounding
        instrument = None
        try:
            from backend.nexus_research.demo_autonomous.account_mode import DemoInstrumentTruth
            if self.write_adapter.get_json is not None:
                raw = self.write_adapter.get_json(
                    "/v5/market/instruments-info",
                    {"category": "linear", "symbol": top.symbol},
                )
                rows = ((raw.get("result") or {}).get("list") or [])
                if rows and isinstance(rows[0], dict):
                    row = rows[0]
                    lot = row.get("lotSizeFilter") or {}
                    price = row.get("priceFilter") or {}
                    lev = row.get("leverageFilter") or {}
                    instrument = DemoInstrumentTruth(
                        symbol=top.symbol,
                        category="linear",
                        status=str(row.get("status") or ""),
                        max_leverage=float(lev.get("maxLeverage") or 0),
                        qty_step=float(lot.get("qtyStep") or 0),
                        min_order_qty=float(lot.get("minOrderQty") or 0),
                        min_notional=float(lot.get("minNotionalValue") or 0),
                        tick_size=float(price.get("tickSize") or 0),
                    )
                    if instrument.qty_step > 0:
                        from backend.nexus_research.demo_autonomous.write_adapter import round_qty_to_step
                        rounded = round_qty_to_step(top.qty, instrument.qty_step, instrument.min_order_qty)
                        if rounded <= 0:
                            sm.transition(DemoOrderState.REJECTED, reason="qty_precision")
                            return OrchestratorResult(
                                summary, candidates, top, False,
                                {"trace": self.write_adapter.last_trace.to_dict(), "account": account.to_dict()},
                                sm.state.value, session_active, self.dry_run,
                                blocker="qty_rounded_to_zero",
                            )
                        # mutate intent qty via reconstruct
                        intent = DemoOrderIntent(
                            intent_id=intent.intent_id,
                            symbol=intent.symbol,
                            side=intent.side,
                            qty=rounded,
                            leverage=intent.leverage,
                            entry_price=intent.entry_price,
                            stop_loss_price=intent.stop_loss_price,
                            take_profit_price=intent.take_profit_price,
                            risk_tier=intent.risk_tier,
                            client_order_id=intent.client_order_id,
                            source=intent.source,
                        )
        except Exception:
            instrument = None

        lev_res = self.write_adapter.set_leverage(top.symbol, top.leverage)
        if not lev_res.ok:
            sm.transition(DemoOrderState.REJECTED, reason=lev_res.ret_msg or lev_res.error or "set_leverage_failed")
            return OrchestratorResult(
                summary, candidates, top, False,
                {
                    "leverage": lev_res.to_dict(),
                    "trace": self.write_adapter.last_trace.to_dict(),
                    "rootCause": self.write_adapter.last_trace.root_cause_report(),
                    "account": account.to_dict(),
                },
                sm.state.value, session_active, self.dry_run,
                blocker=lev_res.classification or lev_res.ret_msg or "set_leverage_failed",
            )

        iso_res = self.write_adapter.ensure_isolated(top.symbol, top.leverage)
        if not iso_res.ok:
            sm.transition(DemoOrderState.REJECTED, reason=iso_res.ret_msg or iso_res.error or "margin_mode_failed")
            return OrchestratorResult(
                summary, candidates, top, False,
                {
                    "leverage": lev_res.to_dict(),
                    "marginMode": iso_res.to_dict(),
                    "trace": self.write_adapter.last_trace.to_dict(),
                    "rootCause": self.write_adapter.last_trace.root_cause_report(),
                    "account": account.to_dict(),
                },
                sm.state.value, session_active, self.dry_run,
                blocker=iso_res.classification or iso_res.ret_msg or "margin_mode_failed",
            )

        place_res = self.write_adapter.place_order(
            intent,
            instrument=instrument,
            position_mode=account.position_mode,
        )
        order_sent = place_res.ok
        if place_res.ok:
            sm.transition(DemoOrderState.ACKNOWLEDGED, reason="exchange_ack")
            prot = self.write_adapter.set_trading_stop(
                top.symbol, stop_loss=top.stop_price, take_profit=top.take_profit_price,
            )
            write_payload = {
                "account": account.to_dict(),
                "leverage": lev_res.to_dict(),
                "marginMode": iso_res.to_dict(),
                "place": place_res.to_dict(),
                "protection": prot.to_dict(),
                "clientOrderId": intent.client_order_id,
                "trace": self.write_adapter.last_trace.to_dict(),
                "rootCause": self.write_adapter.last_trace.root_cause_report(),
                "instrument": instrument.to_dict() if instrument else None,
            }
            if not prot.ok:
                state = "PROTECTION_FAILED"
                # Do not claim PROTECTED
            else:
                state = "PROTECTED"
        else:
            sm.transition(
                DemoOrderState.AMBIGUOUS if place_res.error and "Timeout" in (place_res.error or "") else DemoOrderState.REJECTED,
                reason=place_res.error or place_res.ret_msg,
            )
            write_payload = {
                "account": account.to_dict(),
                "leverage": lev_res.to_dict(),
                "marginMode": iso_res.to_dict(),
                "place": place_res.to_dict(),
                "trace": self.write_adapter.last_trace.to_dict(),
                "rootCause": self.write_adapter.last_trace.root_cause_report(),
                "instrument": instrument.to_dict() if instrument else None,
            }
            state = sm.state.value

        return OrchestratorResult(
            summary, candidates, top, order_sent, write_payload, state,
            session_active, self.dry_run,
            blocker=None if order_sent else (place_res.classification or place_res.error or place_res.ret_msg or "place_failed"),
        )
